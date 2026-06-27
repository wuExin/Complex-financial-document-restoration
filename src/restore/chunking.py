# src/restore/chunking.py
"""切块策略：Chunker Protocol + Phase 1 唯一实现 FixedHeightChunker。

Phase 2 会新增 LayoutAwareChunker（用 PP-Structure），实现同一个 Protocol，
pipeline 不需要改任何代码，只换 chunker 实例。
"""
from __future__ import annotations

from typing import Protocol

from PIL import Image

from .types import Chunk


class Chunker(Protocol):
    """切块策略接口。"""

    def chunk(self, image: Image.Image, image_id: str) -> list[Chunk]:
        ...


class FixedHeightChunker:
    """按固定高度切块。

    若 max(w, h) ≤ threshold，返回单块（整图）。
    否则沿高度方向以 (chunk_height - overlap) 为步长切片，最后一块对齐到原图底部。

    长文档与表格文档统一策略：始终保留全宽，沿高度切。
    """

    def __init__(
        self,
        threshold: int = 8000,
        chunk_height: int = 6000,
        overlap: int = 1000,
    ):
        if overlap >= chunk_height:
            raise ValueError(f"overlap ({overlap}) 必须 < chunk_height ({chunk_height})")
        self.threshold = threshold
        self.chunk_height = chunk_height
        self.overlap = overlap

    @property
    def name(self) -> str:
        return "fixed_height"

    def chunk(self, image: Image.Image, image_id: str) -> list[Chunk]:
        w, h = image.size
        if max(w, h) <= self.threshold:
            return [
                Chunk(
                    image=image,
                    bbox=(0, 0, w, h),
                    overlap_top=0,
                    overlap_bottom=0,
                )
            ]

        step = self.chunk_height - self.overlap

        # Calculate chunk start positions
        positions: list[int] = []
        y = 0
        while y < h:
            positions.append(y)
            if y + self.chunk_height >= h:
                break
            # Look ahead: check if next step would leave room for a full chunk
            next_y = y + step
            if next_y + self.chunk_height > h:
                # Next step would overshoot, jump to last valid position
                y = h - self.chunk_height
            else:
                y = next_y

        chunks: list[Chunk] = []
        for idx, y0 in enumerate(positions):
            y1 = min(y0 + self.chunk_height, h)
            cropped = image.crop((0, y0, w, y1))
            overlap_top = self.overlap if idx > 0 else 0
            is_last = (y1 == h)
            overlap_bottom = 0 if is_last else self.overlap
            chunks.append(
                Chunk(
                    image=cropped,
                    bbox=(0, y0, w, y1),
                    overlap_top=overlap_top,
                    overlap_bottom=overlap_bottom,
                )
            )
        return chunks
