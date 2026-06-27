# src/restore/evaluate.py
"""本地评测：text_edit_distance + 目录扫描评测。

Phase 1 仅实现 Text Edit（归一化字符级编辑距离）。
Phase 2 会加 TEDS（表格结构相似度）。
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def text_edit_distance(pred: str, truth: str) -> float:
    """归一化字符级编辑距离。

    Returns:
        0.0 = 完全相同；1.0 = 完全不同
    """
    if not pred and not truth:
        return 0.0
    return _levenshtein(pred, truth) / max(len(pred), len(truth))


@dataclass
class EvalReport:
    """评测报告。"""

    per_sample: dict[str, float] = field(default_factory=dict)
    mean: float = 0.0
    median: float = 0.0
    min: float = 0.0
    max: float = 0.0
    n_samples: int = 0

    def to_dict(self) -> dict:
        return {
            "per_sample": self.per_sample,
            "mean": self.mean,
            "median": self.median,
            "min": self.min,
            "max": self.max,
            "n_samples": self.n_samples,
        }


def evaluate_directory(pred_dir: str | Path, truth_dir: str | Path) -> EvalReport:
    """对比预测目录与真值目录下的同名 .md 文件，逐对算 text_edit。

    预测目录下存在但真值目录缺失的样本会被跳过（不计入）。
    """
    pred_dir = Path(pred_dir)
    truth_dir = Path(truth_dir)
    per_sample: dict[str, float] = {}
    for pred_file in pred_dir.glob("*.md"):
        stem = pred_file.stem
        truth_file = truth_dir / f"{stem}.md"
        if not truth_file.exists():
            continue
        pred = pred_file.read_text(encoding="utf-8")
        truth = truth_file.read_text(encoding="utf-8")
        per_sample[stem] = text_edit_distance(pred, truth)

    if not per_sample:
        return EvalReport()

    scores = list(per_sample.values())
    return EvalReport(
        per_sample=per_sample,
        mean=statistics.mean(scores),
        median=statistics.median(scores),
        min=min(scores),
        max=max(scores),
        n_samples=len(scores),
    )


def write_report(report: EvalReport, out_dir: str | Path) -> Path:
    """把报告写到 out_dir/report.json + summary.txt，返回 out_dir。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "summary.txt").write_text(
        f"n={report.n_samples} | mean={report.mean:.4f} | "
        f"median={report.median:.4f} | min={report.min:.4f} | max={report.max:.4f}\n",
        encoding="utf-8",
    )
    return out_dir
