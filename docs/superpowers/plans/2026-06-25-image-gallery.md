# AFAC 数据集图片浏览器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Flask + vanilla HTML/JS image browser for 300 AFAC dataset images across 4 subsets, with master-detail layout, tabs, and zoom/pan/rotate controls.

**Architecture:** Two Python scripts (`gen_thumbs.py` for one-time thumbnail pre-generation, `app.py` for Flask server) + static frontend (HTML/CSS/JS, zero deps). Thumbnails cached to `outputs/thumbs/`, image inventory in `outputs/manifest.json`.

**Tech Stack:** Python 3.13, Flask, Pillow, pytest; vanilla HTML/CSS/JS (no build tools).

**Spec:** `docs/superpowers/specs/2026-06-25-image-gallery-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `requirements.txt` | Python deps (flask, pillow, pytest) |
| `src/gen_thumbs.py` | Scan `data/`, generate thumbnails, write manifest |
| `src/app.py` | Flask server with 4 routes |
| `src/static/index.html` | Page skeleton (header tabs + sidebar + main) |
| `src/static/style.css` | Master-detail layout styling |
| `src/static/app.js` | Frontend logic (manifest, tabs, thumbnails, zoom/pan/rotate, keyboard, search) |
| `tests/__init__.py` | Empty marker |
| `tests/conftest.py` | Pytest fixtures (sample images, manifest) |
| `tests/test_gen_thumbs.py` | Tests for `gen_thumbs.py` |
| `tests/test_app.py` | Tests for Flask routes |
| `README.md` | Usage instructions |

---

## Task 1: Project Bootstrap

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `requirements.txt`**

```
flask>=3.0
pillow>=10.0
pytest>=8.0
```

- [ ] **Step 2: Create empty `tests/__init__.py`**

Empty file (just `touch`).

- [ ] **Step 3: Create `tests/conftest.py` with shared fixtures**

```python
"""Shared pytest fixtures for the AFAC image browser tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image


def _make_test_image(path: Path, color=(200, 200, 200), size=(800, 600)) -> None:
    """Create a small valid JPG at `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG")


@pytest.fixture
def sample_data_dir(tmp_path: Path) -> Path:
    """Build a temp data/ dir mirroring the real layout, with 1 image per subset."""
    data_root = tmp_path / "data"
    subsets = {
        "AFAC 训练数据集/finixdocbench_huge_long_100": "aaaaaaaa-0000-0000-0000-000000000001",
        "AFAC 训练数据集/finixdocbench_huge_table_100": "bbbbbbbb-0000-0000-0000-000000000002",
        "AFAC A榜评测数据集(2)/finix_huge_long_rest_A": "cccccccc-0000-0000-0000-000000000003",
        "AFAC A榜评测数据集(2)/finix_huge_table_rest_A": "dddddddd-0000-0000-0000-000000000004",
    }
    for sub_dir, uuid in subsets.items():
        _make_test_image(data_root / sub_dir / "images" / f"{uuid}.jpg")
    return data_root


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

- [ ] **Step 4: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: Successfully installs flask, pillow, pytest.

- [ ] **Step 5: Verify pytest discovers zero tests without errors**

Run: `pytest tests/ -v`
Expected: `no tests ran` (collection succeeded, no import errors).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/__init__.py tests/conftest.py
git commit -m "chore: bootstrap project with requirements and test fixtures"
```

---

## Task 2: Subset Configuration & Image Discovery

**Files:**
- Create: `src/gen_thumbs.py`
- Create: `tests/test_gen_thumbs.py`

- [ ] **Step 1: Write failing tests for `discover_images`**

Create `tests/test_gen_thumbs.py`:

```python
"""Tests for src/gen_thumbs.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_discover_images_finds_all_four_subsets(sample_data_dir: Path) -> None:
    from gen_thumbs import discover_images, SUBSETS

    result = discover_images(sample_data_dir)

    assert set(result.keys()) == {"train_long", "train_table", "eval_long", "eval_table"}
    for key in result:
        assert result[key]["label"] == SUBSETS[key]["label"]
        assert len(result[key]["images"]) == 1


def test_discover_images_records_uuid_and_path(sample_data_dir: Path) -> None:
    from gen_thumbs import discover_images

    result = discover_images(sample_data_dir)
    img = result["train_long"]["images"][0]
    assert img["uuid"] == "aaaaaaaa-0000-0000-0000-000000000001"
    assert img["image_path"].endswith(
        "aaaaaaaa-0000-0000-0000-000000000001.jpg"
    )
    assert "size_bytes" in img and img["size_bytes"] > 0


def test_discover_images_handles_missing_subset_dir(tmp_path: Path) -> None:
    """If a subset dir is missing, return empty list for it (don't crash)."""
    from gen_thumbs import discover_images

    result = discover_images(tmp_path / "empty_data")
    assert result["train_long"]["images"] == []
    assert result["train_long"]["count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gen_thumbs.py -v`
Expected: All 3 tests FAIL with `ModuleNotFoundError: No module named 'gen_thumbs'`.

- [ ] **Step 3: Implement `gen_thumbs.py` with `SUBSETS` and `discover_images`**

Create `src/gen_thumbs.py`:

```python
"""Generate thumbnails and manifest for the AFAC image browser.

Usage:
    python src/gen_thumbs.py [--data-dir DATA] [--outputs-dir OUTPUTS]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import TypedDict


class ImageInfo(TypedDict):
    uuid: str
    image_path: str  # path relative to project root
    size_bytes: int


class SubsetInfo(TypedDict):
    label: str
    count: int
    images: list[ImageInfo]


# Subset key -> metadata.
# data_subdir is the path under data/ that contains the images/ folder.
SUBSETS: dict[str, dict[str, str]] = {
    "train_long": {
        "label": "训练长文档",
        "data_subdir": "AFAC 训练数据集/finixdocbench_huge_long_100",
    },
    "train_table": {
        "label": "训练表格",
        "data_subdir": "AFAC 训练数据集/finixdocbench_huge_table_100",
    },
    "eval_long": {
        "label": "评测长文档",
        "data_subdir": "AFAC A榜评测数据集(2)/finix_huge_long_rest_A",
    },
    "eval_table": {
        "label": "评测表格",
        "data_subdir": "AFAC A榜评测数据集(2)/finix_huge_table_rest_A",
    },
}


def discover_images(data_root: Path) -> dict[str, SubsetInfo]:
    """Scan data_root for each subset's images, returning a dict keyed by subset.

    `image_path` in each entry is relative to data_root.parent (i.e., project root).
    Missing subset directories yield an empty image list rather than an error.
    """
    project_root = data_root.parent
    result: dict[str, SubsetInfo] = {}
    for key, meta in SUBSETS.items():
        images_dir = data_root / meta["data_subdir"] / "images"
        images: list[ImageInfo] = []
        if images_dir.is_dir():
            for jpg in sorted(images_dir.glob("*.jpg")):
                images.append(
                    {
                        "uuid": jpg.stem,
                        "image_path": str(jpg.relative_to(project_root)).replace("\\", "/"),
                        "size_bytes": jpg.stat().st_size,
                    }
                )
        result[key] = {"label": meta["label"], "count": len(images), "images": images}
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gen_thumbs.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/gen_thumbs.py tests/test_gen_thumbs.py
git commit -m "feat: add subset configuration and image discovery"
```

---

## Task 3: Thumbnail Generation

**Files:**
- Modify: `src/gen_thumbs.py`
- Modify: `tests/test_gen_thumbs.py`

- [ ] **Step 1: Write failing tests for `generate_thumbnail`**

Append to `tests/test_gen_thumbs.py`:

```python
def test_generate_thumbnail_creates_jpg(tmp_path: Path) -> None:
    from PIL import Image

    from gen_thumbs import generate_thumbnail

    src = tmp_path / "src.jpg"
    Image.new("RGB", (2000, 3000), (100, 150, 200)).save(src, "JPEG")
    dst = tmp_path / "out.jpg"

    ok = generate_thumbnail(src, dst)

    assert ok is True
    assert dst.exists()
    with Image.open(dst) as thumb:
        # Long edge should be capped near 240px
        assert max(thumb.size) <= 240
        assert thumb.size[0] == 160  # 2000/3000 * 240 = 160


def test_generate_thumbnail_handles_corrupt_image(tmp_path: Path) -> None:
    from gen_thumbs import generate_thumbnail

    src = tmp_path / "broken.jpg"
    src.write_bytes(b"not a real jpg")
    dst = tmp_path / "out.jpg"

    ok = generate_thumbnail(src, dst)

    assert ok is False
    assert not dst.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gen_thumbs.py::test_generate_thumbnail_creates_jpg -v`
Expected: FAIL with `ImportError: cannot import name 'generate_thumbnail'`.

- [ ] **Step 3: Implement `generate_thumbnail`**

Append to `src/gen_thumbs.py` (before any `if __name__ == "__main__":` block — there isn't one yet, just append):

```python
from PIL import Image  # noqa: E402 - module-level import for clarity

THUMBNAIL_LONG_EDGE = 240


def generate_thumbnail(src: Path, dst: Path, long_edge: int = THUMBNAIL_LONG_EDGE) -> bool:
    """Generate a thumbnail at `dst` with the long edge capped at `long_edge` px.

    Returns True on success, False if the source image cannot be decoded.
    """
    try:
        with Image.open(src) as img:
            img = img.convert("RGB")
            w, h = img.size
            scale = long_edge / max(w, h)
            if scale < 1.0:
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
            dst.parent.mkdir(parents=True, exist_ok=True)
            img.save(dst, "JPEG", quality=85)
        return True
    except Exception as exc:  # noqa: BLE001 - log and skip corrupt files
        print(f"[warn] skipped {src}: {exc}")
        return False
```

- [ ] **Step 4: Run all gen_thumbs tests**

Run: `pytest tests/test_gen_thumbs.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/gen_thumbs.py tests/test_gen_thumbs.py
git commit -m "feat: add thumbnail generation with corrupt-image handling"
```

---

## Task 4: Manifest Writer & CLI Entry Point

**Files:**
- Modify: `src/gen_thumbs.py`
- Modify: `tests/test_gen_thumbs.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_gen_thumbs.py`:

```python
def test_main_generates_thumbnails_and_manifest(
    sample_data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: running main() produces 4 thumbnails + manifest with 4 subsets."""
    import json

    import gen_thumbs

    outputs_dir = tmp_path / "outputs"

    # gen_thumbs.main uses argparse; we monkeypatch sys.argv
    monkeypatch.setattr(
        "sys.argv",
        [
            "gen_thumbs.py",
            "--data-dir",
            str(sample_data_dir),
            "--outputs-dir",
            str(outputs_dir),
        ],
    )
    gen_thumbs.main()

    manifest_path = outputs_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    assert "generated_at" in manifest
    assert set(manifest["subsets"].keys()) == {
        "train_long",
        "train_table",
        "eval_long",
        "eval_table",
    }
    # Each subset has 1 image in our fixture
    for key, subset in manifest["subsets"].items():
        assert subset["count"] == 1
        assert len(subset["images"]) == 1
        thumb_rel = subset["images"][0]["thumb_path"]
        assert (outputs_dir / "thumbs" / thumb_rel).exists()


def test_main_errors_when_data_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gen_thumbs

    outputs_dir = tmp_path / "outputs"
    monkeypatch.setattr(
        "sys.argv",
        ["gen_thumbs.py", "--data-dir", str(tmp_path / "does_not_exist"), "--outputs-dir", str(outputs_dir)],
    )
    with pytest.raises(SystemExit) as excinfo:
        gen_thumbs.main()
    # Non-zero exit code, and message printed to stdout
    assert excinfo.value.code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gen_thumbs.py::test_main_generates_thumbnails_and_manifest -v`
Expected: FAIL with `AttributeError: module 'gen_thumbs' has no attribute 'main'`.

- [ ] **Step 3: Implement `main()` and `write_manifest`**

Append to `src/gen_thumbs.py`:

```python
import json
import sys
from datetime import datetime


def write_manifest(outputs_dir: Path, subsets: dict[str, SubsetInfo]) -> Path:
    """Write the manifest JSON to outputs_dir/manifest.json and return its path."""
    manifest = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "subsets": subsets,
    }
    outputs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = outputs_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data",
        help="Path to the data/ directory (default: <project>/data)",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "outputs",
        help="Path to the outputs/ directory (default: <project>/outputs)",
    )
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"[error] data directory not found: {args.data_dir}", file=sys.stderr)
        sys.exit(2)

    subsets = discover_images(args.data_dir)
    total = sum(s["count"] for s in subsets.values())
    print(f"[info] discovered {total} images across {len(subsets)} subsets")

    thumbs_root = args.outputs_dir / "thumbs"
    for subset_key, subset in subsets.items():
        for img in subset["images"]:
            src = args.data_dir.parent / img["image_path"]
            dst = thumbs_root / subset_key / f"{img['uuid']}.jpg"
            generate_thumbnail(src, dst)

    manifest_path = write_manifest(args.outputs_dir, subsets)
    print(f"[info] wrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all gen_thumbs tests**

Run: `pytest tests/test_gen_thumbs.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/gen_thumbs.py tests/test_gen_thumbs.py
git commit -m "feat: add manifest writer and gen_thumbs CLI entry point"
```

---

## Task 5: Flask App Skeleton + `/api/manifest`

**Files:**
- Create: `src/app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_app.py`:

```python
"""Tests for src/app.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def app_client(sample_outputs_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a Flask test client wired to a temp outputs dir (with manifest).

    PROJECT_ROOT is set to the parent of `outputs/` so manifest `image_path`
    values (which are relative to project root) resolve correctly.
    """
    import app as app_module

    monkeypatch.setattr(app_module, "OUTPUTS_DIR", sample_outputs_dir)
    monkeypatch.setattr(app_module, "PROJECT_ROOT", sample_outputs_dir.parent)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_get_manifest_returns_json(app_client) -> None:
    resp = app_client.get("/api/manifest")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    data = resp.get_json()
    assert data["version"] == 1
    assert set(data["subsets"].keys()) == {
        "train_long",
        "train_table",
        "eval_long",
        "eval_table",
    }


def test_get_manifest_500_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app as app_module

    empty_outputs = tmp_path / "empty_outputs"
    empty_outputs.mkdir()
    monkeypatch.setattr(app_module, "OUTPUTS_DIR", empty_outputs)
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()

    resp = client.get("/api/manifest")
    assert resp.status_code == 500
    assert b"gen_thumbs" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: All FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Implement `src/app.py` with `/api/manifest` route**

Create `src/app.py`:

```python
"""Flask server for the AFAC image browser.

Usage:
    python src/app.py [--port PORT]
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

# Project root is parent of src/
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
STATIC_DIR: Path = Path(__file__).resolve().parent / "static"

app = Flask(__name__, static_folder=None)


def _load_manifest() -> dict:
    """Read and parse outputs/manifest.json, or raise FileNotFoundError."""
    manifest_path = OUTPUTS_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@app.route("/api/manifest")
def get_manifest() -> tuple:
    try:
        return jsonify(_load_manifest())
    except FileNotFoundError:
        return (
            jsonify(
                {
                    "error": "manifest not found",
                    "hint": "run `python src/gen_thumbs.py` first",
                }
            ),
            500,
        )


def find_port(start: int = 5000, end: int = 5010) -> int:
    """Return the first available port in [start, end]."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no available port in [{start}, {end}]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=None, help="Port (default: auto-pick 5000+)")
    args = parser.parse_args()
    port = args.port or find_port()
    print(f"[info] serving on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/app.py tests/test_app.py
git commit -m "feat: add Flask app with /api/manifest route and port picker"
```

---

## Task 6: `/thumb/<subset>/<uuid>` Route

**Files:**
- Modify: `src/app.py:46-50` (add new route after `get_manifest`)
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_app.py`:

```python
def test_get_thumb_returns_jpeg(app_client) -> None:
    resp = app_client.get("/thumb/train_long/aaaaaaaa-0000-0000-0000-000000000001.jpg")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_get_thumb_404_when_missing(app_client) -> None:
    resp = app_client.get("/thumb/train_long/does-not-exist.jpg")
    assert resp.status_code == 404


def test_get_thumb_404_on_unknown_subset(app_client) -> None:
    resp = app_client.get("/thumb/unknown_subset/anything.jpg")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -k thumb -v`
Expected: 3 FAIL with `404 NOT FOUND` (Flask's default for unknown routes).

- [ ] **Step 3: Add thumb route to `src/app.py`**

Insert this route immediately after `get_manifest`:

```python
@app.route("/thumb/<subset>/<path:filename>")
def get_thumb(subset: str, filename: str):
    # Block path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    subset_dir = OUTPUTS_DIR / "thumbs" / subset
    if not subset_dir.is_dir():
        abort(404)
    return send_from_directory(subset_dir, filename)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/app.py tests/test_app.py
git commit -m "feat: add /thumb/<subset>/<filename> route with traversal protection"
```

---

## Task 7: `/image/<subset>/<uuid>` Route

The frontend will look up the original file path in the manifest, then request it via `/image/<subset>/<uuid>`. The server reads the manifest to find the actual filesystem path.

**Files:**
- Modify: `src/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_app.py`:

```python
def test_get_image_returns_jpeg(app_client) -> None:
    resp = app_client.get("/image/train_long/aaaaaaaa-0000-0000-0000-000000000001")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_get_image_404_on_unknown_uuid(app_client) -> None:
    resp = app_client.get("/image/train_long/not-a-real-uuid")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -k image -v`
Expected: 2 FAIL (route not defined).

- [ ] **Step 3: Implement `/image/<subset>/<uuid>` route**

Add to `src/app.py`:

```python
def _find_image_path(subset: str, uuid: str) -> Path | None:
    """Look up the original image file path for (subset, uuid) in the manifest."""
    try:
        manifest = _load_manifest()
    except FileNotFoundError:
        return None
    subset_data = manifest.get("subsets", {}).get(subset)
    if not subset_data:
        return None
    for img in subset_data.get("images", []):
        if img["uuid"] == uuid:
            return PROJECT_ROOT / img["image_path"]
    return None


@app.route("/image/<subset>/<uuid>")
def get_image(subset: str, uuid: str):
    # Validate uuid format (basic)
    if "/" in uuid or "\\" in uuid or ".." in uuid:
        abort(404)
    img_path = _find_image_path(subset, uuid)
    if img_path is None or not img_path.is_file():
        abort(404)
    return send_from_directory(img_path.parent, img_path.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/app.py tests/test_app.py
git commit -m "feat: add /image/<subset>/<uuid> route with manifest lookup"
```

---

## Task 8: `/` Route Serving `index.html`

**Files:**
- Modify: `src/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_app.py`:

```python
def test_get_index_returns_html(app_client) -> None:
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert b"<div id=\"app\">" in resp.data


def test_get_static_asset(app_client) -> None:
    # app.js should be served at /static/app.js
    resp = app_client.get("/static/app.js")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py::test_get_index_returns_html -v`
Expected: FAIL with `404 NOT FOUND`.

- [ ] **Step 3: Implement `/` route and static serving**

Add to `src/app.py` (before `def main()`):

```python
@app.route("/")
def get_index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:filename>")
def get_static(filename: str):
    return send_from_directory(STATIC_DIR, filename)
```

- [ ] **Step 4: Create minimal placeholder static files so the routes can return 200**

Create `src/static/index.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AFAC Dataset Browser</title>
</head>
<body>
<div id="app">placeholder</div>
<script src="/static/app.js"></script>
</body>
</html>
```

Create `src/static/app.js`:

```javascript
// placeholder — populated in Task 10
console.log("app loaded");
```

Create empty `src/static/style.css`:

```bash
touch src/static/style.css
```

- [ ] **Step 5: Run all app tests**

Run: `pytest tests/test_app.py -v`
Expected: 9 PASSED.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: 16 PASSED (7 gen_thumbs + 9 app).

- [ ] **Step 7: Commit**

```bash
git add src/app.py src/static/ tests/test_app.py
git commit -m "feat: serve index.html and static assets via Flask"
```

---

## Task 9: Run `gen_thumbs.py` End-to-End Against Real Data

This task generates the real thumbnails and manifest that the browser will serve, and verifies the pipeline works on the actual dataset.

**Files:** No code changes — generates `outputs/` artifacts.

- [ ] **Step 1: Run `gen_thumbs.py` against the real `data/` directory**

Run: `python src/gen_thumbs.py`
Expected output:
```
[info] discovered 300 images across 4 subsets
[info] wrote manifest: .../outputs/manifest.json
```
Runtime: ~30 seconds (300 images × Pillow downsample).

- [ ] **Step 2: Verify thumbnail count matches image count per subset**

Run (PowerShell or bash equivalent):
```bash
ls outputs/thumbs/train_long/*.jpg | wc -l   # expect 100
ls outputs/thumbs/train_table/*.jpg | wc -l  # expect 100
ls outputs/thumbs/eval_long/*.jpg | wc -l    # expect 50
ls outputs/thumbs/eval_table/*.jpg | wc -l   # expect 50
```

- [ ] **Step 3: Spot-check manifest.json structure**

Run: `python -c "import json; m=json.load(open('outputs/manifest.json',encoding='utf-8')); print({k: v['count'] for k,v in m['subsets'].items()})"`
Expected: `{'train_long': 100, 'train_table': 100, 'eval_long': 50, 'eval_table': 50}`

- [ ] **Step 4: No commit needed** (outputs/ is gitignored).

---

## Task 10: HTML Skeleton & CSS Layout

Build the master-detail page shell: header tabs + left thumbnail sidebar + right main image area.

**Files:**
- Modify (replace placeholder): `src/static/index.html`
- Modify (replace placeholder): `src/static/style.css`

- [ ] **Step 1: Replace `src/static/index.html` with the full page skeleton**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AFAC 数据集浏览器</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div id="app">
  <header id="tabs-bar">
    <nav id="tabs"></nav>
    <div id="search-box">
      <input id="search-input" type="search" placeholder="按 UUID 搜索（当前标签内）" disabled>
    </div>
  </header>
  <main>
    <aside id="sidebar">
      <div id="sidebar-header"></div>
      <div id="thumbs"></div>
    </aside>
    <section id="viewer">
      <div id="toolbar">
        <span id="filename" class="mono">未选择</span>
        <span id="file-meta" class="meta"></span>
        <div class="spacer"></div>
        <button id="zoom-out" title="缩小">−</button>
        <span id="zoom-pct" class="mono">100%</span>
        <button id="zoom-in" title="放大">+</button>
        <button id="rotate" title="旋转 90°">⟲</button>
        <button id="fit" title="适配窗口">⤢</button>
      </div>
      <div id="canvas">
        <button id="prev" class="nav-arrow" title="上一张">‹</button>
        <img id="main-image" alt="" draggable="false">
        <button id="next" class="nav-arrow" title="下一张">›</button>
        <div id="error-overlay" hidden>
          <div class="error-content">
            <div class="error-icon">⚠</div>
            <div>加载失败，<a href="#" id="retry-link">点击重试</a></div>
          </div>
        </div>
      </div>
      <div id="statusbar">
        <span id="position-info">—</span>
        <span id="hint">← → 翻页 · 滚轮缩放 · 拖拽平移</span>
      </div>
    </section>
  </main>
</div>
<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Replace `src/static/style.css` with full styling**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { height: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 14px;
  color: #222;
  background: #fff;
  overflow: hidden;
}
.mono { font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }

#app { display: flex; flex-direction: column; }

/* Header / tabs */
#tabs-bar {
  height: 48px;
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid #ddd;
  background: #fafafa;
  padding: 0 12px;
}
#tabs { display: flex; align-items: stretch; }
.tab {
  display: flex; align-items: center;
  padding: 0 16px;
  cursor: pointer;
  color: #666;
  border-bottom: 2px solid transparent;
  font-size: 13px;
  user-select: none;
}
.tab.active {
  color: #4a90e2;
  border-bottom-color: #4a90e2;
  font-weight: 600;
}
.tab .count {
  background: #eee;
  color: #666;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 11px;
  margin-left: 6px;
}
.tab.active .count {
  background: #e8eef7;
  color: #4a90e2;
}
#search-box {
  margin-left: auto;
  display: flex;
  align-items: center;
}
#search-input {
  font-size: 12px;
  padding: 6px 10px;
  width: 200px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

/* Main layout */
main { flex: 1; display: flex; min-height: 0; }

/* Sidebar */
#sidebar {
  width: 260px;
  border-right: 1px solid #ddd;
  background: #f7f7f7;
  overflow-y: auto;
  padding: 8px;
}
#sidebar-header {
  font-size: 11px; color: #888;
  padding: 4px 4px 8px;
}
#thumbs {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}
.thumb {
  cursor: pointer;
}
.thumb img {
  width: 100%;
  aspect-ratio: 3/4;
  object-fit: cover;
  display: block;
  border: 3px solid transparent;
  border-radius: 2px;
  background: #ddd;
}
.thumb.active img { border-color: #4a90e2; }
.thumb .uuid {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  color: #555;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Viewer */
#viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
#toolbar {
  height: 36px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
  font-size: 12px;
}
#filename { font-size: 12px; }
.meta { color: #888; }
.spacer { flex: 1; }
#toolbar button {
  padding: 4px 8px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}
#toolbar button:hover { background: #f0f0f0; }
#zoom-pct { min-width: 48px; text-align: center; }

#canvas {
  flex: 1;
  background: #2a2a2a;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
#main-image {
  max-width: 100%;
  max-height: 100%;
  user-select: none;
  transition: transform 0.05s ease-out;
  transform-origin: center center;
}
#main-image.grabbing { cursor: grabbing; }
#main-image.grabbable { cursor: grab; }

.nav-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255,255,255,0.15);
  color: #fff;
  border: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
}
.nav-arrow:hover { background: rgba(255,255,255,0.25); }
#prev { left: 12px; }
#next { right: 12px; }

#error-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3;
}
.error-content { text-align: center; }
.error-icon { font-size: 36px; margin-bottom: 8px; }
#error-overlay a { color: #4a90e2; cursor: pointer; }

#statusbar {
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-top: 1px solid #eee;
  background: #fafafa;
  font-size: 11px;
  color: #888;
}
```

- [ ] **Step 3: Verify in browser**

Run: `python src/app.py`
Open: http://127.0.0.1:5000
Expected: Page renders with empty tabs, sidebar header, toolbar, dark canvas, status bar. Browser console shows "app loaded" (from placeholder app.js). No errors in console.

- [ ] **Step 4: Commit**

```bash
git add src/static/index.html src/static/style.css
git commit -m "feat: build page shell with master-detail layout"
```

---

## Task 11: Frontend — Load Manifest & Render Tabs

**Files:**
- Modify (replace placeholder): `src/static/app.js`

- [ ] **Step 1: Replace `src/static/app.js` with manifest-loading + tab rendering**

```javascript
// AFAC image browser frontend.
// State is held in module-level consts; we re-render the sidebar on tab change.

const state = {
  manifest: null,            // full manifest from /api/manifest
  currentSubset: null,       // subset key like "train_long"
  currentImages: [],         // filtered list (after search)
  currentIndex: -1,          // index into currentImages (-1 = none selected)
  searchQuery: "",
};

// DOM references
const $tabs = document.getElementById("tabs");
const $sidebarHeader = document.getElementById("sidebar-header");
const $thumbs = document.getElementById("thumbs");
const $searchInput = document.getElementById("search-input");
const $filename = document.getElementById("filename");
const $fileMeta = document.getElementById("file-meta");
const $mainImage = document.getElementById("main-image");
const $positionInfo = document.getElementById("position-info");
const $errorOverlay = document.getElementById("error-overlay");

async function loadManifest() {
  const resp = await fetch("/api/manifest");
  if (!resp.ok) {
    document.getElementById("app").innerHTML =
      '<div style="padding:40px;text-align:center">无法加载 manifest。请先运行 <code>python src/gen_thumbs.py</code>。</div>';
    return;
  }
  state.manifest = await resp.json();
  $searchInput.disabled = false;
  renderTabs();
  selectSubset(Object.keys(state.manifest.subsets)[0]);
}

function renderTabs() {
  $tabs.innerHTML = "";
  for (const [key, subset] of Object.entries(state.manifest.subsets)) {
    const tab = document.createElement("div");
    tab.className = "tab";
    tab.dataset.subset = key;
    if (key === state.currentSubset) tab.classList.add("active");
    tab.innerHTML = `${subset.label}<span class="count">${subset.count}</span>`;
    tab.addEventListener("click", () => selectSubset(key));
    $tabs.appendChild(tab);
  }
}

function selectSubset(key) {
  state.currentSubset = key;
  state.currentIndex = -1;
  state.searchQuery = "";
  $searchInput.value = "";
  renderTabs();
  renderSidebar();
  // Auto-select first image
  if (state.currentImages.length > 0) {
    showImage(0);
  } else {
    clearViewer();
  }
}

function getCurrentImageList() {
  if (!state.currentSubset) return [];
  const subset = state.manifest.subsets[state.currentSubset];
  if (!state.searchQuery) return subset.images;
  const q = state.searchQuery.toLowerCase();
  return subset.images.filter((img) => img.uuid.toLowerCase().includes(q));
}

function renderSidebar() {
  const subset = state.manifest.subsets[state.currentSubset];
  state.currentImages = getCurrentImageList();
  $sidebarHeader.textContent = `${subset.label} · ${state.currentImages.length} 张`;
  $thumbs.innerHTML = "";
  for (let i = 0; i < state.currentImages.length; i++) {
    const img = state.currentImages[i];
    const div = document.createElement("div");
    div.className = "thumb";
    if (i === state.currentIndex) div.classList.add("active");
    div.innerHTML = `
      <img loading="lazy" src="/thumb/${state.currentSubset}/${img.uuid}.jpg" alt="">
      <div class="uuid">${img.uuid.slice(0, 12)}…</div>
    `;
    div.addEventListener("click", () => showImage(i));
    $thumbs.appendChild(div);
  }
}

function showImage(index) {
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
  // Load image (zoom/pan reset happens via the load listener installed in Task 12)
  $errorOverlay.hidden = true;
  $mainImage.style.display = "";
  $mainImage.onerror = () => {
    $mainImage.style.display = "none";
    $errorOverlay.hidden = false;
  };
  $mainImage.src = `/image/${state.currentSubset}/${img.uuid}`;
}

function clearViewer() {
  state.currentIndex = -1;
  $filename.textContent = "未选择";
  $fileMeta.textContent = "";
  $positionInfo.textContent = "—";
  $mainImage.removeAttribute("src");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Wire up search input
$searchInput.addEventListener("input", (e) => {
  state.searchQuery = e.target.value;
  renderSidebar();
  if (state.currentImages.length > 0) {
    showImage(0);
  } else {
    clearViewer();
  }
});

// Boot
loadManifest().catch((err) => console.error("boot failed:", err));
```

- [ ] **Step 2: Verify in browser**

Refresh http://127.0.0.1:5000
Expected:
- 4 tabs render with subset labels and counts (100/100/50/50)
- First tab (训练长文档) is active
- Sidebar shows thumbnail grid (lazy-loaded)
- Search input is enabled
- Clicking a thumbnail loads the full image on the right
- Filename (UUID.jpg) and file size appear in the toolbar
- Status bar shows position and subset label
- Typing in search filters thumbnails live

- [ ] **Step 3: Commit**

```bash
git add src/static/app.js
git commit -m "feat: frontend loads manifest, renders tabs and sidebar"
```

---

## Task 12: Frontend — Zoom, Pan, Rotate, Keyboard Navigation

**Files:**
- Modify: `src/static/app.js`

- [ ] **Step 1: Add zoom/pan/rotate/keyboard logic to `app.js`**

Append to `src/static/app.js` (before the `// Boot` comment):

```javascript
// === Zoom / Pan / Rotate ===
const zoomState = {
  scale: 1,        // 1 = fit-to-window (we treat as 100%)
  rotation: 0,     // degrees, 0/90/180/270
  offsetX: 0,
  offsetY: 0,
  // Track natural image dimensions for fit calculation
  naturalW: 0,
  naturalH: 0,
  // Track the "fit" scale so we can compute actual pixel scale for display
  fitScale: 1,
};

const MIN_SCALE = 0.1;
const MAX_SCALE = 4.0;
const $zoomPct = document.getElementById("zoom-pct");
const $btnZoomIn = document.getElementById("zoom-in");
const $btnZoomOut = document.getElementById("zoom-out");
const $btnRotate = document.getElementById("rotate");
const $btnFit = document.getElementById("fit");
const $btnPrev = document.getElementById("prev");
const $btnNext = document.getElementById("next");

$mainImage.addEventListener("load", () => {
  zoomState.naturalW = $mainImage.naturalWidth;
  zoomState.naturalH = $mainImage.naturalHeight;
  resetView();
});

function resetView() {
  zoomState.scale = 1;
  zoomState.rotation = 0;
  zoomState.offsetX = 0;
  zoomState.offsetY = 0;
  applyTransform();
}

function computeFitScale() {
  // The displayed image (without zoom) already fits the canvas via CSS max-width/height.
  // We treat scale=1 as "fit". Display percentage reflects zoomState.scale directly.
  return zoomState.scale;
}

function setScale(newScale) {
  zoomState.scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
  applyTransform();
}

function applyTransform() {
  $mainImage.style.transform =
    `translate(${zoomState.offsetX}px, ${zoomState.offsetY}px) ` +
    `scale(${zoomState.scale}) rotate(${zoomState.rotation}deg)`;
  $zoomPct.textContent = `${Math.round(zoomState.scale * 100)}%`;
  // Cursor logic
  if (zoomState.scale > 1) {
    $mainImage.classList.add("grabbable");
    $mainImage.classList.remove("grabbing");
  } else {
    $mainImage.classList.remove("grabbable", "grabbing");
    zoomState.offsetX = 0;
    zoomState.offsetY = 0;
    $mainImage.style.transform =
      `scale(${zoomState.scale}) rotate(${zoomState.rotation}deg)`;
  }
}

$btnZoomIn.addEventListener("click", () => setScale(zoomState.scale + 0.1));
$btnZoomOut.addEventListener("click", () => setScale(zoomState.scale - 0.1));
$btnFit.addEventListener("click", resetView);
$btnRotate.addEventListener("click", () => {
  zoomState.rotation = (zoomState.rotation + 90) % 360;
  applyTransform();
});

// Wheel zoom (cursor-centric)
document.getElementById("canvas").addEventListener(
  "wheel",
  (e) => {
    if (state.currentIndex < 0) return;
    e.preventDefault();
    const delta = -Math.sign(e.deltaY) * 0.1;
    setScale(zoomState.scale + delta);
  },
  { passive: false }
);

// Drag pan
let dragState = null;
$mainImage.addEventListener("mousedown", (e) => {
  if (zoomState.scale <= 1) return;
  dragState = {
    startX: e.clientX,
    startY: e.clientY,
    origX: zoomState.offsetX,
    origY: zoomState.offsetY,
  };
  $mainImage.classList.add("grabbing");
  e.preventDefault();
});
window.addEventListener("mousemove", (e) => {
  if (!dragState) return;
  zoomState.offsetX = dragState.origX + (e.clientX - dragState.startX);
  zoomState.offsetY = dragState.origY + (e.clientY - dragState.startY);
  applyTransform();
});
window.addEventListener("mouseup", () => {
  if (dragState) {
    dragState = null;
    $mainImage.classList.remove("grabbing");
  }
});

// === Navigation ===
function gotoOffset(delta) {
  if (state.currentImages.length === 0) return;
  // Wrap around
  const n = state.currentImages.length;
  const newIndex = (state.currentIndex + delta + n) % n;
  showImage(newIndex);
}
$btnPrev.addEventListener("click", () => gotoOffset(-1));
$btnNext.addEventListener("click", () => gotoOffset(1));

window.addEventListener("keydown", (e) => {
  // Don't hijack typing in the search box
  if (document.activeElement === $searchInput) return;
  if (e.key === "ArrowLeft") gotoOffset(-1);
  else if (e.key === "ArrowRight") gotoOffset(1);
});

// Reset zoom/pan whenever a new image finishes loading.
// (Installed above via `$mainImage.addEventListener("load", ...)` which calls
// resetView(). The load listener also fires for cached images, so this covers
// both fresh loads and quick navigation between already-seen images.)
```

- [ ] **Step 2: Verify in browser**

Refresh http://127.0.0.1:5000
Acceptance checks:
- Click image → loads. Toolbar zoom reads 100%.
- Click `+` → zoom increases by 10%. Cursor becomes grab.
- Click and drag on zoomed image → pans.
- Click `−` → zoom decreases. At 100% cursor returns to default.
- Click ⟲ → image rotates 90° (subsequent clicks: 180/270/0).
- Click ⤢ → resets to 100%, no rotation, no offset.
- Scroll wheel over canvas → zoom in/out (10% steps).
- Click ‹ → previous image. Click › → next image.
- Press ← / → → same as prev/next.
- Focus search input, ←→ keys should NOT navigate (they type into search).

- [ ] **Step 3: Commit**

```bash
git add src/static/app.js
git commit -m "feat: add zoom, pan, rotate, keyboard navigation"
```

---

## Task 13: Manual Acceptance Checklist + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run the full pipeline once more, clean**

```bash
rm -rf outputs/thumbs outputs/manifest.json
python src/gen_thumbs.py
python src/app.py
```

- [ ] **Step 2: Walk the manual acceptance checklist in the browser**

Open http://127.0.0.1:5000 and verify each item:

- [ ] 4 tabs render with correct counts: 100 / 100 / 50 / 50
- [ ] Click each tab; sidebar updates with that subset's thumbnails
- [ ] Click any thumbnail; main image loads on the right
- [ ] Toolbar shows `UUID.jpg` filename + size in MB
- [ ] Status bar shows `第 N / M 张 · <subset label>`
- [ ] `+` / `−` buttons zoom in 10% steps
- [ ] Scroll wheel zooms; cursor becomes grab when zoomed > 100%
- [ ] Drag the zoomed image to pan
- [ ] ⟲ button rotates 90° per click
- [ ] ⤢ button resets zoom/rotation/offset
- [ ] ‹ › buttons + ← → keys navigate within subset (wraps around)
- [ ] Search box filters current subset by UUID (case-insensitive substring)
- [ ] Browser DevTools console shows no errors
- [ ] Network panel shows thumbnails served from `/thumb/...` and main images from `/image/...`

- [ ] **Step 3: Write `README.md`**

Create `README.md` (replace existing one-line content):

```markdown
# Complex-financial-document-restoration

AFAC 金融文档还原挑战赛 — 数据集图片浏览器。

## 快速开始

```bash
# 1. 安装依赖（首次）
pip install -r requirements.txt

# 2. 生成缩略图与 manifest（首次或 data/ 变化后重跑）
python src/gen_thumbs.py

# 3. 启动浏览器
python src/app.py
```

打开终端中打印的 URL（默认 http://127.0.0.1:5000）。

## 使用

- **顶部标签**：切换 4 个子集（训练长文档 / 训练表格 / 评测长文档 / 评测表格）
- **左侧列表**：点击缩略图查看大图
- **大图区**：
  - 滚轮 / `+` `−` 缩放（10%–400%）
  - 拖拽平移（缩放 > 100% 时）
  - ⟲ 旋转 90° · ⤢ 适配窗口
  - ← → 键或 ‹ › 翻页
- **搜索框**：在当前子集内按 UUID 模糊过滤

## 目录结构

```
data/                 # 原始数据（只读）
src/
  gen_thumbs.py       # 缩略图 + manifest 生成脚本
  app.py              # Flask 服务
  static/             # HTML / CSS / JS
outputs/
  thumbs/             # 预生成缩略图（gitignored）
  manifest.json       # 图片清单（gitignored）
```

## 测试

```bash
pytest tests/ -v
```

## 设计文档

- 规格：`docs/superpowers/specs/2026-06-25-image-gallery-design.md`
- 实现计划：`docs/superpowers/plans/2026-06-25-image-gallery.md`
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: write README with usage and architecture"
```

---

## Self-Review Checklist (run by you, the engineer, after the last task)

- [ ] All tests pass: `pytest tests/ -v` (16 tests)
- [ ] Full pipeline works: `gen_thumbs.py` → `app.py` → browser
- [ ] Manual acceptance checklist in Task 13 fully green
- [ ] No `TODO` / `TBD` / `FIXME` left in code
- [ ] `.gitignore` includes `outputs/thumbs/`, `outputs/manifest.json`, `.superpowers/`
- [ ] No large binary files accidentally committed (run `git ls-files | xargs ls -la | sort -k5 -n | tail -5`)
