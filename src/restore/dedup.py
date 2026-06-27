# src/restore/dedup.py
"""拼接去重策略：Merger Protocol + Phase 1 唯一实现 EditDistanceMerger。

算法（每对相邻块）：
1. 取左块尾部 window 字符 + 右块头部 window 字符
2. 算归一化编辑距离（levenshtein / max(len)）
3. 若 < threshold，视为重叠；用最长公共子串定位切点
4. 保留：左块到 LCS 结束 + 右块从 LCS 结束之后

否则直接拼接。
"""
from __future__ import annotations

from typing import Protocol

from .types import ChunkResult, MergeDecision


def _levenshtein(a: str, b: str) -> int:
    """标准动态规划编辑距离。"""
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


def _normalized_edit_distance(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    return _levenshtein(a, b) / max(len(a), len(b))


def _longest_common_substring(a: str, b: str) -> str:
    """返回 a 和 b 的最长公共子串。"""
    if not a or not b:
        return ""
    best_len = 0
    best_end_a = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len = cur[j]
                    best_end_a = i
        prev = cur
    return a[best_end_a - best_len : best_end_a]


class Merger(Protocol):
    """拼接去重接口。"""

    def merge(self, results: list[ChunkResult]) -> tuple[str, list[MergeDecision]]:
        ...


class EditDistanceMerger:
    """基于归一化编辑距离 + 最长公共子串的拼接去重。"""

    def __init__(self, window: int = 200, threshold: float = 0.3, min_lcs_len: int = 20):
        self.window = window
        self.threshold = threshold
        self.min_lcs_len = min_lcs_len

    def merge(self, results: list[ChunkResult]) -> tuple[str, list[MergeDecision]]:
        if not results:
            return "", []
        if len(results) == 1:
            return results[0].raw_markdown, []

        decisions: list[MergeDecision] = []
        accumulated = results[0].raw_markdown
        for i in range(1, len(results)):
            left = accumulated
            right = results[i].raw_markdown
            left_tail = left[-self.window :]
            right_head = right[: self.window]

            # Try different overlap lengths to find the best match
            max_overlap = min(self.window, len(left_tail), len(right_head))
            best_ned = 1.0
            best_overlap_len = 0

            for overlap_len in range(1, max_overlap + 1):
                candidate_left = left_tail[-overlap_len:]
                candidate_right = right_head[:overlap_len]
                candidate_ned = _normalized_edit_distance(candidate_left, candidate_right)
                if candidate_ned < best_ned:
                    best_ned = candidate_ned
                    best_overlap_len = overlap_len

            # Use the best NED found
            ned = best_ned

            if ned < self.threshold:
                lcs = _longest_common_substring(left_tail, right_head)
                if len(lcs) >= self.min_lcs_len:
                    lcs_end_in_right_head = right_head.rfind(lcs) + len(lcs)
                    splice_point = lcs_end_in_right_head
                    accumulated = left + right[splice_point:]
                    decisions.append(
                        MergeDecision(
                            left_chunk_idx=i - 1,
                            right_chunk_idx=i,
                            left_tail=left_tail,
                            right_head=right_head,
                            normalized_edit_distance=ned,
                            kept="merged",
                        )
                    )
                else:
                    accumulated = left + right
                    decisions.append(
                        MergeDecision(
                            left_chunk_idx=i - 1,
                            right_chunk_idx=i,
                            left_tail=left_tail,
                            right_head=right_head,
                            normalized_edit_distance=ned,
                            kept="left",
                        )
                    )
            else:
                accumulated = left + right
                decisions.append(
                    MergeDecision(
                        left_chunk_idx=i - 1,
                        right_chunk_idx=i,
                        left_tail=left_tail,
                        right_head=right_head,
                        normalized_edit_distance=ned,
                        kept="left",
                    )
                )
        return accumulated, decisions
