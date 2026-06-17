import hashlib
import logging
from pathlib import Path
from typing import Protocol

import requests

from .models import ImageChunk


LOGGER = logging.getLogger(__name__)


ALLOWED_USER_IDS = frozenset(
    {"finixA1001", "finixB2002", "finixC3003", "finixD4004", "finixE5005"}
)
DEFAULT_USER_ID = "finixB2002"
DEFAULT_API_KEY = "F935A5503983FB19F26FA3F00A94EBF9"
DEFAULT_ENDPOINT = "https://finixdocapi.alipay.com/api/finix_doc/call_with_file"
DEFAULT_TIMEOUT = 180
DEFAULT_MAX_RETRIES = 2
DEFAULT_CACHE_DIR = Path(".cache/finixdoc_vl")


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
    def __init__(
        self,
        user_id: str,
        api_key: str,
        endpoint: str,
        timeout: float,
        max_retries: int,
        cache_dir: Path | None,
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

        self.user_id = user_id
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_dir = cache_dir.expanduser().resolve() if cache_dir else None

    def _parse_response(self, response: requests.Response) -> str:
        content_type = response.headers.get("Content-Type", "")
        body = response.text or ""

        looks_like_json = (
            "application/json" in content_type
            or body.lstrip().startswith(("{", "["))
        )

        if looks_like_json:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            extracted = self._extract_markdown(payload)
            if extracted is not None:
                return extracted
            # JSON-shaped body with no recognizable markdown field is a hard error;
            # never fall back to dumping raw JSON as the document text.
            raise ValueError("Response did not contain parseable markdown.")

        if body.strip():
            return body.strip()

        raise ValueError("Response did not contain parseable markdown.")

    @staticmethod
    def _extract_markdown(payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None

        top = payload.get("markdown")
        if isinstance(top, str) and top.strip():
            return top.strip()

        data = payload.get("data")
        if isinstance(data, dict):
            inner = data.get("markdown")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()

        result = payload.get("result")
        if isinstance(result, str) and result.strip():
            return result.strip()

        if isinstance(data, str) and data.strip():
            return data.strip()

        return None

    def parse_chunk(self, chunk: ImageChunk) -> str:
        raise NotImplementedError(
            "FinixDocVLClient.parse_chunk will be implemented in a later task."
        )
