# MVP Document Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个可运行的 MVP baseline，从图片目录生成符合赛事格式的 `submission.csv`。

**Architecture:** 使用 `main.py` 作为 CLI 入口，核心逻辑放在 `src/document_restoration/`。MVP 每张图片生成一个 chunk，通过可替换的 `VLClient` 解析为 Markdown，再合并并导出 CSV。

**Tech Stack:** Python 3.10+，仅使用标准库；测试使用 `unittest` 和 `tempfile`。

## Global Constraints

- 输出 CSV 必须且仅包含 `file_name` 和 `ground_truth` 两列。
- MVP 默认使用 `MockVLClient`，不接入真实 FinixDoc-VL API。
- 图片扩展名支持 `.jpg`、`.jpeg`、`.png`、`.bmp`、`.tif`、`.tiff`。
- 输入图片按文件名排序，保证结果可复现。
- 单张图片解析失败不得中断全局任务。
- 代码结构必须允许后续替换真实 `FinixDocVLClient`，不改变主流程。

---

## File Structure

- Create: `main.py`  
  CLI 参数解析、日志初始化、调用 pipeline。
- Create: `src/document_restoration/__init__.py`  
  包标记和版本号。
- Create: `src/document_restoration/models.py`  
  定义 `ImageRecord`、`ImageChunk`、`DocumentResult`。
- Create: `src/document_restoration/image_loader.py`  
  图片目录扫描和排序。
- Create: `src/document_restoration/chunker.py`  
  MVP 一图一 chunk。
- Create: `src/document_restoration/vl_client.py`  
  `VLClient` 协议、`MockVLClient`、预留 `FinixDocVLClient`。
- Create: `src/document_restoration/merge.py`  
  chunk Markdown 合并。
- Create: `src/document_restoration/exporter.py`  
  CSV 写出和基础校验。
- Create: `src/document_restoration/pipeline.py`  
  串联 image loader、chunker、client、merge、exporter。
- Create: `tests/test_mvp_pipeline.py`  
  MVP 端到端和核心模块测试。

---

### Task 1: 数据模型与图片发现

**Files:**
- Create: `src/document_restoration/__init__.py`
- Create: `src/document_restoration/models.py`
- Create: `src/document_restoration/image_loader.py`
- Test: `tests/test_mvp_pipeline.py`

**Interfaces:**
- Produces: `ImageRecord(file_name: str, path: Path)`
- Produces: `load_images(input_dir: Path) -> list[ImageRecord]`
- Later tasks consume `ImageRecord.file_name` and `ImageRecord.path`.

- [ ] **Step 1: Write the failing tests**

Append this to `tests/test_mvp_pipeline.py`:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.document_restoration.image_loader import load_images


class ImageLoaderTests(unittest.TestCase):
    def test_load_images_returns_supported_files_sorted_by_name(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.png").write_bytes(b"fake")
            (root / "a.jpg").write_bytes(b"fake")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")

            records = load_images(root)

            self.assertEqual([r.file_name for r in records], ["a.jpg", "b.png"])
            self.assertTrue(all(r.path.is_absolute() for r in records))

    def test_load_images_fails_for_missing_directory(self):
        with self.assertRaises(FileNotFoundError):
            load_images(Path("missing-input-directory"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.document_restoration'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/document_restoration/__init__.py`:

```python
"""Minimal document restoration pipeline."""

__version__ = "0.1.0"
```

Create `src/document_restoration/models.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageRecord:
    file_name: str
    path: Path


@dataclass(frozen=True)
class ImageChunk:
    source: ImageRecord
    chunk_id: int
    path: Path
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class DocumentResult:
    file_name: str
    markdown: str
```

Create `src/document_restoration/image_loader.py`:

```python
from pathlib import Path

from .models import ImageRecord


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def load_images(input_dir: Path) -> list[ImageRecord]:
    input_dir = input_dir.expanduser().resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    records: list[ImageRecord] = []
    for path in input_dir.iterdir():
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            records.append(ImageRecord(file_name=path.name, path=path.resolve()))

    return sorted(records, key=lambda record: record.file_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: PASS for both `ImageLoaderTests`.

- [ ] **Step 5: Commit**

```bash
git add src/document_restoration/__init__.py src/document_restoration/models.py src/document_restoration/image_loader.py tests/test_mvp_pipeline.py
git commit -m "feat: add image discovery"
```

---

### Task 2: 一图一 Chunk 与 Mock 客户端

**Files:**
- Create: `src/document_restoration/chunker.py`
- Create: `src/document_restoration/vl_client.py`
- Modify: `tests/test_mvp_pipeline.py`

**Interfaces:**
- Consumes: `ImageRecord`
- Produces: `create_chunks(image: ImageRecord) -> list[ImageChunk]`
- Produces: `VLClient.parse_chunk(chunk: ImageChunk) -> str`
- Produces: `MockVLClient(gt_dir: Path | None = None).parse_chunk(chunk: ImageChunk) -> str`

- [ ] **Step 1: Write the failing tests**

Append these test cases before the final `if __name__ == "__main__":` block:

```python
from src.document_restoration.chunker import create_chunks
from src.document_restoration.models import ImageRecord
from src.document_restoration.vl_client import FinixDocVLClient, MockVLClient


class ChunkerTests(unittest.TestCase):
    def test_create_chunks_returns_one_chunk_for_mvp(self):
        image = ImageRecord(file_name="doc.jpg", path=Path("doc.jpg").resolve())

        chunks = create_chunks(image)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, 0)
        self.assertEqual(chunks[0].source, image)
        self.assertEqual(chunks[0].path, image.path)


class MockVLClientTests(unittest.TestCase):
    def test_mock_client_reads_matching_markdown_from_gt_dir(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt_dir = root / "mds"
            gt_dir.mkdir()
            image_path = root / "abc.jpg"
            image_path.write_bytes(b"fake")
            (gt_dir / "abc.md").write_text("# 标题\n\n正文", encoding="utf-8")
            chunk = create_chunks(ImageRecord(file_name="abc.jpg", path=image_path))[0]

            markdown = MockVLClient(gt_dir=gt_dir).parse_chunk(chunk)

            self.assertEqual(markdown, "# 标题\n\n正文")

    def test_mock_client_returns_deterministic_fallback_without_gt(self):
        image = ImageRecord(file_name="missing.jpg", path=Path("missing.jpg").resolve())
        chunk = create_chunks(image)[0]

        markdown = MockVLClient().parse_chunk(chunk)

        self.assertEqual(markdown, "# missing.jpg\n\nMock parse result for missing.jpg.")

    def test_finixdoc_client_is_explicitly_not_implemented(self):
        image = ImageRecord(file_name="doc.jpg", path=Path("doc.jpg").resolve())
        chunk = create_chunks(image)[0]

        with self.assertRaises(NotImplementedError):
            FinixDocVLClient().parse_chunk(chunk)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: FAIL with `ModuleNotFoundError` or import errors for `chunker` and `vl_client`.

- [ ] **Step 3: Write minimal implementation**

Create `src/document_restoration/chunker.py`:

```python
from .models import ImageChunk, ImageRecord


def create_chunks(image: ImageRecord) -> list[ImageChunk]:
    return [
        ImageChunk(
            source=image,
            chunk_id=0,
            path=image.path,
            x=0,
            y=0,
            width=None,
            height=None,
        )
    ]
```

Create `src/document_restoration/vl_client.py`:

```python
from pathlib import Path
from typing import Protocol

from .models import ImageChunk


class VLClient(Protocol):
    def parse_chunk(self, chunk: ImageChunk) -> str:
        raise NotImplementedError


class MockVLClient:
    def __init__(self, gt_dir: Path | None = None) -> None:
        self.gt_dir = gt_dir.expanduser().resolve() if gt_dir else None

    def parse_chunk(self, chunk: ImageChunk) -> str:
        gt_path = self._find_ground_truth(chunk)
        if gt_path is not None:
            return gt_path.read_text(encoding="utf-8").strip()

        return f"# {chunk.source.file_name}\n\nMock parse result for {chunk.source.file_name}."

    def _find_ground_truth(self, chunk: ImageChunk) -> Path | None:
        stem = chunk.source.path.stem
        candidates: list[Path] = []
        if self.gt_dir is not None:
            candidates.append(self.gt_dir / f"{stem}.md")

        sibling_mds = chunk.source.path.parent.parent / "mds"
        candidates.append(sibling_mds / f"{stem}.md")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None


class FinixDocVLClient:
    def parse_chunk(self, chunk: ImageChunk) -> str:
        raise NotImplementedError(
            "FinixDoc-VL API details are not available yet. Use --client mock."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: PASS for image loader, chunker, and mock client tests.

- [ ] **Step 5: Commit**

```bash
git add src/document_restoration/chunker.py src/document_restoration/vl_client.py tests/test_mvp_pipeline.py
git commit -m "feat: add mock vl client"
```

---

### Task 3: Markdown 合并与 CSV 导出

**Files:**
- Create: `src/document_restoration/merge.py`
- Create: `src/document_restoration/exporter.py`
- Modify: `tests/test_mvp_pipeline.py`

**Interfaces:**
- Consumes: `ImageChunk`
- Consumes: `DocumentResult`
- Produces: `merge_chunk_markdown(chunks_and_markdown: list[tuple[ImageChunk, str]]) -> str`
- Produces: `write_submission_csv(results: list[DocumentResult], output_path: Path) -> None`

- [ ] **Step 1: Write the failing tests**

Append these test cases before the final `if __name__ == "__main__":` block:

```python
import csv

from src.document_restoration.exporter import write_submission_csv
from src.document_restoration.merge import merge_chunk_markdown
from src.document_restoration.models import DocumentResult


class MergeTests(unittest.TestCase):
    def test_merge_chunk_markdown_orders_by_chunk_id_and_skips_empty_text(self):
        image = ImageRecord(file_name="doc.jpg", path=Path("doc.jpg").resolve())
        chunk_2 = create_chunks(image)[0]
        chunk_1 = create_chunks(image)[0]
        object.__setattr__(chunk_2, "chunk_id", 2)
        object.__setattr__(chunk_1, "chunk_id", 1)

        markdown = merge_chunk_markdown([(chunk_2, "第二段"), (chunk_1, "第一段"), (chunk_1, "   ")])

        self.assertEqual(markdown, "第一段\n\n第二段")


class ExporterTests(unittest.TestCase):
    def test_write_submission_csv_writes_exact_columns_and_escapes_markdown(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "submission.csv"
            results = [
                DocumentResult(file_name="a.jpg", markdown="# 标题\n\n含,逗号和\"引号\""),
                DocumentResult(file_name="b.jpg", markdown="正文"),
            ]

            write_submission_csv(results, output)

            with output.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(rows[0]["file_name"], "a.jpg")
            self.assertEqual(rows[0]["ground_truth"], "# 标题\n\n含,逗号和\"引号\"")
            self.assertEqual(rows[1]["file_name"], "b.jpg")
            self.assertEqual(set(rows[0].keys()), {"file_name", "ground_truth"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: FAIL with import errors for `merge` and `exporter`.

- [ ] **Step 3: Write minimal implementation**

Create `src/document_restoration/merge.py`:

```python
from .models import ImageChunk


def merge_chunk_markdown(chunks_and_markdown: list[tuple[ImageChunk, str]]) -> str:
    parts: list[str] = []
    for _chunk, markdown in sorted(chunks_and_markdown, key=lambda item: item[0].chunk_id):
        normalized = markdown.strip()
        if normalized:
            parts.append(normalized)
    return "\n\n".join(parts)
```

Create `src/document_restoration/exporter.py`:

```python
import csv
from pathlib import Path

from .models import DocumentResult


FIELD_NAMES = ["file_name", "ground_truth"]


def write_submission_csv(results: list[DocumentResult], output_path: Path) -> None:
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "file_name": result.file_name,
                    "ground_truth": result.markdown,
                }
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: PASS for merge and exporter tests plus earlier tests.

- [ ] **Step 5: Commit**

```bash
git add src/document_restoration/merge.py src/document_restoration/exporter.py tests/test_mvp_pipeline.py
git commit -m "feat: add markdown export"
```

---

### Task 4: Pipeline 与 CLI 入口

**Files:**
- Create: `src/document_restoration/pipeline.py`
- Create: `main.py`
- Modify: `tests/test_mvp_pipeline.py`
- Create: `requirements.txt`

**Interfaces:**
- Consumes: `load_images`, `create_chunks`, `VLClient`, `merge_chunk_markdown`, `write_submission_csv`
- Produces: `run_pipeline(input_dir: Path, output_path: Path, client: VLClient) -> list[DocumentResult]`
- Produces: CLI command `python main.py --input_dir <images> --output <csv> --client mock`

- [ ] **Step 1: Write the failing tests**

Append these test cases before the final `if __name__ == "__main__":` block:

```python
import subprocess
import sys

from src.document_restoration.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_run_pipeline_uses_mock_gt_and_writes_csv(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            mds = root / "mds"
            images.mkdir()
            mds.mkdir()
            (images / "doc.jpg").write_bytes(b"fake")
            (mds / "doc.md").write_text("# 文档\n\n正文", encoding="utf-8")
            output = root / "submission.csv"

            results = run_pipeline(images, output, MockVLClient(gt_dir=mds))

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].file_name, "doc.jpg")
            self.assertEqual(results[0].markdown, "# 文档\n\n正文")
            self.assertTrue(output.exists())

    def test_main_cli_runs_with_mock_client(self):
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
                    "--input_dir",
                    str(images),
                    "--output",
                    str(output),
                    "--client",
                    "mock",
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

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: FAIL with import error for `pipeline` or missing `main.py`.

- [ ] **Step 3: Write minimal implementation**

Create `src/document_restoration/pipeline.py`:

```python
import logging
from pathlib import Path

from .chunker import create_chunks
from .exporter import write_submission_csv
from .image_loader import load_images
from .merge import merge_chunk_markdown
from .models import DocumentResult
from .vl_client import VLClient


LOGGER = logging.getLogger(__name__)


def run_pipeline(input_dir: Path, output_path: Path, client: VLClient) -> list[DocumentResult]:
    images = load_images(input_dir)
    results: list[DocumentResult] = []

    for image in images:
        LOGGER.info("Processing %s", image.file_name)
        try:
            chunks = create_chunks(image)
            parsed = [(chunk, client.parse_chunk(chunk)) for chunk in chunks]
            markdown = merge_chunk_markdown(parsed)
        except Exception:
            LOGGER.exception("Failed to process %s", image.file_name)
            markdown = ""

        results.append(DocumentResult(file_name=image.file_name, markdown=markdown))

    write_submission_csv(results, output_path)
    LOGGER.info("Wrote %s rows to %s", len(results), output_path)
    return results
```

Create `main.py`:

```python
import argparse
import logging
from pathlib import Path

from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import FinixDocVLClient, MockVLClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MVP document restoration pipeline.")
    parser.add_argument("--input_dir", required=True, help="Directory containing input images.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--gt_dir", default=None, help="Optional directory containing ground-truth Markdown files.")
    parser.add_argument("--client", choices=["mock", "finixdoc"], default="mock", help="VL client implementation.")
    parser.add_argument("--log_level", default="INFO", help="Python logging level.")
    return parser


def create_client(client_name: str, gt_dir: str | None):
    if client_name == "mock":
        return MockVLClient(Path(gt_dir) if gt_dir else None)
    if client_name == "finixdoc":
        return FinixDocVLClient()
    raise ValueError(f"Unsupported client: {client_name}")


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = create_client(args.client, args.gt_dir)
    run_pipeline(Path(args.input_dir), Path(args.output), client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `requirements.txt`:

```text
# MVP uses only Python standard library.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: PASS for all tests.

- [ ] **Step 5: Run MVP against available training data**

Run:

```bash
python main.py --input_dir "data/AFAC 训练数据集/finixdocbench_huge_long_100/images" --output outputs/submission_long_mock.csv --client mock
```

Expected: command exits 0 and writes `outputs/submission_long_mock.csv`.

- [ ] **Step 6: Commit**

```bash
git add main.py requirements.txt src/document_restoration/pipeline.py tests/test_mvp_pipeline.py
git commit -m "feat: add mvp pipeline cli"
```

---

## Self-Review

Spec coverage:

- 图片扫描：Task 1。
- 一图一 chunk：Task 2。
- 可替换 `VLClient`：Task 2。
- mock 本地 client：Task 2。
- Markdown 合并：Task 3。
- CSV 输出：Task 3。
- CLI 和端到端运行：Task 4。
- 单图失败不中断：Task 4。

Placeholder scan:

- `FinixDocVLClient` 的 `NotImplementedError` 是设计明确要求的预留行为，不是计划占位。
- 没有未填写内容或未定义接口。

Type consistency:

- `ImageRecord`、`ImageChunk`、`DocumentResult` 均在 Task 1 定义。
- 后续任务使用的函数签名与 Task 1-3 的产出一致。
