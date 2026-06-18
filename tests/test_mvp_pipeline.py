import csv
import requests
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from main import create_client
from src.document_restoration.chunker import create_chunks
from src.document_restoration.exporter import write_submission_csv
from src.document_restoration.image_loader import load_images
from src.document_restoration.merge import merge_chunk_markdown
from src.document_restoration.models import DocumentResult, ImageRecord
from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import FinixDocVLClient, MockVLClient


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

class FinixDocConfigTests(unittest.TestCase):
    def test_finixdoc_client_defaults_to_official_configuration(self):
        client = FinixDocVLClient()

        self.assertEqual(client.user_id, "finixB2002")
        self.assertEqual(
            client.endpoint,
            "https://finixdocapi.alipay.com/api/finix_doc/call_with_file",
        )
        self.assertEqual(client.api_key, "F935A5503983FB19F26FA3F00A94EBF9")
        self.assertEqual(client.timeout, 180.0)
        self.assertEqual(client.max_retries, 2)
        self.assertEqual(client.cache_dir, Path(".cache/finixdoc_vl"))

    def test_finixdoc_client_rejects_non_whitelisted_user_id(self):
        with self.assertRaisesRegex(ValueError, "Unsupported FinixDoc userId"):
            FinixDocVLClient(user_id="not-whitelisted")

    def test_finixdoc_client_rejects_empty_api_key(self):
        with self.assertRaisesRegex(ValueError, "apiKey must not be empty"):
            FinixDocVLClient(api_key=" ")

    def test_finixdoc_client_rejects_empty_endpoint(self):
        with self.assertRaisesRegex(ValueError, "endpoint must not be empty"):
            FinixDocVLClient(endpoint="")

    def test_finixdoc_client_rejects_non_positive_timeout(self):
        with self.assertRaisesRegex(ValueError, "timeout must be greater than 0"):
            FinixDocVLClient(timeout=0)

    def test_finixdoc_client_rejects_negative_max_retries(self):
        with self.assertRaisesRegex(ValueError, "max_retries must be greater than or equal to 0"):
            FinixDocVLClient(max_retries=-1)


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


class PipelineTests(unittest.TestCase):
    def test_create_finixdoc_client_uses_cli_options(self):
        client = create_client(
            "finixdoc",
            None,
            "finixD4004",
            "cli-key",
            "https://example.test/api",
            30,
            1,
            ".cache/custom_finixdoc",
        )

        self.assertIsInstance(client, FinixDocVLClient)
        self.assertEqual(client.user_id, "finixD4004")
        self.assertEqual(client.api_key, "cli-key")
        self.assertEqual(client.endpoint, "https://example.test/api")
        self.assertEqual(client.timeout, 30.0)
        self.assertEqual(client.max_retries, 1)
        self.assertEqual(client.cache_dir, Path(".cache/custom_finixdoc"))

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

    def test_run_pipeline_keeps_global_task_when_single_image_parse_fails(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            (images / "bad.jpg").write_bytes(b"fake")
            (images / "good.jpg").write_bytes(b"fake")
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

    def test_pipeline_continues_when_finixdoc_single_image_call_fails(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            (images / "bad.jpg").write_bytes(b"bad")
            (images / "good.jpg").write_bytes(b"good")
            output = root / "submission.csv"

            client = FinixDocVLClient(cache_dir=None, max_retries=0)

            with patch("src.document_restoration.vl_client.requests.post") as post:
                post.side_effect = [
                    FakeResponse(status_code=500, text="server error", content_type="text/plain"),
                    FakeResponse(payload={"markdown": "# Good"}),
                ]
                with self.assertLogs("src.document_restoration.pipeline", level="ERROR") as logs:
                    results = run_pipeline(images, output, client)

            self.assertIn("Failed to process bad.jpg", "\n".join(logs.output))
            self.assertEqual([r.file_name for r in results], ["bad.jpg", "good.jpg"])
            self.assertEqual(results[0].markdown, "")
            self.assertEqual(results[1].markdown, "# Good")

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

    def test_main_cli_accepts_finixdoc_options_without_calling_network(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            image_path = images / "doc.jpg"
            image_path.write_bytes(b"fake")
            output = root / "submission.csv"
            cache_dir = root / "cache"
            cached_client = FinixDocVLClient(
                user_id="finixB2002",
                api_key="cli-key",
                endpoint="https://example.test/api",
                timeout=5,
                max_retries=0,
                cache_dir=cache_dir,
            )
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]
            cached_client._write_cache(chunk, "# Parsed by API")

            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--input_dir",
                    str(images),
                    "--output",
                    str(output),
                    "--client",
                    "finixdoc",
                    "--user_id",
                    "finixB2002",
                    "--api_key",
                    "cli-key",
                    "--endpoint",
                    "https://example.test/api",
                    "--timeout",
                    "5",
                    "--max_retries",
                    "0",
                    "--cache_dir",
                    str(cache_dir),
                ],
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["ground_truth"], "# Parsed by API")


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None, content_type="application/json"):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.headers = {"Content-Type": content_type}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FinixDocResponseAndCacheTests(unittest.TestCase):
    def test_extract_markdown_prefers_top_level_markdown(self):
        client = FinixDocVLClient()
        response = FakeResponse(payload={"markdown": "# Parsed"})

        self.assertEqual(client._extract_markdown(response), "# Parsed")

    def test_extract_markdown_reads_nested_data_markdown(self):
        client = FinixDocVLClient()
        response = FakeResponse(payload={"data": {"markdown": "# Nested"}})

        self.assertEqual(client._extract_markdown(response), "# Nested")

    def test_extract_markdown_reads_result_string(self):
        client = FinixDocVLClient()
        response = FakeResponse(payload={"result": "# Result"})

        self.assertEqual(client._extract_markdown(response), "# Result")

    def test_extract_markdown_reads_data_string(self):
        client = FinixDocVLClient()
        response = FakeResponse(payload={"data": "# Data"})

        self.assertEqual(client._extract_markdown(response), "# Data")

    def test_extract_markdown_uses_text_response_for_non_json(self):
        client = FinixDocVLClient()
        response = FakeResponse(text="# Plain text", payload=None, content_type="text/plain")

        self.assertEqual(client._extract_markdown(response), "# Plain text")

    def test_extract_markdown_rejects_empty_result(self):
        client = FinixDocVLClient()
        response = FakeResponse(payload={"markdown": "   "})

        with self.assertRaisesRegex(ValueError, "FinixDoc response did not contain Markdown"):
            client._extract_markdown(response)

    def test_cache_path_changes_when_file_content_changes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            image_path = root / "doc.jpg"
            image_path.write_bytes(b"first")
            client = FinixDocVLClient(cache_dir=cache_dir)
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]

            first_cache_path = client._cache_path(chunk)
            image_path.write_bytes(b"second")
            second_cache_path = client._cache_path(chunk)

            self.assertIsNotNone(first_cache_path)
            self.assertIsNotNone(second_cache_path)
            self.assertNotEqual(first_cache_path, second_cache_path)

    def test_cache_round_trip_stores_markdown_text(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            image_path = root / "doc.jpg"
            image_path.write_bytes(b"image")
            client = FinixDocVLClient(cache_dir=cache_dir)
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]

            self.assertIsNone(client._read_cache(chunk))
            client._write_cache(chunk, "# Cached")

            self.assertEqual(client._read_cache(chunk), "# Cached")
            cache_files = list(cache_dir.glob("*.md"))
            self.assertEqual(len(cache_files), 1)


class FinixDocHttpTests(unittest.TestCase):
    def test_parse_chunk_builds_multipart_request_fields(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "doc.jpg"
            image_path.write_bytes(b"image-bytes")
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]
            client = FinixDocVLClient(
                user_id="finixC3003",
                api_key="secret",
                endpoint="https://example.test/api",
                timeout=12,
                max_retries=0,
                cache_dir=None,
            )

            with patch("src.document_restoration.vl_client.requests.post") as post:
                post.return_value = FakeResponse(payload={"markdown": "# Parsed"})

                markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# Parsed")
            self.assertEqual(post.call_count, 1)
            _, kwargs = post.call_args
            self.assertEqual(kwargs["data"], {
                "userId": "finixC3003",
                "apiKey": "secret",
                "fileName": "doc.jpg",
            })
            self.assertEqual(kwargs["timeout"], 12.0)
            self.assertEqual(kwargs["files"]["file"][0], "doc.jpg")
            self.assertEqual(kwargs["files"]["file"][1], b"image-bytes")

    def test_parse_chunk_raises_clear_error_for_non_2xx_response(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "doc.jpg"
            image_path.write_bytes(b"image")
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]
            client = FinixDocVLClient(max_retries=0, cache_dir=None)

            with patch("src.document_restoration.vl_client.requests.post") as post:
                post.return_value = FakeResponse(status_code=500, text="server error", content_type="text/plain")

                with self.assertRaisesRegex(RuntimeError, "FinixDoc API returned HTTP 500"):
                    client.parse_chunk(chunk)

    def test_parse_chunk_retries_transient_request_errors(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "doc.jpg"
            image_path.write_bytes(b"image")
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]
            client = FinixDocVLClient(max_retries=1, cache_dir=None)

            with patch("src.document_restoration.vl_client.requests.post") as post:
                post.side_effect = [
                    requests.Timeout("slow"),
                    FakeResponse(payload={"markdown": "# Retry success"}),
                ]

                markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# Retry success")
            self.assertEqual(post.call_count, 2)

    def test_parse_chunk_uses_cache_without_network_call(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            image_path = root / "doc.jpg"
            image_path.write_bytes(b"image")
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]
            client = FinixDocVLClient(cache_dir=cache_dir)
            client._write_cache(chunk, "# Cached")

            with patch("src.document_restoration.vl_client.requests.post") as post:
                markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# Cached")
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
