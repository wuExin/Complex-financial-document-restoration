# 长条图切片实施计划（Phase 3）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement page-level chunking for tall stitched multi-page strips (aspect 1:25+) so each FinixDoc-VL API call gets a normal-sized image, plus fix the two pre-existing client bugs that would have made chunking a no-op (using `chunk.source.path` for upload; cache key colliding across chunks of the same source).

**Architecture:** `chunker.py` gains an aspect-threshold gate; strips go through white-band page detection with fixed-height fallback, then materialize JPEGs to `.cache/chunks/` via a new `chunk_storage` module. `FinixDocVLClient` switches to `chunk.path`/`chunk.file_name` and a chunk-aware cache key; `MockVLClient` looks up per-chunk GT first. CLI gains 4 tunable flags.

**Tech Stack:** Python 3.10+, Pillow (PIL) for image processing, `unittest` + `MagicMock`, `requests` (already installed), `tempfile.TemporaryDirectory` for test isolation.

**Spec:** `docs/superpowers/specs/2026-06-18-long-strip-chunking-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add `pillow>=10.0.0` |
| `src/document_restoration/models.py` | Modify | Add `file_name: str` field to `ImageChunk` |
| `src/document_restoration/chunker.py` | Modify | Aspect gate, `_detect_cut_points`, `_materialize_chunks`, `_split_strip`, `ChunkerConfig` |
| `src/document_restoration/chunk_storage.py` | Create | `file_exists`, `write_jpeg`, `clear` — pure file I/O |
| `src/document_restoration/vl_client.py` | Modify | `FinixDocVLClient`: use chunk.path/file_name, new cache key, `min_request_interval`. `MockVLClient`: per-chunk GT lookup |
| `src/document_restoration/pipeline.py` | Modify | Accept `ChunkerConfig`, pass to `create_chunks` |
| `main.py` | Modify | Add 4 CLI flags, build `ChunkerConfig`, pass to `run_pipeline` |
| `tests/test_chunk_storage.py` | Create | `chunk_storage` unit tests |
| `tests/test_chunker.py` | Create | Chunker unit tests (config, aspect gate, cut-point detection, materialization) |
| `tests/test_finixdoc_client.py` | Modify | Add tests for chunk.path/file_name usage, new cache key, min_request_interval |
| `tests/test_mvp_pipeline.py` | Modify | Add ChunkerConfig-through-pipeline test, mock-GT per-chunk test |

---

### Task 1: Add pillow dependency and `file_name` field to `ImageChunk`

**Files:**
- Modify: `requirements.txt`
- Modify: `src/document_restoration/models.py`
- Modify: `src/document_restoration/chunker.py`
- Test: `tests/test_mvp_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mvp_pipeline.py` inside the `ChunkerTests` class:

```python
    def test_create_chunks_sets_file_name_equal_to_source_for_mvp(self):
        image = ImageRecord(file_name="doc.jpg", path=Path("doc.jpg").resolve())

        chunks = create_chunks(image)

        self.assertEqual(chunks[0].file_name, "doc.jpg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mvp_pipeline.ChunkerTests.test_create_chunks_sets_file_name_equal_to_source_for_mvp -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'file_name'` or `AttributeError`.

- [ ] **Step 3: Add pillow to requirements**

Replace `requirements.txt` contents with:

```
requests>=2.31.0
pillow>=10.0.0
```

Then run: `pip install -r requirements.txt`
Expected: `Successfully installed pillow-...` (or `already satisfied`).

- [ ] **Step 4: Add `file_name` field to `ImageChunk`**

In `src/document_restoration/models.py`, replace the `ImageChunk` dataclass:

```python
@dataclass(frozen=True)
class ImageChunk:
    source: ImageRecord
    chunk_id: int
    path: Path
    file_name: str
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
```

- [ ] **Step 5: Update chunker constructor**

Replace `src/document_restoration/chunker.py` contents:

```python
from .models import ImageChunk, ImageRecord


def create_chunks(image: ImageRecord) -> list[ImageChunk]:
    return [
        ImageChunk(
            source=image,
            chunk_id=0,
            path=image.path,
            file_name=image.file_name,
            x=0,
            y=0,
            width=None,
            height=None,
        )
    ]
```

- [ ] **Step 6: Run the full test suite**

Run: `python -m unittest discover -s tests -v`
Expected: All existing tests pass (55+ tests).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/document_restoration/models.py src/document_restoration/chunker.py tests/test_mvp_pipeline.py
git commit -m "feat: add pillow dep and file_name field to ImageChunk"
```

---

### Task 2: Create `chunk_storage` module

**Files:**
- Create: `src/document_restoration/chunk_storage.py`
- Test: `tests/test_chunk_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chunk_storage.py`:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from src.document_restoration.chunk_storage import clear, file_exists, write_jpeg


def _make_rgb(width: int, height: int, color=(128, 128, 128)) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


class FileExistsTests(unittest.TestCase):
    def test_returns_false_for_missing_path(self):
        with TemporaryDirectory() as tmp:
            self.assertFalse(file_exists(Path(tmp) / "missing.jpg"))

    def test_returns_false_for_empty_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jpg"
            path.write_bytes(b"")
            self.assertFalse(file_exists(path))

    def test_returns_true_for_non_empty_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "img.jpg"
            write_jpeg(path, _make_rgb(10, 10))
            self.assertTrue(file_exists(path))


class WriteJpegTests(unittest.TestCase):
    def test_writes_loadable_jpeg_with_default_quality(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jpg"
            write_jpeg(path, _make_rgb(50, 30, color=(200, 100, 50)))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)
            with Image.open(path) as im:
                self.assertEqual(im.size, (50, 30))
                self.assertEqual(im.format, "JPEG")

    def test_creates_parent_directory_if_missing(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "deep" / "out.jpg"
            write_jpeg(path, _make_rgb(10, 10))
            self.assertTrue(path.exists())

    def test_does_not_overwrite_existing_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jpg"
            write_jpeg(path, _make_rgb(10, 10, color=(255, 0, 0)))
            first_size = path.stat().st_size
            first_bytes = path.read_bytes()

            write_jpeg(path, _make_rgb(10, 10, color=(0, 255, 0)))

            self.assertEqual(path.stat().st_size, first_size)
            self.assertEqual(path.read_bytes(), first_bytes)


class ClearTests(unittest.TestCase):
    def test_removes_all_chunks_for_stem(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            for nn in ("01", "02", "03"):
                p = cache_dir / f"doc_p{nn}.jpg"
                write_jpeg(p, _make_rgb(10, 10))
            other = cache_dir / "other_p01.jpg"
            write_jpeg(other, _make_rgb(10, 10))

            clear("doc", cache_dir)

            remaining = sorted(p.name for p in cache_dir.iterdir())
            self.assertEqual(remaining, ["other_p01.jpg"])

    def test_silent_when_no_matching_files(self):
        with TemporaryDirectory() as tmp:
            clear("never_existed", Path(tmp))  # should not raise


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_chunk_storage -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.document_restoration.chunk_storage'`.

- [ ] **Step 3: Implement `chunk_storage.py`**

Create `src/document_restoration/chunk_storage.py`:

```python
"""File I/O for chunked images. Knows nothing about cut points or ImageChunk metadata."""

import logging
from pathlib import Path

from PIL import Image


LOGGER = logging.getLogger(__name__)


def file_exists(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def write_jpeg(path: Path, pil_image: Image.Image, quality: int = 90) -> None:
    if file_exists(path):
        LOGGER.info("Skipping write; chunk already cached at %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pil_image.convert("RGB").save(path, format="JPEG", quality=quality)


def clear(source_stem: str, cache_dir: Path) -> None:
    for entry in cache_dir.iterdir():
        if entry.is_file() and entry.name.startswith(f"{source_stem}_p") and entry.suffix == ".jpg":
            try:
                entry.unlink()
            except OSError:
                LOGGER.warning("Failed to remove %s", entry, exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_chunk_storage -v`
Expected: 7 tests pass.

- [ ] **Step 5: Run full suite**

Run: `python -m unittest discover -s tests`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/chunk_storage.py tests/test_chunk_storage.py
git commit -m "feat: add chunk_storage module for cached chunk file I/O"
```

---

### Task 3: Add `ChunkerConfig` and `_detect_cut_points`

**Files:**
- Modify: `src/document_restoration/chunker.py`
- Test: `tests/test_chunker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chunker.py`:

```python
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from src.document_restoration.chunker import ChunkerConfig, _detect_cut_points
from src.document_restoration.models import ImageRecord


def _make_strip(width: int, page_height: int, num_pages: int, gap_height: int = 30) -> Image.Image:
    """A tall strip of `num_pages` grey pages separated by white gaps."""
    total_h = num_pages * page_height + (num_pages - 1) * gap_height
    img = Image.new("RGB", (width, total_h), color="white")
    draw = ImageDraw.Draw(img)
    for i in range(num_pages):
        y0 = i * (page_height + gap_height)
        draw.rectangle([0, y0, width - 1, y0 + page_height - 1], fill=(128, 128, 128))
    return img


def _make_uniform_strip(width: int, height: int) -> Image.Image:
    """A tall strip with no white gaps (forces fixed-height fallback)."""
    return Image.new("RGB", (width, height), color=(100, 100, 100))


class DetectCutPointsTests(unittest.TestCase):
    def test_three_pages_with_clear_gaps_cut_at_gap_midpoints(self):
        width, page_h, gap = 200, 600, 60
        img = _make_strip(width, page_h, 3, gap_height=gap)
        config = ChunkerConfig()

        cuts = _detect_cut_points(img, config)

        self.assertEqual(len(cuts), 3)
        for y0, y1 in cuts:
            self.assertGreater(y1, y0)
        # First chunk starts at 0, last chunk ends at image bottom
        self.assertEqual(cuts[0][0], 0)
        self.assertEqual(cuts[-1][1], img.size[1])
        # Internal boundaries should fall inside the gaps (y between pages)
        gap1_mid = page_h + gap // 2
        self.assertLess(cuts[0][1], page_h + gap)
        self.assertGreater(cuts[0][1], page_h)

    def test_uniform_strip_falls_back_to_fixed_height(self):
        width = 200
        # Width 200 -> expected_page_h = round(200 * 1.414) = 283
        # height = 4 pages * 283 - overlap=10% => step ~255; ceil(4*283 / 255) ~ 5 chunks
        img = _make_uniform_strip(width, height=1000)
        config = ChunkerConfig()

        cuts = _detect_cut_points(img, config)

        self.assertGreater(len(cuts), 1)
        # Each cut's height should be roughly expected_page_h (allow overlap slack)
        expected_h = round(width * config.page_height_ratio)
        for y0, y1 in cuts[:-1]:  # ignore last (may be shorter)
            self.assertAlmostEqual(y1 - y0, expected_h, delta=expected_h * 0.2)

    def test_single_page_strip_returns_one_chunk(self):
        img = _make_strip(200, 600, 1)
        config = ChunkerConfig()

        cuts = _detect_cut_points(img, config)

        self.assertEqual(cuts, [(0, img.size[1])])

    def test_respects_custom_page_height_ratio(self):
        # With a huge ratio, expected_page_h becomes larger than the image → single chunk
        img = _make_strip(200, 600, 3, gap_height=60)
        config = ChunkerConfig(page_height_ratio=10.0)

        cuts = _detect_cut_points(img, config)

        self.assertEqual(cuts, [(0, img.size[1])])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_chunker -v`
Expected: FAIL with `ImportError: cannot import name 'ChunkerConfig' from 'src.document_restoration.chunker'`.

- [ ] **Step 3: Implement `ChunkerConfig` and `_detect_cut_points`**

Replace `src/document_restoration/chunker.py` contents:

```python
from dataclasses import dataclass

from PIL import Image

from .models import ImageChunk, ImageRecord


STRIP_ASPECT_THRESHOLD = 3.0
PAGE_HEIGHT_RATIO = 1.414  # sqrt(2), A4 portrait
WHITE_ROW_THRESHOLD = 248  # 0..255 grayscale mean
MIN_BAND_RATIO = 0.3       # band >= 30% of expected page height
DOWNSCALE_WIDTH = 200      # for row-brightness analysis
MAX_CHUNKS_PER_IMAGE = 100


@dataclass(frozen=True)
class ChunkerConfig:
    strip_aspect_threshold: float = STRIP_ASPECT_THRESHOLD
    page_height_ratio: float = PAGE_HEIGHT_RATIO
    chunk_cache_dir: "Path | None" = None  # resolved by pipeline; chunker treats None as "no cache"


def create_chunks(image: ImageRecord) -> list[ImageChunk]:
    return [
        ImageChunk(
            source=image,
            chunk_id=0,
            path=image.path,
            file_name=image.file_name,
            x=0,
            y=0,
            width=None,
            height=None,
        )
    ]


def _detect_cut_points(image: Image.Image, config: ChunkerConfig) -> list[tuple[int, int]]:
    width, height = image.size
    expected_page_h = max(1, round(width * config.page_height_ratio))
    if height <= expected_page_h:
        return [(0, height)]

    bands = _find_white_bands(image, expected_page_h)
    if _bands_look_like_page_separators(bands, height, expected_page_h):
        return _cuts_from_bands(bands, height)

    return _fixed_height_cuts(height, expected_page_h)


def _find_white_bands(image: Image.Image, expected_page_h: int) -> list[tuple[int, int]]:
    width, height = image.size
    new_w = DOWNSCALE_WIDTH
    new_h = max(1, round(height * new_w / width))
    small = image.convert("L").resize((new_w, new_h), Image.BILINEAR)
    pixels = list(small.getdata())  # row-major
    row_mean = [sum(pixels[r * new_w:(r + 1) * new_w]) / new_w for r in range(new_h)]

    min_band_downscaled = max(1, round(expected_page_h * new_w / width * MIN_BAND_RATIO))
    bands: list[tuple[int, int]] = []
    i = 0
    while i < new_h:
        if row_mean[i] >= WHITE_ROW_THRESHOLD:
            j = i
            while j < new_h and row_mean[j] >= WHITE_ROW_THRESHOLD:
                j += 1
            if j - i >= min_band_downscaled:
                # Map back to original-y coordinates
                y0 = round(i * height / new_h)
                y1 = round(j * height / new_h)
                bands.append((y0, y1))
            i = j
        else:
            i += 1
    return bands


def _bands_look_like_page_separators(
    bands: list[tuple[int, int]], height: int, expected_page_h: int
) -> bool:
    if len(bands) < 2:
        return False
    # Internal band-to-band distances
    mids = [(b0 + b1) // 2 for b0, b1 in bands]
    distances = [mids[i + 1] - mids[i] for i in range(len(mids) - 1)]
    return all(expected_page_h * 0.5 <= d <= expected_page_h * 2.0 for d in distances)


def _cuts_from_bands(bands: list[tuple[int, int]], height: int) -> list[tuple[int, int]]:
    # Use each band's midpoint as a cut boundary, plus image top and bottom
    boundaries = [0] + [(b0 + b1) // 2 for b0, b1 in bands] + [height]
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def _fixed_height_cuts(height: int, expected_page_h: int) -> list[tuple[int, int]]:
    step = max(1, round(expected_page_h * 0.9))
    if height <= step:
        return [(0, height)]
    cuts: list[tuple[int, int]] = []
    y = 0
    while y < height:
        y1 = min(y + expected_page_h, height)
        cuts.append((y, y1))
        if y1 == height:
            break
        y += step
    return cuts[:MAX_CHUNKS_PER_IMAGE]
```

Also add this import at the top of the file:

```python
from pathlib import Path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_chunker -v`
Expected: 4 tests pass.

- [ ] **Step 5: Run full suite**

Run: `python -m unittest discover -s tests`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/chunker.py tests/test_chunker.py
git commit -m "feat: detect cut points for long-strip chunking"
```

---

### Task 4: Implement `_materialize_chunks` and integrate `_split_strip`

**Files:**
- Modify: `src/document_restoration/chunker.py`
- Test: `tests/test_chunker.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chunker.py` (add imports first; add `create_chunks` to the existing import line):

```python
from src.document_restoration.chunker import (
    ChunkerConfig,
    _detect_cut_points,
    create_chunks,
)
from src.document_restoration.models import ImageRecord
```

Add this test class:

```python
class CreateChunksIntegrationTests(unittest.TestCase):
    def _save_image_record(self, tmp: str, name: str, img: Image.Image) -> ImageRecord:
        path = Path(tmp) / name
        img.save(path, format="JPEG")
        return ImageRecord(file_name=name, path=path)

    def test_short_image_returns_single_chunk_pointing_at_source(self):
        with TemporaryDirectory() as tmp:
            img = Image.new("RGB", (400, 300), color=(50, 50, 50))
            record = self._save_image_record(tmp, "page.jpg", img)
            config = ChunkerConfig()

            chunks = create_chunks(record, config)

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].path, record.path)
            self.assertEqual(chunks[0].file_name, "page.jpg")
            self.assertIsNone(chunks[0].width)

    def test_tall_image_splits_and_writes_chunk_files(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "chunks"
            strip = _make_strip(400, page_height=600, num_pages=3, gap_height=80)
            record = self._save_image_record(tmp, "tall.jpg", strip)
            config = ChunkerConfig(chunk_cache_dir=cache_dir)

            chunks = create_chunks(record, config)

            self.assertEqual(len(chunks), 3)
            for idx, chunk in enumerate(chunks):
                self.assertEqual(chunk.chunk_id, idx)
                self.assertEqual(chunk.source, record)
                self.assertTrue(chunk.path.exists(), f"chunk file missing: {chunk.path}")
                self.assertTrue(chunk.path.name.startswith("tall_p"))
                self.assertTrue(chunk.path.name.endswith(".jpg"))
                self.assertIsNotNone(chunk.x)
                self.assertIsNotNone(chunk.y)
                self.assertIsNotNone(chunk.width)
                self.assertIsNotNone(chunk.height)
                with Image.open(chunk.path) as im:
                    self.assertEqual(im.size, (chunk.width, chunk.height))

    def test_reuses_cached_chunks_without_rewriting(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "chunks"
            strip = _make_strip(400, page_height=600, num_pages=2, gap_height=80)
            record = self._save_image_record(tmp, "tall.jpg", strip)
            config = ChunkerConfig(chunk_cache_dir=cache_dir)

            first_chunks = create_chunks(record, config)
            first_sizes = {c.path: c.path.stat().st_size for c in first_chunks}
            # Tamper with mtime to detect rewrite
            import os
            for path in first_sizes:
                os.utime(path, (1_000_000_000, 1_000_000_000))

            second_chunks = create_chunks(record, config)

            self.assertEqual(
                [c.path for c in first_chunks], [c.path for c in second_chunks]
            )
            for path in first_sizes:
                self.assertEqual(path.stat().st_mtime, 1_000_000_000,
                                 "cache file was rewritten on second run")

    def test_max_chunks_cap_logs_warning_and_truncates(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "chunks"
            # expected_page_h = round(200 * 1.414) = 283; height 100_000 -> ~440 chunks
            strip = _make_uniform_strip(200, height=100_000)
            record = self._save_image_record(tmp, "huge.jpg", strip)
            config = ChunkerConfig(chunk_cache_dir=cache_dir)

            with self.assertLogs("src.document_restoration.chunker", level="WARNING") as logs:
                chunks = create_chunks(record, config)

            self.assertEqual(len(chunks), 100)
            self.assertIn(
                "truncated",
                "\n".join(logs.output).lower(),
            )
```

Also add `from src.document_restoration.chunker import create_chunks` to the imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_chunker.CreateChunksIntegrationTests -v`
Expected: FAIL — `create_chunks` doesn't accept `config` param and short-image test gets `TypeError`.

- [ ] **Step 3: Implement `_materialize_chunks` and wire `create_chunks`**

Replace `src/document_restoration/chunker.py` contents:

```python
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import chunk_storage
from .models import ImageChunk, ImageRecord


LOGGER = logging.getLogger(__name__)


STRIP_ASPECT_THRESHOLD = 3.0
PAGE_HEIGHT_RATIO = 1.414  # sqrt(2), A4 portrait
WHITE_ROW_THRESHOLD = 248
MIN_BAND_RATIO = 0.3
DOWNSCALE_WIDTH = 200
MAX_CHUNKS_PER_IMAGE = 100


@dataclass(frozen=True)
class ChunkerConfig:
    strip_aspect_threshold: float = STRIP_ASPECT_THRESHOLD
    page_height_ratio: float = PAGE_HEIGHT_RATIO
    chunk_cache_dir: "Path | None" = None


def create_chunks(
    image: ImageRecord, config: "ChunkerConfig | None" = None
) -> list[ImageChunk]:
    if config is None:
        config = ChunkerConfig()

    try:
        with Image.open(image.path) as pil_image:
            width, height = pil_image.size
    except Exception as exc:
        raise ChunkerError(f"Failed to read image header for {image.file_name}: {exc}") from exc

    aspect = height / width if width else float("inf")
    if aspect <= config.strip_aspect_threshold:
        return [
            ImageChunk(
                source=image,
                chunk_id=0,
                path=image.path,
                file_name=image.file_name,
                x=0,
                y=0,
                width=None,
                height=None,
            )
        ]

    return _split_strip(image, width, height, config)


def _split_strip(
    image: ImageRecord, width: int, height: int, config: ChunkerConfig
) -> list[ImageChunk]:
    with Image.open(image.path) as pil_image:
        cut_points = _detect_cut_points(pil_image, config)
    chunks = _materialize_chunks(image, width, cut_points, config)
    if len(chunks) > MAX_CHUNKS_PER_IMAGE:
        LOGGER.warning(
            "Image %s produced %s chunks; truncated to %s",
            image.file_name,
            len(chunks),
            MAX_CHUNKS_PER_IMAGE,
        )
        chunks = chunks[:MAX_CHUNKS_PER_IMAGE]
    return chunks


def _materialize_chunks(
    image: ImageRecord,
    width: int,
    cut_points: list[tuple[int, int]],
    config: ChunkerConfig,
) -> list[ImageChunk]:
    cache_dir = config.chunk_cache_dir
    stem = image.path.stem
    chunks: list[ImageChunk] = []
    with Image.open(image.path) as pil_image:
        for idx, (y0, y1) in enumerate(cut_points):
            nn = f"{idx + 1:02d}"
            file_name = f"{stem}_p{nn}.jpg"
            if cache_dir is not None:
                path = cache_dir / file_name
            else:
                # No cache dir -> fall back to source path (single-chunk semantics)
                # Should not happen for strips, but stay safe.
                path = image.path
            if cache_dir is not None and not chunk_storage.file_exists(path):
                cropped = pil_image.crop((0, y0, width, y1))
                chunk_storage.write_jpeg(path, cropped)
            chunks.append(
                ImageChunk(
                    source=image,
                    chunk_id=idx,
                    path=path,
                    file_name=file_name,
                    x=0,
                    y=y0,
                    width=width,
                    height=y1 - y0,
                )
            )
    return chunks


def _detect_cut_points(image: Image.Image, config: ChunkerConfig) -> list[tuple[int, int]]:
    width, height = image.size
    expected_page_h = max(1, round(width * config.page_height_ratio))
    if height <= expected_page_h:
        return [(0, height)]

    bands = _find_white_bands(image, expected_page_h)
    if _bands_look_like_page_separators(bands, height, expected_page_h):
        return _cuts_from_bands(bands, height)

    return _fixed_height_cuts(height, expected_page_h)


def _find_white_bands(image: Image.Image, expected_page_h: int) -> list[tuple[int, int]]:
    width, height = image.size
    new_w = DOWNSCALE_WIDTH
    new_h = max(1, round(height * new_w / width))
    small = image.convert("L").resize((new_w, new_h), Image.BILINEAR)
    pixels = list(small.getdata())
    row_mean = [sum(pixels[r * new_w:(r + 1) * new_w]) / new_w for r in range(new_h)]

    min_band_downscaled = max(1, round(expected_page_h * new_w / width * MIN_BAND_RATIO))
    bands: list[tuple[int, int]] = []
    i = 0
    while i < new_h:
        if row_mean[i] >= WHITE_ROW_THRESHOLD:
            j = i
            while j < new_h and row_mean[j] >= WHITE_ROW_THRESHOLD:
                j += 1
            if j - i >= min_band_downscaled:
                y0 = round(i * height / new_h)
                y1 = round(j * height / new_h)
                bands.append((y0, y1))
            i = j
        else:
            i += 1
    return bands


def _bands_look_like_page_separators(
    bands: list[tuple[int, int]], height: int, expected_page_h: int
) -> bool:
    if len(bands) < 2:
        return False
    mids = [(b0 + b1) // 2 for b0, b1 in bands]
    distances = [mids[i + 1] - mids[i] for i in range(len(mids) - 1)]
    return all(expected_page_h * 0.5 <= d <= expected_page_h * 2.0 for d in distances)


def _cuts_from_bands(bands: list[tuple[int, int]], height: int) -> list[tuple[int, int]]:
    boundaries = [0] + [(b0 + b1) // 2 for b0, b1 in bands] + [height]
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def _fixed_height_cuts(height: int, expected_page_h: int) -> list[tuple[int, int]]:
    step = max(1, round(expected_page_h * 0.9))
    if height <= step:
        return [(0, height)]
    cuts: list[tuple[int, int]] = []
    y = 0
    while y < height:
        y1 = min(y + expected_page_h, height)
        cuts.append((y, y1))
        if y1 == height:
            break
        y += step
        if len(cuts) >= MAX_CHUNKS_PER_IMAGE:
            break
    return cuts


class ChunkerError(RuntimeError):
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_chunker -v`
Expected: 8 tests pass.

- [ ] **Step 5: Run full suite**

Run: `python -m unittest discover -s tests`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/chunker.py tests/test_chunker.py
git commit -m "feat: split long strips into materialized chunk files"
```

---

### Task 5: Plumb `ChunkerConfig` through `pipeline.run_pipeline`

**Files:**
- Modify: `src/document_restoration/pipeline.py`
- Modify: `tests/test_mvp_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mvp_pipeline.py` (add `ChunkerConfig` to imports):

```python
from src.document_restoration.chunker import ChunkerConfig
```

Add this test inside `PipelineTests`:

```python
    def test_run_pipeline_threads_chunker_config_to_create_chunks(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            # Image with aspect 1.0 — well below the configured threshold of 100
            (images / "doc.jpg").write_bytes(b"fake")
            output = root / "submission.csv"
            config = ChunkerConfig(strip_aspect_threshold=100.0)

            # ImageRecord doesn't decode bytes; load_images will return one record.
            # create_chunks will fail when PIL tries to open the fake bytes.
            # That bubbles up as logged exception per-image; pipeline writes empty markdown.
            with self.assertLogs("src.document_restoration.pipeline", level="ERROR"):
                results = run_pipeline(
                    images, output, MockVLClient(), chunker_config=config
                )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].markdown, "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mvp_pipeline.PipelineTests.test_run_pipeline_threads_chunker_config_to_create_chunks -v`
Expected: FAIL with `TypeError: run_pipeline() got an unexpected keyword argument 'chunker_config'`.

- [ ] **Step 3: Update `pipeline.run_pipeline`**

Replace `src/document_restoration/pipeline.py`:

```python
import logging
from pathlib import Path

from .chunker import ChunkerConfig, ChunkerError, create_chunks
from .exporter import write_submission_csv
from .image_loader import load_images
from .merge import merge_chunk_markdown
from .models import DocumentResult
from .vl_client import VLClient


LOGGER = logging.getLogger(__name__)


def run_pipeline(
    input_dir: Path,
    output_path: Path,
    client: VLClient,
    chunker_config: ChunkerConfig | None = None,
) -> list[DocumentResult]:
    images = load_images(input_dir)
    results: list[DocumentResult] = []

    for image in images:
        LOGGER.info("Processing %s", image.file_name)
        try:
            chunks = create_chunks(image, chunker_config)
            parsed = [(chunk, client.parse_chunk(chunk)) for chunk in chunks]
            markdown = merge_chunk_markdown(parsed)
        except (Exception,) as exc:
            if isinstance(exc, ChunkerError):
                LOGGER.error("Chunker failed for %s: %s", image.file_name, exc)
            else:
                LOGGER.exception("Failed to process %s", image.file_name)
            markdown = ""

        results.append(DocumentResult(file_name=image.file_name, markdown=markdown))

    write_submission_csv(results, output_path)
    LOGGER.info("Wrote %s rows to %s", len(results), output_path)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_mvp_pipeline.PipelineTests.test_run_pipeline_threads_chunker_config_to_create_chunks -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `python -m unittest discover -s tests`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/pipeline.py tests/test_mvp_pipeline.py
git commit -m "feat: thread ChunkerConfig through pipeline.run_pipeline"
```

---

### Task 6: `FinixDocVLClient` uses `chunk.path`/`chunk.file_name` and chunk-aware cache key

**Files:**
- Modify: `src/document_restoration/vl_client.py`
- Modify: `tests/test_finixdoc_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_finixdoc_client.py`. Add to imports at top:

```python
import time
from unittest.mock import MagicMock, patch, call
```

Add this test class:

```python
class FinixDocChunkPathTests(unittest.TestCase):
    def _build_client(self, **overrides):
        kwargs = dict(
            user_id="finixB2002",
            api_key="key",
            endpoint="https://example.invalid/api",
            timeout=10,
            max_retries=0,
            cache_dir=None,
        )
        kwargs.update(overrides)
        return FinixDocVLClient(**kwargs)

    def _make_chunk_with_distinct_path(self, tmp_path, stem: str):
        from src.document_restoration.chunker import create_chunks
        from src.document_restoration.models import ImageRecord
        path = tmp_path / f"{stem}.jpg"
        path.write_bytes(b"chunk-bytes")
        record = ImageRecord(file_name=f"{stem}.jpg", path=path)
        return create_chunks(record)[0]._replace(
            path=tmp_path / f"{stem}_p01.jpg",
            file_name=f"{stem}_p01.jpg",
        )

    @patch("src.document_restoration.vl_client.requests.post")
    def test_call_api_uses_chunk_path_not_source_path(self, mock_post):
        mock_post.return_value = _make_response(200, "markdown body", "text/plain")
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            chunk_path = tmp_path / "doc_p01.jpg"
            chunk_path.write_bytes(b"chunk-bytes")
            source_path = tmp_path / "doc.jpg"
            source_path.write_bytes(b"source-bytes")

            from src.document_restoration.models import ImageRecord
            record = ImageRecord(file_name="doc.jpg", path=source_path)
            from src.document_restoration.chunker import create_chunks
            chunk = create_chunks(record)[0]._replace(
                path=chunk_path, file_name="doc_p01.jpg"
            )

            client = self._build_client(cache_dir=None)
            client.parse_chunk(chunk)

        sent_files = mock_post.call_args.kwargs["files"]
        sent_data = mock_post.call_args.kwargs["data"]
        # Multipart opened the chunk file (chunk-bytes), not the source
        self.assertEqual(sent_data["fileName"], "doc_p01.jpg")
        file_obj = sent_files["file"][1]
        # requests passes an open file-like; verify by reading what got uploaded
        file_obj.seek(0)
        self.assertEqual(file_obj.read(), b"chunk-bytes")

    def test_cache_key_differs_for_chunks_of_same_source(self):
        from src.document_restoration.models import ImageRecord
        from src.document_restoration.chunker import create_chunks
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "doc.jpg"
            source_path.write_bytes(b"source-bytes")
            record = ImageRecord(file_name="doc.jpg", path=source_path)
            base_chunk = create_chunks(record)[0]
            chunk_a = base_chunk._replace(
                path=tmp_path / "doc_p01.jpg", file_name="doc_p01.jpg"
            )
            chunk_a.path.write_bytes(b"chunk-a-bytes")
            chunk_b = base_chunk._replace(
                path=tmp_path / "doc_p02.jpg", file_name="doc_p02.jpg"
            )
            chunk_b.path.write_bytes(b"chunk-b-bytes")

            client = self._build_client(cache_dir=None)
            key_a = client._cache_key(chunk_a)
            key_b = client._cache_key(chunk_b)

            self.assertNotEqual(key_a, key_b)

    @patch("src.document_restoration.vl_client.time.sleep")
    @patch("src.document_restoration.vl_client.requests.post")
    def test_min_request_interval_sleeps_before_each_request(self, mock_post, mock_sleep):
        mock_post.return_value = _make_response(200, "ok", "text/plain")
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "doc.jpg"
            source_path.write_bytes(b"x")
            from src.document_restoration.models import ImageRecord
            from src.document_restoration.chunker import create_chunks
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=source_path))[0]

            client = self._build_client(min_request_interval=2.5)
            client.parse_chunk(chunk)

        mock_sleep.assert_called_once_with(2.5)
```

Make sure `_make_response` is already a helper in the test file (it should be from earlier Phase 2 tests). If not, add:

```python
def _make_response(status_code: int, body: str, content_type: str = "text/plain"):
    response = MagicMock()
    response.status_code = status_code
    response.text = body
    response.headers = {"Content-Type": content_type}
    response.json.side_effect = ValueError("not json")
    return response
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_finixdoc_client.FinixDocChunkPathTests -v`
Expected: FAIL — `cache_key` collisions, no `min_request_interval` param, file content is source-bytes.

- [ ] **Step 3: Update `FinixDocVLClient`**

In `src/document_restoration/vl_client.py`:

(a) Add `import time` near the top:

```python
import hashlib
import logging
import time
from pathlib import Path
from typing import Protocol

import requests

from .models import ImageChunk
```

(b) Add module constant:

```python
DEFAULT_MIN_REQUEST_INTERVAL = 0.0
```

(c) Extend `__init__` signature (insert before `cache_dir`):

```python
    def __init__(
        self,
        user_id: str,
        api_key: str,
        endpoint: str,
        timeout: float,
        max_retries: int,
        cache_dir: Path | None,
        min_request_interval: float = DEFAULT_MIN_REQUEST_INTERVAL,
    ) -> None:
        if user_id not in ALLOWED_USER_IDS:
            raise ValueError(
                f"userId '{user_id}' is not in the official whitelist: {sorted(ALLOWED_USER_IDS)}"
            )
        if not api_key:
            raise ValueError("apiKey must not be empty.")
        if not endpoint:
            raise ValueError("endpoint must not be empty.")
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}.")
        if max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {max_retries}.")
        if min_request_interval < 0:
            raise ValueError(
                f"min_request_interval must be non-negative, got {min_request_interval}."
            )

        self.user_id = user_id
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_dir = cache_dir.expanduser().resolve() if cache_dir else None
        self.min_request_interval = min_request_interval
```

(d) Replace `_cache_key`:

```python
    def _cache_key(self, chunk: ImageChunk) -> str:
        hasher = hashlib.sha256()
        hasher.update(chunk.path.read_bytes())
        hasher.update(chunk.file_name.encode("utf-8"))
        hasher.update(b"finixdoc")
        hasher.update(self.endpoint.encode("utf-8"))
        hasher.update(self.user_id.encode("utf-8"))
        return f"{hasher.hexdigest()}.md"
```

(e) Replace `_call_api`:

```python
    def _call_api(self, chunk: ImageChunk) -> str:
        total_attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(total_attempts):
            try:
                if self.min_request_interval > 0:
                    time.sleep(self.min_request_interval)
                with chunk.path.open("rb") as file_obj:
                    response = requests.post(
                        self.endpoint,
                        data={
                            "userId": self.user_id,
                            "apiKey": self.api_key,
                            "fileName": chunk.file_name,
                        },
                        files={"file": (chunk.file_name, file_obj)},
                        timeout=self.timeout,
                    )
                if not 200 <= response.status_code < 300:
                    raise RuntimeError(
                        f"FinixDoc-VL API returned status {response.status_code}"
                    )
                return self._parse_response(response)
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "FinixDoc-VL attempt %s/%s failed for %s: %s",
                    attempt + 1,
                    total_attempts,
                    chunk.file_name,
                    exc,
                )

        raise RuntimeError(
            f"FinixDoc-VL API failed after {total_attempts} attempts for {chunk.file_name}"
        ) from last_error
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_finixdoc_client -v`
Expected: All FinixDoc tests pass (new + old).

- [ ] **Step 5: Run full suite**

Run: `python -m unittest discover -s tests`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/vl_client.py tests/test_finixdoc_client.py
git commit -m "feat: route finixdoc upload through chunk.path with chunk-aware cache key"
```

---

### Task 7: `MockVLClient` per-chunk GT lookup

**Files:**
- Modify: `src/document_restoration/vl_client.py`
- Modify: `tests/test_mvp_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append inside `MockVLClientTests` in `tests/test_mvp_pipeline.py`:

```python
    def test_mock_client_prefers_chunk_specific_gt_over_source_gt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt_dir = root / "mds"
            gt_dir.mkdir()
            image_path = root / "abc.jpg"
            image_path.write_bytes(b"fake")
            (gt_dir / "abc_p01.md").write_text("# Page 1", encoding="utf-8")
            (gt_dir / "abc.md").write_text("# Whole doc", encoding="utf-8")
            chunk = create_chunks(
                ImageRecord(file_name="abc.jpg", path=image_path)
            )[0]._replace(file_name="abc_p01.jpg")

            markdown = MockVLClient(gt_dir=gt_dir).parse_chunk(chunk)

            self.assertEqual(markdown, "# Page 1")

    def test_mock_client_falls_back_to_source_stem_when_no_chunk_gt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt_dir = root / "mds"
            gt_dir.mkdir()
            image_path = root / "abc.jpg"
            image_path.write_bytes(b"fake")
            (gt_dir / "abc.md").write_text("# Whole doc", encoding="utf-8")
            chunk = create_chunks(
                ImageRecord(file_name="abc.jpg", path=image_path)
            )[0]._replace(file_name="abc_p01.jpg")

            markdown = MockVLClient(gt_dir=gt_dir).parse_chunk(chunk)

            self.assertEqual(markdown, "# Whole doc")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_mvp_pipeline.MockVLClientTests -v`
Expected: FAIL — both new tests fail because the current `_find_ground_truth` only looks up `chunk.source.path.stem`.

- [ ] **Step 3: Update `MockVLClient._find_ground_truth`**

In `src/document_restoration/vl_client.py`, replace `_find_ground_truth`:

```python
    def _find_ground_truth(self, chunk: ImageChunk) -> Path | None:
        chunk_stem = Path(chunk.file_name).stem
        source_stem = chunk.source.path.stem

        candidates: list[Path] = []
        if self.gt_dir is not None:
            candidates.append(self.gt_dir / f"{chunk_stem}.md")
            candidates.append(self.gt_dir / f"{source_stem}.md")
        sibling_mds = chunk.source.path.parent.parent / "mds"
        candidates.append(sibling_mds / f"{chunk_stem}.md")
        candidates.append(sibling_mds / f"{source_stem}.md")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_mvp_pipeline.MockVLClientTests tests.test_finixdoc_client -v`
Expected: All tests pass.

- [ ] **Step 5: Run full suite**

Run: `python -m unittest discover -s tests`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/vl_client.py tests/test_mvp_pipeline.py
git commit -m "feat: mock client prefers chunk-specific gt with source fallback"
```

---

### Task 8: CLI flags and end-to-end integration

**Files:**
- Modify: `main.py`
- Modify: `tests/test_mvp_pipeline.py` (extend `PipelineTests`)

- [ ] **Step 1: Write the failing test**

Append inside `PipelineTests` in `tests/test_mvp_pipeline.py`:

```python
    def test_main_cli_passes_new_chunker_flags_and_runs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            (images / "doc.jpg").write_bytes(b"fake")
            output = root / "submission.csv"

            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--input_dir", str(images),
                    "--output", str(output),
                    "--client", "mock",
                    "--strip_aspect_threshold", "5.0",
                    "--page_height_ratio", "1.414",
                    "--chunk_cache_dir", str(root / "chunks"),
                    "--min_request_interval", "0",
                ],
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mvp_pipeline.PipelineTests.test_main_cli_passes_new_chunker_flags_and_runs -v`
Expected: FAIL — `SystemExit: 2` with `error: unrecognized arguments: --strip_aspect_threshold ...`.

- [ ] **Step 3: Add CLI flags and wire to pipeline**

Replace `main.py` contents:

```python
import argparse
import logging
from pathlib import Path

from src.document_restoration.chunker import ChunkerConfig
from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import (
    DEFAULT_API_KEY,
    DEFAULT_CACHE_DIR,
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_ID,
    FinixDocVLClient,
    MockVLClient,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run document restoration pipeline.")
    parser.add_argument(
        "--input_dir", required=True, help="Directory containing input images."
    )
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument(
        "--gt_dir",
        default=None,
        help="Optional directory containing ground-truth Markdown files (mock client only).",
    )
    parser.add_argument(
        "--client",
        choices=["mock", "finixdoc"],
        default="mock",
        help="VL client implementation.",
    )
    parser.add_argument(
        "--user_id",
        default=DEFAULT_USER_ID,
        help=f"FinixDoc-VL whitelist userId (default: {DEFAULT_USER_ID}).",
    )
    parser.add_argument(
        "--api_key",
        default=DEFAULT_API_KEY,
        help="FinixDoc-VL apiKey (default: official fixed key).",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="FinixDoc-VL API endpoint.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--max_retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum number of retries per image.",
    )
    parser.add_argument(
        "--cache_dir",
        default=str(DEFAULT_CACHE_DIR),
        help="Local cache directory for parsed markdown (pass 'none' to disable).",
    )
    parser.add_argument(
        "--min_request_interval",
        type=float,
        default=0.0,
        help="Minimum seconds between FinixDoc-VL API requests (rate-limit avoidance).",
    )
    parser.add_argument(
        "--strip_aspect_threshold",
        type=float,
        default=3.0,
        help="height/width ratio above which an image is treated as a tall strip.",
    )
    parser.add_argument(
        "--page_height_ratio",
        type=float,
        default=1.414,
        help="Expected page height as a multiple of image width (sqrt(2) for A4).",
    )
    parser.add_argument(
        "--chunk_cache_dir",
        default=".cache/chunks",
        help="Directory for materialized chunk JPEGs (pass 'none' to disable chunk file caching).",
    )
    parser.add_argument("--log_level", default="INFO", help="Python logging level.")
    return parser


def create_client(args: argparse.Namespace):
    if args.client == "mock":
        return MockVLClient(Path(args.gt_dir) if args.gt_dir else None)
    if args.client == "finixdoc":
        cache_arg = (args.cache_dir or "").strip()
        cache_dir = None if cache_arg.lower() == "none" else Path(cache_arg)
        return FinixDocVLClient(
            user_id=args.user_id,
            api_key=args.api_key,
            endpoint=args.endpoint,
            timeout=args.timeout,
            max_retries=args.max_retries,
            cache_dir=cache_dir,
            min_request_interval=args.min_request_interval,
        )
    raise ValueError(f"Unsupported client: {args.client}")


def build_chunker_config(args: argparse.Namespace) -> ChunkerConfig:
    chunk_cache_arg = (args.chunk_cache_dir or "").strip()
    chunk_cache_dir = None if chunk_cache_arg.lower() == "none" else Path(chunk_cache_arg)
    return ChunkerConfig(
        strip_aspect_threshold=args.strip_aspect_threshold,
        page_height_ratio=args.page_height_ratio,
        chunk_cache_dir=chunk_cache_dir,
    )


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = create_client(args)
    chunker_config = build_chunker_config(args)
    run_pipeline(Path(args.input_dir), Path(args.output), client, chunker_config=chunker_config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -v`
Expected: All tests pass including the new CLI test.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_mvp_pipeline.py
git commit -m "feat: expose chunker and rate-limit flags on the cli"
```

---

## Self-review notes

- **Spec coverage**:
  - aspect-threshold gate → Task 4 (`create_chunks` integration)
  - white-band detection with fixed-height fallback → Task 3 (`_detect_cut_points`)
  - `.cache/chunks/` persistent materialized chunks → Tasks 2 (storage) + 4 (materialize)
  - `ImageChunk.file_name` → Task 1
  - `FinixDocVLClient` uses chunk.path + new cache key + `min_request_interval` → Task 6
  - `MockVLClient` chunk-specific GT priority → Task 7
  - `ChunkerConfig` + pipeline plumbing → Task 5
  - 4 CLI flags → Task 8
  - edge cases (PIL open failure, max chunks cap, single-page fallback) → Tasks 3 + 4
- **Placeholder scan**: every code step has concrete code; no "TODO"/"similar to N".
- **Type consistency**: `ChunkerConfig` field names (`strip_aspect_threshold`, `page_height_ratio`, `chunk_cache_dir`) match between dataclass, `create_chunks` callsite, pipeline, and CLI. `ImageChunk.file_name` is consistently used in `_call_api`, `_cache_key`, `_find_ground_truth`, `_materialize_chunks`.
- **Edge case**: `create_chunks` now reads image header (PIL open) for every image, including non-strip images. This adds disk I/O to the MVP path. For a corrupt non-strip image, the test in Task 5 expects ERROR logging + empty markdown; `ChunkerError` is caught in the pipeline-level `except Exception` and re-classified. The single existing test that does `(images / "doc.jpg").write_bytes(b"fake")` will now go through this error path — Task 5's test makes this explicit.
