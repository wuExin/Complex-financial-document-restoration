"""Tests for src/gen_thumbs.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_discover_images_finds_all_four_subsets(sample_data_dir: Path) -> None:
    from gen_thumbs import discover_images, SUBSETS

    result = discover_images(sample_data_dir)

    assert set(result.keys()) == {"train_long", "train_table", "eval_long", "eval_table"}
    for key in result:
        assert result[key]["label"] == SUBSETS[key]["label"]
        assert len(result[key]["images"]) == 1


def test_discover_images_records_uuid_and_path(sample_data_dir: Path) -> None:
    from gen_thumbs import discover_images

    result = discover_images(sample_data_dir)
    img = result["train_long"]["images"][0]
    assert img["uuid"] == "aaaaaaaa-0000-0000-0000-000000000001"
    assert img["image_path"].endswith(
        "aaaaaaaa-0000-0000-0000-000000000001.jpg"
    )
    assert "size_bytes" in img and img["size_bytes"] > 0


def test_discover_images_handles_missing_subset_dir(tmp_path: Path) -> None:
    """If a subset dir is missing, return empty list for it (don't crash)."""
    from gen_thumbs import discover_images

    result = discover_images(tmp_path / "empty_data")
    assert result["train_long"]["images"] == []
    assert result["train_long"]["count"] == 0
