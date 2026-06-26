"""Shared pytest fixtures for the AFAC image browser tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image


def _make_test_image(path: Path, color=(200, 200, 200), size=(800, 600)) -> None:
    """Create a small valid JPG at `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG")


@pytest.fixture
def sample_data_dir(tmp_path: Path) -> Path:
    """Build a temp data/ dir mirroring the real layout, with 1 image per subset."""
    data_root = tmp_path / "data"
    subsets = {
        "AFAC 训练数据集/finixdocbench_huge_long_100": "aaaaaaaa-0000-0000-0000-000000000001",
        "AFAC 训练数据集/finixdocbench_huge_table_100": "bbbbbbbb-0000-0000-0000-000000000002",
        "AFAC A榜评测数据集(2)/finix_huge_long_rest_A": "cccccccc-0000-0000-0000-000000000003",
        "AFAC A榜评测数据集(2)/finix_huge_table_rest_A": "dddddddd-0000-0000-0000-000000000004",
    }
    for sub_dir, uuid in subsets.items():
        _make_test_image(data_root / sub_dir / "images" / f"{uuid}.jpg")
    return data_root


@pytest.fixture
def sample_outputs_dir(tmp_path: Path) -> Path:
    """Build a temp outputs/ dir with manifest.json + 4 thumbnails (one per subset)."""
    outputs = tmp_path / "outputs"
    thumbs_root = outputs / "thumbs"
    previews_root = outputs / "previews"

    subsets_data = {}
    for subset_key, label, uuid in [
        ("train_long", "训练长文档", "aaaaaaaa-0000-0000-0000-000000000001"),
        ("train_table", "训练表格", "bbbbbbbb-0000-0000-0000-000000000002"),
        ("eval_long", "评测长文档", "cccccccc-0000-0000-0000-000000000003"),
        ("eval_table", "评测表格", "dddddddd-0000-0000-0000-000000000004"),
    ]:
        thumb_rel = f"{subset_key}/{uuid}.jpg"
        _make_test_image(thumbs_root / thumb_rel, color=(150, 150, 200), size=(240, 320))
        _make_test_image(previews_root / thumb_rel, color=(180, 180, 220), size=(1600, 2000))
        src_rel = f"data/some_dir/{uuid}.jpg"
        _make_test_image(tmp_path / src_rel)
        subsets_data[subset_key] = {
            "label": label,
            "count": 1,
            "images": [
                {
                    "uuid": uuid,
                    "image_path": src_rel.replace("/", "/"),
                    "thumb_path": thumb_rel,
                    "preview_path": thumb_rel,
                    "size_bytes": (tmp_path / src_rel).stat().st_size,
                }
            ],
        }

    manifest = {
        "version": 1,
        "generated_at": "2026-06-25T12:00:00",
        "subsets": subsets_data,
    }
    (outputs / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return outputs
