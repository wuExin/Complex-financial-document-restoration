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


def test_generate_thumbnail_creates_jpg(tmp_path: Path) -> None:
    from PIL import Image

    from gen_thumbs import generate_thumbnail

    src = tmp_path / "src.jpg"
    Image.new("RGB", (2000, 3000), (100, 150, 200)).save(src, "JPEG")
    dst = tmp_path / "out.jpg"

    ok = generate_thumbnail(src, dst)

    assert ok is True
    assert dst.exists()
    with Image.open(dst) as thumb:
        # Long edge should be capped near 240px
        assert max(thumb.size) <= 240
        assert thumb.size[0] == 160  # 2000/3000 * 240 = 160


def test_generate_thumbnail_handles_corrupt_image(tmp_path: Path) -> None:
    from gen_thumbs import generate_thumbnail

    src = tmp_path / "broken.jpg"
    src.write_bytes(b"not a real jpg")
    dst = tmp_path / "out.jpg"

    ok = generate_thumbnail(src, dst)

    assert ok is False
    assert not dst.exists()


def test_main_generates_thumbnails_and_manifest(
    sample_data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: running main() produces 4 thumbnails + manifest with 4 subsets."""
    import json

    import gen_thumbs

    outputs_dir = tmp_path / "outputs"

    monkeypatch.setattr(
        "sys.argv",
        [
            "gen_thumbs.py",
            "--data-dir",
            str(sample_data_dir),
            "--outputs-dir",
            str(outputs_dir),
        ],
    )
    gen_thumbs.main()

    manifest_path = outputs_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    assert "generated_at" in manifest
    assert set(manifest["subsets"].keys()) == {
        "train_long",
        "train_table",
        "eval_long",
        "eval_table",
    }
    for key, subset in manifest["subsets"].items():
        assert subset["count"] == 1
        assert len(subset["images"]) == 1
        thumb_rel = subset["images"][0]["thumb_path"]
        assert (outputs_dir / "thumbs" / thumb_rel).exists()


def test_main_errors_when_data_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gen_thumbs

    outputs_dir = tmp_path / "outputs"
    monkeypatch.setattr(
        "sys.argv",
        ["gen_thumbs.py", "--data-dir", str(tmp_path / "does_not_exist"), "--outputs-dir", str(outputs_dir)],
    )
    with pytest.raises(SystemExit) as excinfo:
        gen_thumbs.main()
    assert excinfo.value.code != 0
