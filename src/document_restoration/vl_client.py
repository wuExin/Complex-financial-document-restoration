from pathlib import Path
from typing import Protocol

from .models import ImageChunk


ALLOWED_FINIXDOC_USER_IDS = {
    "finixA1001",
    "finixB2002",
    "finixC3003",
    "finixD4004",
    "finixE5005",
}
DEFAULT_FINIXDOC_ENDPOINT = "https://finixdocapi.alipay.com/api/finix_doc/call_with_file"
DEFAULT_FINIXDOC_USER_ID = "finixB2002"
DEFAULT_FINIXDOC_API_KEY = "F935A5503983FB19F26FA3F00A94EBF9"
DEFAULT_FINIXDOC_TIMEOUT = 180.0
DEFAULT_FINIXDOC_MAX_RETRIES = 2
DEFAULT_FINIXDOC_CACHE_DIR = Path(".cache/finixdoc_vl")


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
        user_id: str = DEFAULT_FINIXDOC_USER_ID,
        api_key: str = DEFAULT_FINIXDOC_API_KEY,
        endpoint: str = DEFAULT_FINIXDOC_ENDPOINT,
        timeout: float = DEFAULT_FINIXDOC_TIMEOUT,
        max_retries: int = DEFAULT_FINIXDOC_MAX_RETRIES,
        cache_dir: Path | None = DEFAULT_FINIXDOC_CACHE_DIR,
    ) -> None:
        if user_id not in ALLOWED_FINIXDOC_USER_IDS:
            raise ValueError(f"Unsupported FinixDoc userId: {user_id}")
        if not api_key.strip():
            raise ValueError("apiKey must not be empty")
        if not endpoint.strip():
            raise ValueError("endpoint must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        if max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0")

        self.user_id = user_id
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = float(timeout)
        self.max_retries = max_retries
        self.cache_dir = cache_dir

    def parse_chunk(self, chunk: ImageChunk) -> str:
        raise NotImplementedError(
            "FinixDoc-VL HTTP calling is implemented in the next task."
        )
