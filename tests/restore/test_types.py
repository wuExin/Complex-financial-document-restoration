# tests/restore/test_types.py
"""types 模块的单元测试。"""
from __future__ import annotations

from PIL import Image

from src.restore.types import (
    Chunk,
    ChunkResult,
    MergeDecision,
    PipelineResult,
)


def test_chunk_construction():
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=50)
    assert c.bbox == (0, 0, 100, 200)
    assert c.overlap_top == 0
    assert c.overlap_bottom == 50


def test_chunk_to_dict_excludes_image():
    """image 字段不可 JSON 序列化，to_dict 必须排除。"""
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=0)
    d = c.to_dict()
    assert "image" not in d
    assert d["bbox"] == [0, 0, 100, 200]


def test_chunk_result_to_dict():
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=0)
    cr = ChunkResult(chunk=c, raw_markdown="# Hello", elapsed_ms=120, cached=False)
    d = cr.to_dict()
    assert d["raw_markdown"] == "# Hello"
    assert d["elapsed_ms"] == 120
    assert d["cached"] is False
    assert d["chunk"]["bbox"] == [0, 0, 100, 200]


def test_merge_decision_to_dict():
    md = MergeDecision(
        left_chunk_idx=0,
        right_chunk_idx=1,
        left_tail="tail text",
        right_head="head text",
        normalized_edit_distance=0.15,
        kept="merged",
    )
    d = md.to_dict()
    assert d["left_chunk_idx"] == 0
    assert d["kept"] == "merged"
    assert d["normalized_edit_distance"] == 0.15


def test_pipeline_result_to_dict():
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=0)
    cr = ChunkResult(chunk=c, raw_markdown="text", elapsed_ms=100, cached=False)
    pr = PipelineResult(
        image_id="test-uuid",
        image_shape=(100, 200),
        chunker_name="fixed_height",
        chunks=[cr],
        merge_decisions=[],
        final_markdown="text",
        ground_truth=None,
        elapsed_ms=100,
    )
    d = pr.to_dict()
    assert d["image_id"] == "test-uuid"
    assert d["image_shape"] == [100, 200]
    assert d["chunker_name"] == "fixed_height"
    assert len(d["chunks"]) == 1
    assert d["final_markdown"] == "text"
    assert d["ground_truth"] is None
