# Open Original Image in OS Viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-browser large-image viewer with a backend endpoint that launches the OS default image viewer on the original file.

**Architecture:** New `POST /open/<subset>/<uuid>` Flask route calls `os.startfile()` (Windows) / `open` (macOS) / `xdg-open` (Linux) on the original file path from the manifest. Frontend `showImage()` becomes a status panel that fires this endpoint on thumbnail click. Dead `/image` route, preview generation, and zoom/pan/rotate UI are removed.

**Tech Stack:** Python 3 + Flask (backend), vanilla JS + HTML (frontend), pytest (tests), PIL (thumbnail gen).

**Spec:** `docs/superpowers/specs/2026-06-27-open-in-os-viewer-design.md`

---

## File Map

- **Modify** `src/app.py` — add `/open` route + `_open_in_default_viewer` helper; remove `/image` route + `_find_image_path`
- **Modify** `src/gen_thumbs.py` — remove `PREVIEW_LONG_EDGE`, `previews_root`, preview-generation loop, `preview_path` field
- **Modify** `src/static/index.html` — replace `#viewer` interior with status panel
- **Modify** `src/static/app.js` — rewrite `showImage()`, remove zoom/pan/rotate/wheel/drag handlers
- **Modify** `src/static/style.css` — drop dead rules for removed elements, add status-panel rules
- **Modify** `tests/test_app.py` — add 4 `/open` tests, remove 2 `/image` tests
- **Modify** `tests/conftest.py` — drop preview-file creation from `sample_outputs_dir`
- **Modify** `README.md` — update usage section

---

### Task 1: Add `/open` endpoint (TDD)

**Files:**
- Modify: `tests/test_app.py` (add tests at end of file)
- Modify: `src/app.py` (add route + helper)

- [ ] **Step 1: Write 4 failing tests**

Append to `tests/test_app.py`:

```python
def test_open_returns_ok(app_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /open for a valid uuid returns 200 and calls os.startfile."""
    import app as app_module

    calls = []
    monkeypatch.setattr(
        app_module, "_open_in_default_viewer", lambda p: calls.append(p)
    )
    resp = app_client.post("/open/train_long/aaaaaaaa-0000-0000-0000-000000000001")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert len(calls) == 1
    assert calls[0].name == "aaaaaaaa-0000-0000-0000-000000000001.jpg"


def test_open_404_on_unknown_uuid(app_client, monkeypatch: pytest.MonkeyPatch) -> None:
    import app as app_module

    monkeypatch.setattr(app_module, "_open_in_default_viewer", lambda p: None)
    resp = app_client.post("/open/train_long/not-a-real-uuid")
    assert resp.status_code == 404


def test_open_404_on_unknown_subset(app_client, monkeypatch: pytest.MonkeyPatch) -> None:
    import app as app_module

    monkeypatch.setattr(app_module, "_open_in_default_viewer", lambda p: None)
    resp = app_client.post("/open/unknown_subset/aaaaaaaa-0000-0000-0000-000000000001")
    assert resp.status_code == 404


def test_open_500_when_startfile_raises(app_client, monkeypatch: pytest.MonkeyPatch) -> None:
    import app as app_module

    def raise_oserror(path):
        raise OSError("simulated failure")

    monkeypatch.setattr(app_module, "_open_in_default_viewer", raise_oserror)
    resp = app_client.post("/open/train_long/aaaaaaaa-0000-0000-0000-000000000001")
    assert resp.status_code == 500
    assert "error" in resp.get_json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v -k open`
Expected: 4 FAIL with `AttributeError: module 'app' has no attribute '_open_in_default_viewer'` (or 404 because route doesn't exist).

- [ ] **Step 3: Implement helper + route**

In `src/app.py`, add `import os` and `import subprocess` to the imports block at the top (after existing imports). Then add this code immediately before the `@app.route("/image/<subset>/<uuid>")` line:

```python
def _open_in_default_viewer(path: Path) -> None:
    """Launch the OS default image viewer on `path`.

    os.startfile (Windows) returns immediately. Popen (macOS/Linux) is
    non-blocking. Either way the HTTP response stays fast.
    """
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _find_original_path(subset: str, uuid: str) -> Path | None:
    """Look up the original image path for (subset, uuid) in the manifest."""
    try:
        manifest = _load_manifest()
    except FileNotFoundError:
        return None
    subset_data = manifest.get("subsets", {}).get(subset)
    if not subset_data:
        return None
    for img in subset_data.get("images", []):
        if img["uuid"] == uuid:
            rel = img.get("image_path")
            if not rel:
                return None
            return PROJECT_ROOT / rel
    return None


@app.route("/open/<subset>/<uuid>", methods=["POST"])
def open_image(subset: str, uuid: str):
    if "/" in uuid or "\\" in uuid or ".." in uuid:
        abort(404)
    img_path = _find_original_path(subset, uuid)
    if img_path is None or not img_path.is_file():
        abort(404)
    try:
        _open_in_default_viewer(img_path)
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v -k open`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app.py tests/test_app.py
git commit -m "feat: add POST /open endpoint to launch OS image viewer"
```

---

### Task 2: Remove `/image` route + tests

**Files:**
- Modify: `src/app.py` (delete `_find_image_path` + `/image` route)
- Modify: `tests/test_app.py` (delete 2 tests)

- [ ] **Step 1: Delete the `/image` route and `_find_image_path`**

In `src/app.py`, delete the entire `_find_image_path` function (currently lines 59–79) AND the entire `@app.route("/image/<subset>/<uuid>")` block (currently lines 82–89). The `_find_original_path` added in Task 1 supersedes `_find_image_path`.

- [ ] **Step 2: Delete the 2 `/image` tests**

In `tests/test_app.py`, delete:

```python
def test_get_image_returns_jpeg(app_client) -> None:
    resp = app_client.get("/image/train_long/aaaaaaaa-0000-0000-0000-000000000001")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_get_image_404_on_unknown_uuid(app_client) -> None:
    resp = app_client.get("/image/train_long/not-a-real-uuid")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run all tests to verify nothing else broke**

Run: `pytest tests/ -v`
Expected: all tests PASS (10 remaining in test_app.py, 7 in test_gen_thumbs.py).

- [ ] **Step 4: Commit**

```bash
git add src/app.py tests/test_app.py
git commit -m "refactor: remove dead /image route and preview-serving logic"
```

---

### Task 3: Remove preview generation from `gen_thumbs.py`

**Files:**
- Modify: `src/gen_thumbs.py` (delete preview-related code)
- Modify: `tests/conftest.py` (drop preview file creation + `preview_path` field)

- [ ] **Step 1: Update conftest fixture**

In `tests/conftest.py`, inside `sample_outputs_dir`:

1. Delete the line `previews_root = outputs / "previews"` (line 37)
2. Delete the line `_make_test_image(previews_root / thumb_rel, color=(180, 180, 220), size=(1600, 2000))` (line 48)
3. Delete the line `"preview_path": thumb_rel,` (line 59)

The fixture should now read:

```python
@pytest.fixture
def sample_outputs_dir(tmp_path: Path) -> Path:
    """Build a temp outputs/ dir with manifest.json + 4 thumbnails (one per subset)."""
    outputs = tmp_path / "outputs"
    thumbs_root = outputs / "thumbs"

    subsets_data = {}
    for subset_key, label, uuid in [
        ("train_long", "训练长文档", "aaaaaaaa-0000-0000-0000-000000000001"),
        ("train_table", "训练表格", "bbbbbbbb-0000-0000-0000-000000000002"),
        ("eval_long", "评测长文档", "cccccccc-0000-0000-0000-000000000003"),
        ("eval_table", "评测表格", "dddddddd-0000-0000-0000-000000000004"),
    ]:
        thumb_rel = f"{subset_key}/{uuid}.jpg"
        _make_test_image(thumbs_root / thumb_rel, color=(150, 150, 200), size=(240, 320))
        src_rel = f"data/some_dir/{uuid}.jpg"
        _make_test_image(tmp_path / src_rel)
        subsets_data[subset_key] = {
            "label": label,
            "count": 1,
            "images": [
                {
                    "uuid": uuid,
                    "image_path": src_rel.replace("/", "/"),
                    "thumb_path": thumb_rel,
                    "size_bytes": (tmp_path / src_rel).stat().st_size,
                }
            ],
        }

    manifest = {
        "version": 1,
        "generated_at": "2026-06-25T12:00:00",
        "subsets": subsets_data,
    }
    (outputs / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return outputs
```

- [ ] **Step 2: Remove preview code from `gen_thumbs.py`**

1. Delete the line `preview_path: str  # browser-safe downsampled preview, added by main()` from the `ImageInfo` TypedDict (around line 27).

2. Delete the constant `PREVIEW_LONG_EDGE = 2000  # browser-safe preview (Chrome decodes <img> up to ~100M px)` (line 83).

3. In `main()`, replace the loop body (lines 145–156) to remove preview generation. Old:

   ```python
   thumbs_root = args.outputs_dir / "thumbs"
   previews_root = args.outputs_dir / "previews"
   for subset_key, subset in subsets.items():
       for img in subset["images"]:
           src = args.data_dir.parent / img["image_path"]
           uuid = img["uuid"]
           generate_thumbnail(src, thumbs_root / subset_key / f"{uuid}.jpg")
           # Browser-safe preview: real AFAC scans reach 1500x92024 (138M px),
           # which exceeds Chrome's <img> decode limit. Serve downsampled preview.
           generate_thumbnail(
               src, previews_root / subset_key / f"{uuid}.jpg", long_edge=PREVIEW_LONG_EDGE
           )

   # Add thumb_path + preview_path to each image record before writing manifest
   for subset_key, subset in subsets.items():
       for img in subset["images"]:
           uuid = img["uuid"]
           img["thumb_path"] = f"{subset_key}/{uuid}.jpg"
           img["preview_path"] = f"{subset_key}/{uuid}.jpg"
   ```

   New:

   ```python
   thumbs_root = args.outputs_dir / "thumbs"
   for subset_key, subset in subsets.items():
       for img in subset["images"]:
           src = args.data_dir.parent / img["image_path"]
           uuid = img["uuid"]
           generate_thumbnail(src, thumbs_root / subset_key / f"{uuid}.jpg")

   # Add thumb_path to each image record before writing manifest
   for subset_key, subset in subsets.items():
       for img in subset["images"]:
           uuid = img["uuid"]
           img["thumb_path"] = f"{subset_key}/{uuid}.jpg"
   ```

- [ ] **Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add src/gen_thumbs.py tests/conftest.py
git commit -m "refactor: drop preview generation (replaced by OS viewer)"
```

---

### Task 4: Rewrite frontend HTML

**Files:**
- Modify: `src/static/index.html` (replace `#viewer` section)

- [ ] **Step 1: Replace the `#viewer` interior**

In `src/static/index.html`, find the `<section id="viewer">...</section>` block (currently lines 22–48) and replace it entirely with:

```html
    <section id="viewer">
      <div id="toolbar">
        <span id="filename" class="mono">未选择</span>
        <span id="file-meta" class="meta"></span>
        <div class="spacer"></div>
        <span id="position-info" class="mono">—</span>
      </div>
      <div id="canvas">
        <button id="prev" class="nav-arrow" title="上一张">‹</button>
        <div id="status-panel">
          <img id="preview-thumb" alt="" hidden>
          <div id="status-text">点击左侧缩略图用系统查看器打开</div>
        </div>
        <button id="next" class="nav-arrow" title="下一张">›</button>
      </div>
      <div id="statusbar">
        <span id="hint">← → 翻页</span>
      </div>
    </section>
```

- [ ] **Step 2: Smoke-test page load**

Run: `python src/app.py` (then open the printed URL in browser, then Ctrl+C the server)
Expected: page loads, tabs and sidebar render with thumbnails, no console errors. Clicking thumbnails does nothing useful yet (no JS wired). Status panel shows placeholder text.

- [ ] **Step 3: Commit**

```bash
git add src/static/index.html
git commit -m "feat: replace in-browser image viewer with status panel HTML"
```

---

### Task 5: Rewrite frontend JS

**Files:**
- Modify: `src/static/app.js` (replace viewer logic)
- Modify: `src/static/style.css` (drop dead rules, add status-panel rules)

- [ ] **Step 1: Update DOM references in `app.js`**

In `src/static/app.js`, replace the existing DOM-reference block (lines 13–21) with:

```javascript
// DOM references
const $tabs = document.getElementById("tabs");
const $sidebarHeader = document.getElementById("sidebar-header");
const $thumbs = document.getElementById("thumbs");
const $searchInput = document.getElementById("search-input");
const $filename = document.getElementById("filename");
const $fileMeta = document.getElementById("file-meta");
const $positionInfo = document.getElementById("position-info");
const $previewThumb = document.getElementById("preview-thumb");
const $statusText = document.getElementById("status-text");
```

- [ ] **Step 2: Replace `showImage()` and `clearViewer()`**

In `src/static/app.js`, replace the existing `showImage` function (lines 91–111) and `clearViewer` function (lines 113–119) with:

```javascript
async function showImage(index) {
  if (index < 0 || index >= state.currentImages.length) return;
  state.currentIndex = index;
  const img = state.currentImages[index];
  // Update sidebar highlight
  document.querySelectorAll(".thumb").forEach((el, i) => {
    el.classList.toggle("active", i === index);
  });
  // Update toolbar
  $filename.textContent = `${img.uuid}.jpg`;
  $fileMeta.textContent = formatBytes(img.size_bytes);
  $positionInfo.textContent = `第 ${index + 1} / ${state.currentImages.length} 张 · ${state.manifest.subsets[state.currentSubset].label}`;
  // Show preview thumbnail (visual context for what's selected)
  $previewThumb.hidden = false;
  $previewThumb.src = `/thumb/${state.currentSubset}/${img.uuid}.jpg`;
  // Fire OS viewer
  $statusText.textContent = "正在打开…";
  try {
    const resp = await fetch(`/open/${state.currentSubset}/${img.uuid}`, { method: "POST" });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      $statusText.textContent = `打开失败：${body.error || resp.status}`;
    } else {
      $statusText.textContent = "已用系统查看器打开";
    }
  } catch (err) {
    $statusText.textContent = `打开失败：${err.message}`;
  }
}

function clearViewer() {
  state.currentIndex = -1;
  $filename.textContent = "未选择";
  $fileMeta.textContent = "";
  $positionInfo.textContent = "—";
  $previewThumb.hidden = true;
  $previewThumb.removeAttribute("src");
  $statusText.textContent = "点击左侧缩略图用系统查看器打开";
}
```

- [ ] **Step 3: Delete the entire zoom/pan/rotate block**

In `src/static/app.js`, delete lines 138–248 (from `// === Zoom / Pan / Rotate ===` through the end of the `mouseup` handler, just before `// === Navigation ===`).

Keep the navigation block (`gotoOffset`, `$btnPrev`, `$btnNext`, keyboard handler) — it's unchanged.

- [ ] **Step 4: Verify `$btnPrev` and `$btnNext` references still resolve**

After deletion, the existing code:

```javascript
const $btnPrev = document.getElementById("prev");
const $btnNext = document.getElementById("next");
```

should still be present in the file (they were part of the original const block at lines 158–159 — verify they weren't accidentally inside the deleted range). If they were deleted, restore them just above `$btnPrev.addEventListener(...)`.

- [ ] **Step 5: Update `style.css`**

Open `src/static/style.css` and:

1. Delete any rules referencing `#main-image`, `#zoom-pct`, `#zoom-in`, `#zoom-out`, `#rotate`, `#fit`, `#error-overlay`, `.grabbable`, `.grabbing`.
2. Add rules for the new status panel:

```css
#status-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  height: 100%;
  color: #666;
}

#preview-thumb {
  max-width: 320px;
  max-height: 320px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fff;
}

#status-text {
  font-size: 14px;
}
```

(Use the existing color/spacing variables if the file has them; otherwise these defaults are fine.)

- [ ] **Step 6: Manual end-to-end test**

Run: `python src/app.py` and open the URL.

Expected:
- Tabs render, sidebar shows thumbnails
- Clicking a thumbnail launches Windows Photos (or default viewer) on the **original** file
- Status panel shows "已用系统查看器打开"
- Preview thumbnail appears in the panel
- Prev/next arrows and ←/→ keys work
- Search filters the list

Verify on a real AFAC scan (e.g., a `train_long` image) that the OS viewer displays the full-resolution image.

- [ ] **Step 7: Commit**

```bash
git add src/static/app.js src/static/style.css
git commit -m "feat: wire thumbnail click to /open endpoint, drop zoom/pan UI"
```

---

### Task 6: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the "使用" section**

In `README.md`, replace lines 21–29 (the bullet list under `## 使用`) with:

```markdown
## 使用

- **顶部标签**：切换 4 个子集（训练长文档 / 训练表格 / 评测长文档 / 评测表格）
- **左侧列表**：点击缩略图，用系统默认图片查看器打开原图
- **状态面板**：显示当前选中的文件名、缩略图预览、打开状态
- **上一张 / 下一张**：‹ › 按钮 或 ← → 键
- **搜索框**：在当前子集内按 UUID 模糊过滤

> 为什么用系统查看器？真实的 AFAC 长文档扫描图可达 1500×92024（1.38 亿像素），
> 超过 Chrome 的 `<img>` 解码上限（约 1 亿像素）。系统查看器（Windows 照片等）
> 可以正常显示原始分辨率。
```

- [ ] **Step 2: Update the "目录结构" section if it mentions previews**

In `README.md`, the directory-structure block (lines 33–43) doesn't currently mention `previews/`, so no change needed there. (If `previews/` were mentioned, delete that line.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for OS-viewer launch flow"
```

---

## Self-Review

**Spec coverage:**
- ✅ Backend `/open` endpoint → Task 1
- ✅ Remove `/image` route + `_find_image_path` → Task 2
- ✅ Remove preview generation (`PREVIEW_LONG_EDGE`, `previews_root`, `preview_path` field, generation loop) → Task 3
- ✅ Frontend HTML status panel → Task 4
- ✅ Frontend JS rework (new `showImage`, remove zoom/pan/rotate) → Task 5
- ✅ Tests: 4 added for `/open`, 2 removed for `/image` → Tasks 1 & 2
- ✅ conftest preview cleanup → Task 3
- ✅ README update → Task 6
- ✅ Security (path-traversal guard, no shell=True) → Task 1 (route validates `uuid`, helper uses `Popen` with list args)

**Placeholder scan:** None — every step has actual code or exact edit instructions.

**Type/name consistency:** `_open_in_default_viewer` and `_find_original_path` defined in Task 1, called consistently in tests and route. `$previewThumb` and `$statusText` defined in Task 5 Step 1, used in Steps 2 & 3.

**Ordering notes:** Task 2 removes `/image` *after* Task 1 adds `/open`, so the test suite stays green between commits (no transient state where neither route exists). Task 3 (preview removal) is independent and could be done in any order relative to Tasks 1–2; placed here to keep backend changes together. Tasks 4–5 (frontend) come after backend so manual E2E in Task 5 Step 6 hits a real endpoint.
