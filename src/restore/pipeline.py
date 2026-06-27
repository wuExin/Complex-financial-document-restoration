# src/restore/pipeline.py
"""单图编排：切块 → 并发识别 → 拼接去重 → 装配 PipelineResult。

process_image 是库入口，浏览器 /api/restore 直接调用。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from PIL import Image

from .chunking import Chunker, FixedHeightChunker
from .dedup import EditDistanceMerger, Merger
from .finix_client import FinixClient, MockFinixClient
from .types import ChunkResult, PipelineResult


def process_image(
    image: Image.Image,
    image_id: str,
    client: FinixClient,
    chunker: Chunker | None = None,
    merger: Merger | None = None,
    ground_truth: str | None = None,
    chunk_concurrency: int = 4,
) -> PipelineResult:
    """处理单张图像，返回完整 PipelineResult。

    Args:
        image: 输入 PIL 图像
        image_id: 图像标识（UUID 或文件名 stem）
        client: FinixDoc-VL 客户端（HTTP 或 Mock）
        chunker: 切块器，默认 FixedHeightChunker()
        merger: 合并器，默认 EditDistanceMerger()
        ground_truth: 训练集真值，可选（评测/可视化用）
        chunk_concurrency: 单图内块级并发上限

    Returns:
        PipelineResult，含每块识别结果与合并决策
    """
    if chunker is None:
        chunker = FixedHeightChunker()
    if merger is None:
        merger = EditDistanceMerger()

    start = time.monotonic()
    chunks = chunker.chunk(image, image_id)

    # 块级并发识别
    def _recognize(idx: int) -> tuple[int, ChunkResult]:
        chunk = chunks[idx]
        t0 = time.monotonic()
        md = client.recognize(chunk.image)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return idx, ChunkResult(
            chunk=chunk, raw_markdown=md, elapsed_ms=elapsed_ms, cached=False
        )

    results: list[ChunkResult | None] = [None] * len(chunks)
    if chunks:
        with ThreadPoolExecutor(max_workers=min(chunk_concurrency, len(chunks))) as ex:
            for idx, cr in ex.map(_recognize, range(len(chunks))):
                results[idx] = cr
    chunk_results: list[ChunkResult] = [r for r in results if r is not None]

    final_markdown, decisions = merger.merge(chunk_results)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    return PipelineResult(
        image_id=image_id,
        image_shape=image.size,
        chunker_name=getattr(chunker, "name", "unknown"),
        chunks=chunk_results,
        merge_decisions=decisions,
        final_markdown=final_markdown,
        ground_truth=ground_truth,
        elapsed_ms=elapsed_ms,
    )
