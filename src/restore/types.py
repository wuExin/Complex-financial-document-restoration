# src/restore/types.py
"""流水线各阶段传递的数据结构。

所有 dataclass 提供 to_dict() 以便序列化为 JSON（给浏览器 /api/restore 用）。
PIL.Image 不可 JSON 序列化，所有 to_dict 都排除 image 字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from PIL import Image


@dataclass
class Chunk:
    """切块后的一张子图。"""

    image: Image.Image
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) 在原图坐标系
    overlap_top: int  # 与上一块顶部的重叠像素数
    overlap_bottom: int  # 与下一块底部的重叠像素数

    def to_dict(self) -> dict:
        """返回不含 image 的可序列化字典。"""
        return {
            "bbox": list(self.bbox),
            "overlap_top": self.overlap_top,
            "overlap_bottom": self.overlap_bottom,
        }


@dataclass
class ChunkResult:
    """单块识别结果。"""

    chunk: Chunk
    raw_markdown: str  # FinixDoc-VL 原始返回
    elapsed_ms: int
    cached: bool  # 是否命中磁盘缓存

    def to_dict(self) -> dict:
        return {
            "chunk": self.chunk.to_dict(),
            "raw_markdown": self.raw_markdown,
            "elapsed_ms": self.elapsed_ms,
            "cached": self.cached,
        }


@dataclass
class MergeDecision:
    """相邻块的一次去重决策记录。"""

    left_chunk_idx: int
    right_chunk_idx: int
    left_tail: str  # 左块参与比对的尾部文本
    right_head: str  # 右块参与比对的头部文本
    normalized_edit_distance: float
    kept: Literal["left", "right", "merged"]  # 最终保留策略

    def to_dict(self) -> dict:
        return {
            "left_chunk_idx": self.left_chunk_idx,
            "right_chunk_idx": self.right_chunk_idx,
            "left_tail": self.left_tail,
            "right_head": self.right_head,
            "normalized_edit_distance": self.normalized_edit_distance,
            "kept": self.kept,
        }


@dataclass
class PipelineResult:
    """单图流水线完整结果（含中间结构）。"""

    image_id: str
    image_shape: tuple[int, int]  # (width, height)
    chunker_name: str
    chunks: list[ChunkResult]  # 按位置顺序
    merge_decisions: list[MergeDecision]
    final_markdown: str
    ground_truth: str | None  # 训练集才有
    elapsed_ms: int

    def to_dict(self) -> dict:
        return {
            "image_id": self.image_id,
            "image_shape": list(self.image_shape),
            "chunker_name": self.chunker_name,
            "chunks": [c.to_dict() for c in self.chunks],
            "merge_decisions": [m.to_dict() for m in self.merge_decisions],
            "final_markdown": self.final_markdown,
            "ground_truth": self.ground_truth,
            "elapsed_ms": self.elapsed_ms,
        }
