import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock

from src.document_restoration.chunker import create_chunks
from src.document_restoration.models import ImageRecord
from src.document_restoration.vl_client import (
    ALLOWED_USER_IDS,
    DEFAULT_API_KEY,
    DEFAULT_CACHE_DIR,
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_ID,
    FinixDocVLClient,
)


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
        path.write_bytes(content)
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


if __name__ == "__main__":
    unittest.main()
