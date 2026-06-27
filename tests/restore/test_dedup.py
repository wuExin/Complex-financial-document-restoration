# tests/restore/test_dedup.py
"""dedup 模块的单元测试。"""
from __future__ import annotations

from PIL import Image

from src.restore.dedup import EditDistanceMerger, Merger
from src.restore.types import Chunk, ChunkResult


def _make_chunk_result(text: str, idx: int = 0) -> ChunkResult:
    img = Image.new("RGB", (100, 100))
    return ChunkResult(
        chunk=Chunk(image=img, bbox=(0, idx * 100, 100, (idx + 1) * 100),
                    overlap_top=0, overlap_bottom=0),
        raw_markdown=text,
        elapsed_ms=10,
        cached=False,
    )


def test_no_overlap_just_concatenates():
    merger = EditDistanceMerger(window=200, threshold=0.3)
    results = [
        _make_chunk_result("Hello world.", 0),
        _make_chunk_result("Goodbye world.", 1),
    ]
    merged, decisions = merger.merge(results)
    assert "Hello world." in merged
    assert "Goodbye world." in merged
    assert len(decisions) == 1
    assert decisions[0].kept == "left"


def test_full_overlap_dedups():
    merger = EditDistanceMerger(window=200, threshold=0.3)
    overlap_text = "This is the overlapping tail content."
    left = "Header content.\n\n" + overlap_text
    right = overlap_text + "\n\nFooter content."
    results = [_make_chunk_result(left, 0), _make_chunk_result(right, 1)]
    merged, decisions = merger.merge(results)
    assert merged.count(overlap_text) == 1
    assert "Header content." in merged
    assert "Footer content." in merged
    assert decisions[0].kept == "merged"
    assert decisions[0].normalized_edit_distance < 0.3


def test_three_chunks_merges_sequentially():
    merger = EditDistanceMerger(window=200, threshold=0.3)
    results = [
        _make_chunk_result("AAA common1", 0),
        _make_chunk_result("common1 BBB common2", 1),
        _make_chunk_result("common2 CCC", 2),
    ]
    merged, decisions = merger.merge(results)
    assert len(decisions) == 2
    assert "AAA" in merged
    assert "BBB" in merged
    assert "CCC" in merged


def test_single_chunk_no_decisions():
    merger = EditDistanceMerger()
    results = [_make_chunk_result("only one chunk", 0)]
    merged, decisions = merger.merge(results)
    assert merged == "only one chunk"
    assert decisions == []


def test_protocol_satisfied():
    merger: Merger = EditDistanceMerger()
    assert hasattr(merger, "merge")


def test_empty_input_returns_empty():
    merger = EditDistanceMerger()
    merged, decisions = merger.merge([])
    assert merged == ""
    assert decisions == []
