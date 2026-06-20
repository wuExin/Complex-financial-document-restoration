import argparse
import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import requests as requests_lib
from PIL import Image

from main import create_client
from src.document_restoration.chunker import create_chunks
from src.document_restoration.models import ImageRecord
from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import (
    ALLOWED_USER_IDS,
    DEFAULT_API_KEY,
    DEFAULT_CACHE_DIR,
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_ID,
    FinixDocVLClient,
    MockVLClient,
)
from tests._fixtures import write_tiny_jpeg


class FinixDocClientConstructionTests(unittest.TestCase):
    def test_default_constants_match_spec(self):
        self.assertEqual(DEFAULT_USER_ID, "finixB2002")
        self.assertEqual(DEFAULT_API_KEY, "F935A5503983FB19F26FA3F00A94EBF9")
        self.assertEqual(
            DEFAULT_ENDPOINT,
            "https://finixdocapi.alipay.com/api/finix_doc/call_with_file",
        )
        self.assertEqual(DEFAULT_TIMEOUT, 180)
        self.assertEqual(DEFAULT_MAX_RETRIES, 2)
        self.assertEqual(DEFAULT_CACHE_DIR, Path(".cache/finixdoc_vl"))
        self.assertEqual(
            ALLOWED_USER_IDS,
            {"finixA1001", "finixB2002", "finixC3003", "finixD4004", "finixE5005"},
        )

    def test_construction_succeeds_with_valid_whitelist_user(self):
        with TemporaryDirectory() as tmp:
            client = FinixDocVLClient(
                user_id="finixA1001",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=30,
                max_retries=1,
                cache_dir=Path(tmp),
            )
            self.assertEqual(client.user_id, "finixA1001")

    def test_construction_uses_none_cache_dir_when_disabled(self):
        client = FinixDocVLClient(
            user_id=DEFAULT_USER_ID,
            api_key=DEFAULT_API_KEY,
            endpoint=DEFAULT_ENDPOINT,
            timeout=DEFAULT_TIMEOUT,
            max_retries=DEFAULT_MAX_RETRIES,
            cache_dir=None,
        )
        self.assertIsNone(client.cache_dir)

    def test_construction_fails_when_user_id_not_in_whitelist(self):
        with self.assertRaisesRegex(ValueError, "userId"):
            FinixDocVLClient(
                user_id="rogue",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=30,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_api_key_empty(self):
        with self.assertRaisesRegex(ValueError, "apiKey"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="",
                endpoint=DEFAULT_ENDPOINT,
                timeout=30,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_endpoint_empty(self):
        with self.assertRaisesRegex(ValueError, "endpoint"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="key",
                endpoint="",
                timeout=30,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_timeout_non_positive(self):
        with self.assertRaisesRegex(ValueError, "timeout"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="key",
                endpoint=DEFAULT_ENDPOINT,
                timeout=0,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_max_retries_negative(self):
        with self.assertRaisesRegex(ValueError, "max_retries"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="key",
                endpoint=DEFAULT_ENDPOINT,
                timeout=30,
                max_retries=-1,
                cache_dir=None,
            )


def _make_response(
    status_code: int = 200,
    body: Any = None,
    content_type: str | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"Content-Type": content_type} if content_type else {}
    if isinstance(body, str):
        response.text = body
        response.json.side_effect = ValueError("not json")
    elif body is None:
        response.text = ""
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body
        response.text = json.dumps(body)
    return response


class FinixDocResponseParsingTests(unittest.TestCase):
    def _client(self) -> FinixDocVLClient:
        return FinixDocVLClient(
            user_id=DEFAULT_USER_ID,
            api_key=DEFAULT_API_KEY,
            endpoint=DEFAULT_ENDPOINT,
            timeout=30,
            max_retries=0,
            cache_dir=None,
        )

    def test_parse_response_reads_top_level_markdown(self):
        response = _make_response(body={"markdown": "# 标题\n\n正文"})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "# 标题\n\n正文")

    def test_parse_response_reads_data_markdown_when_top_level_missing(self):
        response = _make_response(body={"data": {"markdown": "从 data 取出"}})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "从 data 取出")

    def test_parse_response_reads_result_field_when_no_markdown(self):
        response = _make_response(body={"result": "从 result 取出"})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "从 result 取出")

    def test_parse_response_reads_data_string_when_no_other_fields(self):
        response = _make_response(body={"data": "纯字符串"})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "纯字符串")

    def test_parse_response_returns_plain_text_when_not_json(self):
        response = _make_response(
            body="直接返回的 markdown", content_type="text/markdown"
        )

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "直接返回的 markdown")

    def test_parse_response_raises_when_markdown_blank(self):
        response = _make_response(body={"markdown": "   "})

        with self.assertRaisesRegex(ValueError, "markdown"):
            self._client()._parse_response(response)

    def test_parse_response_raises_when_body_empty(self):
        response = _make_response(body=None)

        with self.assertRaisesRegex(ValueError, "markdown"):
            self._client()._parse_response(response)


class FinixDocCacheTests(unittest.TestCase):
    def _make_chunk(
        self,
        root: Path,
        content: bytes = b"image-bytes",
        file_name: str = "doc.jpg",
    ) -> object:
        path = root / file_name
        # Phase 3 chunker reads the image header, so write a real JPEG.
        # Vary the pixel color by `content` hash so cache-key tests still
        # exercise distinct file contents.
        hue = sum(content) % 256
        Image.new("RGB", (16, 16), color=(hue, hue, hue)).save(path, format="JPEG")
        image = ImageRecord(file_name=file_name, path=path)
        return create_chunks(image)[0]

    def _client(
        self,
        cache_dir: Path | None,
        user_id: str = "finixA1001",
    ) -> FinixDocVLClient:
        return FinixDocVLClient(
            user_id=user_id,
            api_key="key",
            endpoint="https://example.invalid/api",
            timeout=30,
            max_retries=0,
            cache_dir=cache_dir,
        )

    def test_cache_key_is_stable_for_same_inputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(root)

            key_a = client._cache_key(chunk)
            key_b = client._cache_key(chunk)

            self.assertEqual(key_a, key_b)
            self.assertTrue(key_a.endswith(".md"))

    def test_cache_key_changes_with_user_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client_a = self._client(root, user_id="finixA1001")
            client_b = self._client(root, user_id="finixB2002")

            self.assertNotEqual(client_a._cache_key(chunk), client_b._cache_key(chunk))

    def test_cache_key_changes_with_file_content(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk_a = self._make_chunk(root, b"bytes-a", file_name="a.jpg")
            chunk_b = self._make_chunk(root, b"bytes-b", file_name="b.jpg")
            client = self._client(root)

            self.assertNotEqual(client._cache_key(chunk_a), client._cache_key(chunk_b))

    def test_write_and_read_cache_round_trip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            cache_dir = root / "cache"
            client = self._client(cache_dir)

            key = client._cache_key(chunk)
            client._write_cache(key, "# 标题\n\n正文")

            self.assertEqual(client._read_cache(key), "# 标题\n\n正文")

    def test_read_cache_returns_none_when_missing(self):
        with TemporaryDirectory() as tmp:
            client = self._client(Path(tmp))

            self.assertIsNone(client._read_cache("nonexistent.md"))

    def test_cache_disabled_returns_none_on_read(self):
        client = self._client(cache_dir=None)

        self.assertIsNone(client._read_cache("any.md"))

    def test_cache_disabled_write_is_noop(self):
        client = self._client(cache_dir=None)

        client._write_cache("any.md", "value")


class FinixDocParseChunkTests(unittest.TestCase):
    def _make_chunk(self, root: Path, file_name: str = "doc.jpg") -> object:
        path = root / file_name
        write_tiny_jpeg(path)
        image = ImageRecord(file_name=file_name, path=path)
        return create_chunks(image)[0]

    def _client(
        self,
        cache_dir: Path | None,
        max_retries: int = 2,
    ) -> FinixDocVLClient:
        return FinixDocVLClient(
            user_id="finixA1001",
            api_key="key",
            endpoint="https://example.invalid/api",
            timeout=30,
            max_retries=max_retries,
            cache_dir=cache_dir,
        )

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_returns_markdown_from_api(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.return_value = _make_response(body={"markdown": "# 标题"})

            markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# 标题")
            mock_post.assert_called_once()

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_writes_cache_on_success(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            cache_dir = root / "cache"
            client = self._client(cache_dir=cache_dir)
            mock_post.return_value = _make_response(body={"markdown": "# 标题"})

            client.parse_chunk(chunk)

            cached_files = list(cache_dir.iterdir())
            self.assertEqual(len(cached_files), 1)
            self.assertIn("# 标题", cached_files[0].read_text(encoding="utf-8"))

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_skips_api_when_cache_hit(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            cache_dir = root / "cache"
            client = self._client(cache_dir=cache_dir)
            key = client._cache_key(chunk)
            client._write_cache(key, "# 来自缓存")

            markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# 来自缓存")
            mock_post.assert_not_called()

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_sends_multipart_fields(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root, file_name="report.png")
            client = self._client(cache_dir=None)
            mock_post.return_value = _make_response(body={"markdown": "# ok"})

            client.parse_chunk(chunk)

            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertEqual(kwargs["data"]["userId"], "finixA1001")
            self.assertEqual(kwargs["data"]["apiKey"], "key")
            self.assertEqual(kwargs["data"]["fileName"], "report.png")
            self.assertEqual(kwargs["timeout"], 30)
            self.assertIn("file", kwargs["files"])

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_retries_on_transient_failure(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.side_effect = [
                requests_lib.exceptions.Timeout("timeout 1"),
                _make_response(body={"markdown": "# retry succeeded"}),
            ]

            markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# retry succeeded")
            self.assertEqual(mock_post.call_count, 2)

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_raises_when_all_attempts_fail(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.side_effect = requests_lib.exceptions.Timeout("always times out")

            with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
                client.parse_chunk(chunk)
            self.assertEqual(mock_post.call_count, 3)

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_retries_on_non_2xx(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.return_value = MagicMock(
                status_code=500, headers={}, text="server error"
            )

            with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
                client.parse_chunk(chunk)
            self.assertEqual(mock_post.call_count, 3)


def _build_args(**overrides: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "client": "mock",
        "gt_dir": None,
        "user_id": DEFAULT_USER_ID,
        "api_key": DEFAULT_API_KEY,
        "endpoint": DEFAULT_ENDPOINT,
        "timeout": DEFAULT_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "cache_dir": "none",
        "input_dir": "ignored",
        "output": "ignored",
        "log_level": "INFO",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class CreateClientTests(unittest.TestCase):
    def test_returns_mock_for_mock_choice(self):
        client = create_client(_build_args(client="mock"))

        self.assertIsInstance(client, MockVLClient)

    def test_returns_finixdoc_for_finixdoc_choice(self):
        client = create_client(_build_args(client="finixdoc", cache_dir="none"))

        self.assertIsInstance(client, FinixDocVLClient)
        self.assertIsNone(client.cache_dir)

    def test_converts_cache_dir_path_when_provided(self):
        with TemporaryDirectory() as tmp:
            client = create_client(_build_args(client="finixdoc", cache_dir=tmp))

            self.assertEqual(client.cache_dir, Path(tmp).resolve())

    def test_passes_user_id_and_endpoint_to_client(self):
        client = create_client(
            _build_args(
                client="finixdoc",
                user_id="finixC3003",
                endpoint="https://custom.invalid/api",
                cache_dir="none",
            )
        )

        self.assertEqual(client.user_id, "finixC3003")
        self.assertEqual(client.endpoint, "https://custom.invalid/api")


class FinixDocPipelineIntegrationTests(unittest.TestCase):
    @patch("src.document_restoration.vl_client.requests.post")
    def test_run_pipeline_with_finixdoc_client_writes_csv(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            write_tiny_jpeg(images / "doc.jpg")
            output = root / "submission.csv"
            mock_post.return_value = _make_response(body={"markdown": "# 真实解析"})

            client = FinixDocVLClient(
                user_id="finixA1001",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=10,
                max_retries=0,
                cache_dir=None,
            )
            results = run_pipeline(images, output, client)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].markdown, "# 真实解析")
            with output.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["ground_truth"], "# 真实解析")

    def test_main_cli_runs_with_finixdoc_client_via_cache(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            image_path = images / "doc.jpg"
            write_tiny_jpeg(image_path)
            output = root / "submission.csv"
            cache_dir = root / "cache"
            cache_dir.mkdir()

            seed_client = FinixDocVLClient(
                user_id="finixA1001",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=10,
                max_retries=0,
                cache_dir=cache_dir,
            )
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]
            seed_client._write_cache(seed_client._cache_key(chunk), "# 来自缓存")

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
                    "finixA1001",
                    "--api_key",
                    "key",
                    "--endpoint",
                    "https://example.invalid/api",
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
            self.assertEqual(rows[0]["ground_truth"], "# 来自缓存")


if __name__ == "__main__":
    unittest.main()
