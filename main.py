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
