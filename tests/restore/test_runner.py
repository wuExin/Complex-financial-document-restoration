# tests/restore/test_runner.py
"""runner 模块的单元测试。"""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image

from src.restore.chunking import FixedHeightChunker
from src.restore.dedup import EditDistanceMerger
from src.restore.finix_client import MockFinixClient
from src.restore.runner import run_directory


def _make_image(path: Path, size=(1000, 1000)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 200, 200)).save(path, "JPEG")


def test_run_directory_writes_csv(tmp_path: Path):
    img_dir = tmp_path / "imgs"
    _make_image(img_dir / "a.jpg")
    _make_image(img_dir / "b.jpg")
    _make_image(img_dir / "c.jpg")

    out_csv = tmp_path / "out.csv"
    client = MockFinixClient(default_response="# MD")
    run_directory(
        image_dirs=[img_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=2,
    )
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 3
    file_names = {r["file_name"] for r in rows}
    assert file_names == {"a.jpg", "b.jpg", "c.jpg"}
    for r in rows:
        assert r["ground_truth"] == "# MD"


def test_run_directory_resumes_from_existing_csv(tmp_path: Path):
    """已存在的 CSV 中的图被跳过，不重复耗 API。"""
    img_dir = tmp_path / "imgs"
    _make_image(img_dir / "a.jpg")
    _make_image(img_dir / "b.jpg")

    out_csv = tmp_path / "out.csv"
    # 预写入 a 的结果
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["file_name", "ground_truth"])
        w.writerow(["a.jpg", "# Previous run"])

    client = MockFinixClient(default_response="# Fresh MD")
    run_directory(
        image_dirs=[img_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=1,
    )
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 2
    by_name = {r["file_name"]: r["ground_truth"] for r in rows}
    # a 保持原值（跳过）
    assert by_name["a.jpg"] == "# Previous run"
    # b 是新跑的
    assert by_name["b.jpg"] == "# Fresh MD"
    # 只调了 1 次 API
    assert client.call_count == 1


def test_run_directory_eval_mode_writes_per_image_md(tmp_path: Path):
    """--eval-mode 时除了 CSV 还把 final_markdown 落到 predictions/<id>.md。"""
    img_dir = tmp_path / "imgs"
    _make_image(img_dir / "uuid-1.jpg")
    _make_image(img_dir / "uuid-2.jpg")

    out_csv = tmp_path / "out.csv"
    pred_dir = tmp_path / "pred"
    client = MockFinixClient(default_response="# MD")
    run_directory(
        image_dirs=[img_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=2,
        eval_mode=True,
        predictions_dir=pred_dir,
    )
    assert (pred_dir / "uuid-1.md").exists()
    assert (pred_dir / "uuid-2.md").exists()
    assert (pred_dir / "uuid-1.md").read_text(encoding="utf-8") == "# MD"


def test_run_directory_handles_multiple_dirs(tmp_path: Path):
    """支持多目录输入（长文档 + 表格文档）。"""
    long_dir = tmp_path / "long"
    table_dir = tmp_path / "table"
    _make_image(long_dir / "L1.jpg")
    _make_image(table_dir / "T1.jpg")

    out_csv = tmp_path / "out.csv"
    client = MockFinixClient(default_response="# MD")
    run_directory(
        image_dirs=[long_dir, table_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=2,
    )
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 2
