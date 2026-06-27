# src/restore/runner.py
"""批处理 runner：图级并发 + 单 writer 线程 + 断点续跑。

- 多目录输入：合并扫描所有目录的 *.jpg
- 断点续跑：output_csv 已存在的 file_name 跳过
- 单 writer：所有 worker 把结果投到 Queue，单一 writer 线程串行写 CSV
- eval_mode：额外把 final_markdown 落到 predictions_dir/<id>.md
"""
from __future__ import annotations

import csv
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from PIL import Image

from .chunking import Chunker, FixedHeightChunker
from .dedup import EditDistanceMerger, Merger
from .finix_client import FinixClient, MockFinixClient
from .pipeline import process_image


def _load_done_set(output_csv: Path) -> set[str]:
    """读 CSV 中已有的 file_name，用于断点续跑。"""
    if not output_csv.exists():
        return set()
    done: set[str] = set()
    with output_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "file_name" in row and row["file_name"]:
                done.add(row["file_name"])
    return done


def _ensure_csv_header(output_csv: Path) -> None:
    """CSV 不存在时写表头。存在时不破坏。"""
    if output_csv.exists():
        return
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["file_name", "ground_truth"])


def _scan_images(image_dirs: list[Path]) -> list[Path]:
    images: list[Path] = []
    for d in image_dirs:
        images.extend(sorted(Path(d).glob("*.jpg")))
        images.extend(sorted(Path(d).glob("*.png")))
    return images


def run_directory(
    image_dirs: list[Path | str],
    output_csv: Path | str,
    client: Optional[FinixClient] = None,
    chunker: Optional[Chunker] = None,
    merger: Optional[Merger] = None,
    max_workers: int = 8,
    time_budget_seconds: float = 2.8 * 3600,
    eval_mode: bool = False,
    predictions_dir: Path | str | None = None,
) -> dict:
    """批量跑流水线，写 CSV。

    Args:
        image_dirs: 图像目录列表
        output_csv: 输出 CSV 路径
        client: FinixClient（默认 MockFinixClient；生产应传 HTTPFinixClient）
        chunker: 切块器
        merger: 合并器
        max_workers: 图级并发上限
        time_budget_seconds: 时间预算，超过则停止派发新图（已派发的会完成）
        eval_mode: 是否额外写 predictions/<id>.md（评测用）
        predictions_dir: eval_mode 时的输出目录

    Returns:
        统计字典 {processed, skipped, failed, elapsed_s}
    """
    if client is None:
        client = MockFinixClient()
    if chunker is None:
        chunker = FixedHeightChunker()
    if merger is None:
        merger = EditDistanceMerger()

    output_csv = Path(output_csv)
    image_dirs_p = [Path(d) for d in image_dirs]
    images = _scan_images(image_dirs_p)

    _ensure_csv_header(output_csv)
    done = _load_done_set(output_csv)
    todo = [p for p in images if p.name not in done]

    print(f"[runner] total={len(images)} done={len(done)} todo={len(todo)}",
          file=sys.stderr)

    result_queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
    predictions_dir_p = Path(predictions_dir) if predictions_dir else None
    if eval_mode and predictions_dir_p:
        predictions_dir_p.mkdir(parents=True, exist_ok=True)

    stop_event = threading.Event()
    stats = {"processed": 0, "skipped": len(done), "failed": 0}

    def writer_thread() -> None:
        with output_csv.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            while True:
                item = result_queue.get()
                if item is None:
                    break
                file_name, md = item
                w.writerow([file_name, md])
                f.flush()
                if eval_mode and predictions_dir_p:
                    stem = Path(file_name).stem
                    (predictions_dir_p / f"{stem}.md").write_text(
                        md, encoding="utf-8"
                    )

    writer = threading.Thread(target=writer_thread, daemon=True)
    writer.start()

    def process_one(img_path: Path) -> tuple[str, str]:
        try:
            img = Image.open(img_path)
            img.load()
            result = process_image(
                image=img,
                image_id=img_path.stem,
                client=client,
                chunker=chunker,
                merger=merger,
            )
            return img_path.name, result.final_markdown
        except Exception as e:  # noqa: BLE001
            print(f"[runner] FAIL {img_path.name}: {e}", file=sys.stderr)
            return img_path.name, ""

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(process_one, p): p for p in todo}
        for fut in as_completed(future_map):
            if stop_event.is_set():
                break
            file_name, md = fut.result()
            result_queue.put((file_name, md))
            if md:
                stats["processed"] += 1
            else:
                stats["failed"] += 1
            done_count = stats["processed"] + stats["failed"] + stats["skipped"]
            elapsed = time.monotonic() - start
            print(
                f"[runner] {done_count}/{len(images)} | "
                f"elapsed={elapsed:.0f}s | "
                f"current={file_name}",
                file=sys.stderr,
            )
            if elapsed > time_budget_seconds:
                print("[runner] time budget exceeded, stopping new dispatch",
                      file=sys.stderr)
                stop_event.set()

    result_queue.put(None)
    writer.join(timeout=5)
    stats["elapsed_s"] = time.monotonic() - start
    return stats
