"""命令行入口：python -m src.restore <command> [args]

Commands:
  run <images_dir> [<images_dir>...] --out <csv>
      批处理跑流水线，写 CSV。需要 FINIX_USER_ID / FINIX_API_KEY 环境变量。

  eval <pred_dir> <truth_dir>
      本地评测，输出到 outputs/eval/<timestamp>/
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .chunking import FixedHeightChunker
from .config import Config
from .dedup import EditDistanceMerger
from .evaluate import evaluate_directory, write_report
from .finix_client import HTTPFinixClient
from .runner import run_directory


def cmd_run(args: argparse.Namespace) -> int:
    cfg = Config.from_env(load_dotenv=True)
    if not cfg.finix_user_id or not cfg.finix_api_key:
        print(
            "ERROR: FINIX_USER_ID / FINIX_API_KEY not set. "
            "Get them from DingTalk group 179205019946 and put in .env",
            file=sys.stderr,
        )
        return 2

    client = HTTPFinixClient(
        user_id=cfg.finix_user_id,
        api_key=cfg.finix_api_key,
        cache_dir=cfg.cache_dir,
        max_concurrency=cfg.concurrency,
    )
    chunker = FixedHeightChunker(
        threshold=cfg.chunk_threshold,
        chunk_height=cfg.chunk_height,
        overlap=cfg.chunk_overlap,
    )
    stats = run_directory(
        image_dirs=args.images,
        output_csv=args.out,
        client=client,
        chunker=chunker,
        merger=EditDistanceMerger(),
        max_workers=cfg.concurrency,
        eval_mode=args.eval_mode,
        predictions_dir=cfg.predictions_dir if args.eval_mode else None,
    )
    print(f"[done] {stats}", file=sys.stderr)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    report = evaluate_directory(args.pred_dir, args.truth_dir)
    timestamp = time.strftime("%Y-%m-%d-%H%M%S")
    out_dir = Config.from_env().eval_dir / timestamp
    write_report(report, out_dir)
    print(f"[done] report written to {out_dir}", file=sys.stderr)
    print(f"  n={report.n_samples} mean={report.mean:.4f} "
          f"median={report.median:.4f}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.restore")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="batch run pipeline → CSV")
    p_run.add_argument("images", nargs="+", type=Path, help="image directories")
    p_run.add_argument("--out", type=Path, required=True, help="output CSV path")
    p_run.add_argument(
        "--eval-mode", action="store_true",
        help="also write predictions/<id>.md for local evaluation",
    )
    p_run.set_defaults(func=cmd_run)

    p_eval = sub.add_parser("eval", help="local evaluation")
    p_eval.add_argument("pred_dir", type=Path)
    p_eval.add_argument("truth_dir", type=Path)
    p_eval.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
