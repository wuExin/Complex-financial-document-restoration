# tests/restore/test_evaluate.py
"""evaluate 模块的单元测试。"""
from __future__ import annotations

from pathlib import Path

from src.restore.evaluate import (
    EvalReport,
    evaluate_directory,
    text_edit_distance,
)


def test_identical_strings_distance_zero():
    assert text_edit_distance("hello", "hello") == 0.0


def test_completely_different_strings_distance_one():
    # 完全无公共字符（长度对齐）
    assert text_edit_distance("aaaa", "bbbb") == 1.0


def test_one_substitution():
    # hello vs hallo: 1 个替换 / 长度 5 = 0.2
    assert text_edit_distance("hello", "hallo") == 0.2


def test_empty_strings():
    assert text_edit_distance("", "") == 0.0


def test_one_empty_other_full():
    assert text_edit_distance("", "abc") == 1.0
    assert text_edit_distance("abc", "") == 1.0


def test_evaluate_directory(tmp_path: Path):
    pred_dir = tmp_path / "pred"
    truth_dir = tmp_path / "truth"
    pred_dir.mkdir()
    truth_dir.mkdir()

    # 两个样本
    (pred_dir / "uuid-1.md").write_text("hello world", encoding="utf-8")
    (truth_dir / "uuid-1.md").write_text("hello world", encoding="utf-8")
    (pred_dir / "uuid-2.md").write_text("hallo world", encoding="utf-8")
    (truth_dir / "uuid-2.md").write_text("hello world", encoding="utf-8")

    report = evaluate_directory(str(pred_dir), str(truth_dir))
    assert isinstance(report, EvalReport)
    assert len(report.per_sample) == 2
    # uuid-1 完美
    assert report.per_sample["uuid-1"] == 0.0
    # uuid-2 1 替换 / 11 = 约 0.09
    assert 0.05 < report.per_sample["uuid-2"] < 0.15
    # 均值在两者之间
    assert report.mean > 0


def test_evaluate_directory_missing_truth_skipped(tmp_path: Path):
    pred_dir = tmp_path / "pred"
    truth_dir = tmp_path / "truth"
    pred_dir.mkdir()
    truth_dir.mkdir()
    (pred_dir / "uuid-1.md").write_text("x", encoding="utf-8")
    (truth_dir / "uuid-1.md").write_text("x", encoding="utf-8")
    (pred_dir / "uuid-2.md").write_text("y", encoding="utf-8")
    # uuid-2 没有 truth

    report = evaluate_directory(str(pred_dir), str(truth_dir))
    assert "uuid-1" in report.per_sample
    assert "uuid-2" not in report.per_sample
