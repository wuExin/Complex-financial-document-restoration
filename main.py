import argparse
import logging
from pathlib import Path

from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import (
    DEFAULT_FINIXDOC_API_KEY,
    DEFAULT_FINIXDOC_CACHE_DIR,
    DEFAULT_FINIXDOC_ENDPOINT,
    DEFAULT_FINIXDOC_MAX_RETRIES,
    DEFAULT_FINIXDOC_TIMEOUT,
    DEFAULT_FINIXDOC_USER_ID,
    FinixDocVLClient,
    MockVLClient,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MVP document restoration pipeline.")
    parser.add_argument("--input_dir", required=True, help="Directory containing input images.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument(
        "--gt_dir",
        default=None,
        help="Optional directory containing ground-truth Markdown files.",
    )
    parser.add_argument(
        "--client",
        choices=["mock", "finixdoc"],
        default="mock",
        help="VL client implementation.",
    )
    parser.add_argument("--user_id", default=DEFAULT_FINIXDOC_USER_ID, help="FinixDoc whitelist user ID.")
    parser.add_argument("--api_key", default=DEFAULT_FINIXDOC_API_KEY, help="FinixDoc API key.")
    parser.add_argument("--endpoint", default=DEFAULT_FINIXDOC_ENDPOINT, help="FinixDoc API endpoint.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_FINIXDOC_TIMEOUT, help="FinixDoc request timeout in seconds.")
    parser.add_argument("--max_retries", type=int, default=DEFAULT_FINIXDOC_MAX_RETRIES, help="FinixDoc request retry count.")
    parser.add_argument(
        "--cache_dir",
        default=str(DEFAULT_FINIXDOC_CACHE_DIR),
        help="Directory for FinixDoc response cache. Use an empty string to disable cache.",
    )
    parser.add_argument("--log_level", default="INFO", help="Python logging level.")
    return parser


def create_client(
    client_name: str,
    gt_dir: str | None,
    user_id: str = DEFAULT_FINIXDOC_USER_ID,
    api_key: str = DEFAULT_FINIXDOC_API_KEY,
    endpoint: str = DEFAULT_FINIXDOC_ENDPOINT,
    timeout: float = DEFAULT_FINIXDOC_TIMEOUT,
    max_retries: int = DEFAULT_FINIXDOC_MAX_RETRIES,
    cache_dir: str | None = str(DEFAULT_FINIXDOC_CACHE_DIR),
):
    if client_name == "mock":
        return MockVLClient(Path(gt_dir) if gt_dir else None)
    if client_name == "finixdoc":
        return FinixDocVLClient(
            user_id=user_id,
            api_key=api_key,
            endpoint=endpoint,
            timeout=timeout,
            max_retries=max_retries,
            cache_dir=Path(cache_dir) if cache_dir else None,
        )
    raise ValueError(f"Unsupported client: {client_name}")


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = create_client(
        args.client,
        args.gt_dir,
        args.user_id,
        args.api_key,
        args.endpoint,
        args.timeout,
        args.max_retries,
        args.cache_dir,
    )
    run_pipeline(Path(args.input_dir), Path(args.output), client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
