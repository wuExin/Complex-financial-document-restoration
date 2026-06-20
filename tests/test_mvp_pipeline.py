import csv
import dataclasses
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.document_restoration.chunker import ChunkerConfig, create_chunks
from src.document_restoration.exporter import write_submission_csv
from src.document_restoration.image_loader import load_images
from src.document_restoration.merge import merge_chunk_markdown
from src.document_restoration.models import DocumentResult, ImageRecord
from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import MockVLClient
from tests._fixtures import write_tiny_jpeg


class FailingOneImageClient:
    def parse_chunk(self, chunk):
        if chunk.source.file_name == "bad.jpg":
            raise RuntimeError("parse failed")
        return f"# Parsed {chunk.source.file_name}"


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


class ChunkerTests(unittest.TestCase):
    def test_create_chunks_returns_one_chunk_for_mvp(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.jpg"
            write_tiny_jpeg(path)
            image = ImageRecord(file_name="doc.jpg", path=path)

            chunks = create_chunks(image)

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].chunk_id, 0)
            self.assertEqual(chunks[0].source, image)
            self.assertEqual(chunks[0].path, image.path)

    def test_create_chunks_sets_file_name_equal_to_source_for_mvp(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.jpg"
            write_tiny_jpeg(path)
            image = ImageRecord(file_name="doc.jpg", path=path)

            chunks = create_chunks(image)

            self.assertEqual(chunks[0].file_name, "doc.jpg")


class MockVLClientTests(unittest.TestCase):
    def test_mock_client_reads_matching_markdown_from_gt_dir(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt_dir = root / "mds"
            gt_dir.mkdir()
            image_path = root / "abc.jpg"
            write_tiny_jpeg(image_path)
            (gt_dir / "abc.md").write_text("# 标题\n\n正文", encoding="utf-8")
            chunk = create_chunks(ImageRecord(file_name="abc.jpg", path=image_path))[0]

            markdown = MockVLClient(gt_dir=gt_dir).parse_chunk(chunk)

            self.assertEqual(markdown, "# 标题\n\n正文")

    def test_mock_client_returns_deterministic_fallback_without_gt(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.jpg"
            write_tiny_jpeg(path)
            image = ImageRecord(file_name="missing.jpg", path=path)
            chunk = create_chunks(image)[0]

            markdown = MockVLClient().parse_chunk(chunk)

            self.assertEqual(markdown, "# missing.jpg\n\nMock parse result for missing.jpg.")

    def test_mock_client_prefers_chunk_specific_gt_over_source_gt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt_dir = root / "mds"
            gt_dir.mkdir()
            image_path = root / "abc.jpg"
            write_tiny_jpeg(image_path)
            (gt_dir / "abc_p01.md").write_text("# Page 1", encoding="utf-8")
            (gt_dir / "abc.md").write_text("# Whole doc", encoding="utf-8")
            chunk = create_chunks(
                ImageRecord(file_name="abc.jpg", path=image_path)
            )[0]
            chunk = dataclasses.replace(chunk, file_name="abc_p01.jpg")

            markdown = MockVLClient(gt_dir=gt_dir).parse_chunk(chunk)

            self.assertEqual(markdown, "# Page 1")

    def test_mock_client_falls_back_to_source_stem_when_no_chunk_gt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt_dir = root / "mds"
            gt_dir.mkdir()
            image_path = root / "abc.jpg"
            write_tiny_jpeg(image_path)
            (gt_dir / "abc.md").write_text("# Whole doc", encoding="utf-8")
            chunk = create_chunks(
                ImageRecord(file_name="abc.jpg", path=image_path)
            )[0]
            chunk = dataclasses.replace(chunk, file_name="abc_p01.jpg")

            markdown = MockVLClient(gt_dir=gt_dir).parse_chunk(chunk)

            self.assertEqual(markdown, "# Whole doc")


class MergeTests(unittest.TestCase):
    def test_merge_chunk_markdown_orders_by_chunk_id_and_skips_empty_text(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.jpg"
            write_tiny_jpeg(path)
            image = ImageRecord(file_name="doc.jpg", path=path)
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


class PipelineTests(unittest.TestCase):
    def test_run_pipeline_uses_mock_gt_and_writes_csv(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            mds = root / "mds"
            images.mkdir()
            mds.mkdir()
            write_tiny_jpeg(images / "doc.jpg")
            (mds / "doc.md").write_text("# 文档\n\n正文", encoding="utf-8")
            output = root / "submission.csv"

            results = run_pipeline(images, output, MockVLClient(gt_dir=mds))

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].file_name, "doc.jpg")
            self.assertEqual(results[0].markdown, "# 文档\n\n正文")
            self.assertTrue(output.exists())

    def test_run_pipeline_threads_chunker_config_to_create_chunks(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            # Image with aspect 1.0 — well below the configured threshold of 100,
            # so it takes the MVP single-chunk path. Tiny JPEG so create_chunks can
            # actually open the header.
            write_tiny_jpeg(images / "doc.jpg")
            output = root / "submission.csv"
            config = ChunkerConfig(strip_aspect_threshold=100.0)

            results = run_pipeline(
                images, output, MockVLClient(), chunker_config=config
            )

            self.assertEqual(len(results), 1)
            # MockVLClient returns "# doc.jpg\n\nMock parse result for doc.jpg."
            # so markdown should be non-empty
            self.assertEqual(results[0].markdown, "# doc.jpg\n\nMock parse result for doc.jpg.")

    def test_run_pipeline_keeps_global_task_when_single_image_parse_fails(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            write_tiny_jpeg(images / "bad.jpg")
            write_tiny_jpeg(images / "good.jpg")
            output = root / "submission.csv"

            with self.assertLogs("src.document_restoration.pipeline", level="ERROR") as logs:
                results = run_pipeline(images, output, FailingOneImageClient())

            with output.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            self.assertIn("Failed to process bad.jpg", "\n".join(logs.output))
            self.assertEqual([r.file_name for r in results], ["bad.jpg", "good.jpg"])
            self.assertEqual([row["file_name"] for row in rows], ["bad.jpg", "good.jpg"])
            self.assertEqual(rows[0]["ground_truth"], "")
            self.assertEqual(rows[1]["ground_truth"], "# Parsed good.jpg")

    def test_main_cli_runs_with_mock_client(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            write_tiny_jpeg(images / "doc.jpg")
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

    def test_main_cli_passes_new_chunker_flags_and_runs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            write_tiny_jpeg(images / "doc.jpg")
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


if __name__ == "__main__":
    unittest.main()
