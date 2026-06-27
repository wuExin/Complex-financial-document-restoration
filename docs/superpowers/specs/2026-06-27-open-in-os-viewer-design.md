# Open Original Image in OS Viewer

**Date:** 2026-06-27
**Status:** Approved (pending review)
**Supersedes:** in-browser large-image viewer from `2026-06-25-image-gallery-design.md`

## Problem

The in-browser large-image viewer cannot reliably display real AFAC scans. Originals reach 1500×92024 (138M pixels), well over Chrome's `<img>` decode limit (~100M px). Commit `1face75` mitigated this by serving a 2000px downsampled preview, but:

- The preview is capped at 2000px, far below original resolution — fine details are unreadable
- The handoff doc (`98130b9`) notes the fix was applied but never browser-verified
- For a document-restoration task, the user needs to see full original resolution

The user's decision: bypass the browser entirely. Clicking a thumbnail should launch the OS's default image viewer (Windows Photos, etc.) on the **original** file, which handles 138M-pixel images natively.

## Design

### Approach

Full replacement (not additive). Remove the in-browser viewer, the `/image` route, and the preview-generation pipeline. Add a new `/open` endpoint that launches the OS default viewer. The frontend becomes a browser+launcher: tabs, sidebar, search, prev/next stay; zoom/pan/rotate/wheel/drag/error-overlay go away.

A browser cannot directly launch a local application — but the Flask backend runs locally with filesystem access, so it can call `os.startfile()` (Windows) or equivalent on the user's behalf.

### Backend (`src/app.py`)

**New endpoint:** `POST /open/<subset>/<uuid>`

1. Validate `subset` and `uuid` contain no path separators or `..` (path-traversal guard, same pattern as existing `/thumb` route)
2. Load manifest, find the image record matching `(subset, uuid)`
3. Read `image_path` (relative to project root) — this points at the **original** file under `data/`, not the preview
4. Resolve to `PROJECT_ROOT / image_path`; verify the file exists
5. Call `_open_in_default_viewer(path)` — a small helper:
   ```python
   def _open_in_default_viewer(path: Path) -> None:
       if sys.platform == "win32":
           os.startfile(str(path))
       elif sys.platform == "darwin":
           subprocess.Popen(["open", str(path)])
       else:
           subprocess.Popen(["xdg-open", str(path)])
   ```
   (`os.startfile` returns immediately; `Popen` is non-blocking. HTTP response stays fast.)
6. Return JSON:
   - `200 {ok: true, path: "..."}` on success
   - `404 {error: "..."}` if subset/uuid unknown, file missing, or path-traversal guard trips
   - `500 {error: "..."}` if `os.startfile` raises `OSError` for any other reason

**Removed:**
- `/image/<subset>/<uuid>` route
- `_find_image_path` helper (no longer needed)

### Backend (`src/gen_thumbs.py`)

**Removed:**
- `PREVIEW_LONG_EDGE` constant
- Preview-generation loop body (the second `generate_thumbnail` call writing to `previews_root`)
- `previews_root` variable
- `preview_path` field in `ImageInfo` TypedDict and in the manifest-writing loop

Thumbnails (`/thumb` route, `THUMBNAIL_LONG_EDGE`, `thumb_path` field) stay — the sidebar still needs them.

### Frontend (`src/static/index.html`)

Replace the entire `#viewer` section's interior:
- Remove `<img id="main-image">`, the toolbar (`#zoom-out`, `#zoom-in`, `#zoom-pct`, `#rotate`, `#fit`), the error overlay, and the prev/next arrow buttons inside `#canvas`
- Keep `#filename`, `#file-meta`, `#position-info` (move them into a single status panel)
- Add a thumbnail preview element so the user has visual context for what's currently selected

New `#viewer` layout (sketch):
```
┌─ toolbar ─────────────────────────────────┐
│ filename.jpg   12.3 MB   1/100 训练长文档   │
├─ canvas ──────────────────────────────────┤
│                                           │
│         [thumbnail of current image]      │
│                                           │
│         已用系统查看器打开                  │
│         ← → 切换上一张/下一张               │
│                                           │
├─ statusbar ───────────────────────────────┤
│ ← → 翻页                                  │
└───────────────────────────────────────────┘
```

Prev/next arrows become optional (keyboard nav covers it). Decision: keep simple on-screen ‹ › buttons inside the canvas for discoverability.

### Frontend (`src/static/app.js`)

**Replaced:** `showImage(index)` now:
1. Updates sidebar highlight, filename, file-meta, position-info (same as today)
2. Updates the thumbnail preview's `src` to `/thumb/...` (gives visual context)
3. `fetch("/open/<subset>/<uuid>", {method: "POST"})` — fire the OS viewer
4. On non-200 response, show an inline error in the status panel

**Removed:**
- `zoomState`, `MIN_SCALE`, `MAX_SCALE`, `$zoomPct`, `$btnZoomIn`, `$btnZoomOut`, `$btnRotate`, `$btnFit`
- `computeFitScale`, `setScale`, `applyTransform`, `resetView`
- `load` listener on `$mainImage`
- Wheel zoom handler
- `dragState`, mousedown/mousemove/mouseup handlers

**Kept (unchanged or trivially modified):**
- `loadManifest`, `renderTabs`, `selectSubset`, `getCurrentImageList`, `renderSidebar`, `clearViewer`, `formatBytes`
- Search input handler
- `gotoOffset`, `$btnPrev`/`$btnNext`, keyboard nav

### Tests (`tests/test_app.py`)

**Add (with `monkeypatch` on `os.startfile` to avoid actually launching Photo Viewer during tests):**
- `test_open_returns_ok` — valid subset+uuid → 200, JSON `{ok: true}`
- `test_open_404_unknown_uuid` — valid subset, fake uuid → 404
- `test_open_404_unknown_subset` — fake subset → 404
- `test_open_500_when_startfile_fails` — `os.startfile` raises `OSError` → 500

**Remove:**
- `test_get_image_returns_jpeg`
- `test_get_image_404_on_unknown_uuid`

### Tests (`tests/test_gen_thumbs.py`)

Update any test that asserts `preview_path` exists in manifest records — remove those assertions.

## Security Considerations

- `subset` and `uuid` are validated against the manifest (must match a record). Path traversal via `..` or separators is blocked at the route boundary.
- `image_path` comes from a locally-generated manifest; we trust it. Adding a "resolved path must be under PROJECT_ROOT/data/" check would be defense-in-depth but is not strictly necessary for a single-user local tool. Decision: skip it (YAGNI).
- `os.startfile` / `subprocess.Popen` only receive paths derived from manifest data — no shell=True, no user-controlled arguments.

## Out of Scope

- Existing files in `outputs/previews/` (gitignored) stay on disk; not deleted by code changes
- No new dependencies
- No changes to `/thumb`, `/api/manifest`, `/`, `/static/<path>` routes
- README updates will be done as part of the implementation plan

## Migration

Users with stale `outputs/manifest.json` (containing `preview_path`) don't need to regenerate — the `/open` route only reads `image_path`, which has been present since the initial implementation. The `preview_path` field just becomes ignored dead data in old manifests. Regenerating via `gen_thumbs.py` produces clean manifests without it.
