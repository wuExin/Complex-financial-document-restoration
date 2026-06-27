# tests/restore/test_pipeline.py
"""pipeline 模块的单元测试。"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from PIL import Image

from src.restore.chunking import FixedHeightChunker
from src.restore.dedup import EditDistanceMerger
from src.restore.finix_client import MockFinixClient
from src.restore.pipeline import process_image
from src.restore.types import PipelineResult


def test_process_small_image_single_chunk():
    """小图只产 1 块，无 merge decision。"""
    img = Image.new("RGB", (1000, 1000))
    client = MockFinixClient(default_response="# Small image MD")
    chunker = FixedHeightChunker(threshold=8000)
    merger = EditDistanceMerger()

    result = process_image(
        image=img,
        image_id="test-small",
        client=client,
        chunker=chunker,
        merger=merger,
    )
    assert isinstance(result, PipelineResult)
    assert result.image_id == "test-small"
    assert result.image_shape == (1000, 1000)
    assert result.chunker_name == "fixed_height"
    assert len(result.chunks) == 1
    assert result.chunks[0].raw_markdown == "# Small image MD"
    assert result.merge_decisions == []
    assert result.final_markdown == "# Small image MD"
    assert result.elapsed_ms >= 0


def test_process_large_image_multiple_chunks():
    """大图切多块，并发调 client，最后 merge。"""
    img = Image.new("RGB", (1500, 15000))
    # 模拟每块返回不同内容
    def responder(image):
        # 用图像高度作为内容标识
        return f"# Chunk h={image.size[1]}"

    client = MockFinixClient(responder=responder)
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    merger = EditDistanceMerger()

    result = process_image(
        image=img,
        image_id="test-large",
        client=client,
        chunker=chunker,
        merger=merger,
    )
    # 15000 / 5000 步长 = 3 块
    assert len(result.chunks) == 3
    assert client.call_count == 3
    # final_markdown 包含所有块的内容（所有块都是 h=6000）
    assert result.final_markdown.count("h=6000") == 3
    # 有 2 个 merge decision（3 块两两相邻）
    assert len(result.merge_decisions) == 2


def test_process_image_includes_ground_truth_when_provided():
    img = Image.new("RGB", (100, 100))
    client = MockFinixClient(default_response="x")
    result = process_image(
        image=img,
        image_id="x",
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        ground_truth="# Truth",
    )
    assert result.ground_truth == "# Truth"


def test_process_image_handles_empty_chunks():
    """理论上不会发生，但 pipeline 应能优雅处理。"""
    img = Image.new("RGB", (100, 100))
    client = MockFinixClient(default_response="x")
    chunker = FixedHeightChunker()
    merger = EditDistanceMerger()
    # 用一个返回空列表的假 chunker
    fake_chunker = MagicMock()
    fake_chunker.chunk.return_value = []
    fake_chunker.name = "empty"

    result = process_image(
        image=img,
        image_id="x",
        client=client,
        chunker=fake_chunker,
        merger=merger,
    )
    assert result.chunks == []
    assert result.final_markdown == ""
