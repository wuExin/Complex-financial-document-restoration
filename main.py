import argparse
import logging
from pathlib import Path

from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import FinixDocVLClient, MockVLClient


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
