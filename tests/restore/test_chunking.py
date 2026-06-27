# tests/restore/test_chunking.py
"""chunking 模块的单元测试。"""
from __future__ import annotations

from PIL import Image

from src.restore.chunking import Chunker, FixedHeightChunker


def test_small_image_returns_single_chunk():
    img = Image.new("RGB", (1000, 2000))
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    assert len(chunks) == 1
    assert chunks[0].bbox == (0, 0, 1000, 2000)
    assert chunks[0].overlap_top == 0
    assert chunks[0].overlap_bottom == 0


def test_tall_image_chunks_vertically():
    img = Image.new("RGB", (1500, 15000))
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    assert len(chunks) == 3
    for c in chunks:
        assert c.bbox[0] == 0
        assert c.bbox[2] == 1500
    assert chunks[0].bbox[1] == 0
    assert chunks[0].bbox[3] == 6000
    assert chunks[0].overlap_top == 0
    assert chunks[0].overlap_bottom == 1000
    assert chunks[-1].bbox[3] == 15000
    assert chunks[-1].overlap_top == 1000
    assert chunks[-1].overlap_bottom == 0


def test_wide_table_image_chunks_vertically_too():
    img = Image.new("RGB", (9000, 9000))
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    assert len(chunks) == 2
    for c in chunks:
        assert c.bbox[2] == 9000


def test_step_is_chunk_height_minus_overlap():
    img = Image.new("RGB", (1000, 20000))
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    assert chunks[0].bbox == (0, 0, 1000, 6000)
    assert chunks[1].bbox == (0, 5000, 1000, 11000)
    assert chunks[2].bbox == (0, 10000, 1000, 16000)
    assert chunks[3].bbox == (0, 14000, 1000, 20000)
    assert chunks[1].overlap_top == 1000
    assert chunks[1].overlap_bottom == 1000


def test_protocol_satisfied():
    chunker: Chunker = FixedHeightChunker()
    img = Image.new("RGB", (100, 100))
    chunks = chunker.chunk(img, "id")
    assert isinstance(chunks, list)
