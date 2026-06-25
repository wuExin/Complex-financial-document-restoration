"""Generate thumbnails and manifest for the AFAC image browser.

Usage:
    python src/gen_thumbs.py [--data-dir DATA] [--outputs-dir OUTPUTS]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import TypedDict

from PIL import Image


class ImageInfo(TypedDict):
    uuid: str
    image_path: str  # path relative to project root
    size_bytes: int


class SubsetInfo(TypedDict):
    label: str
    count: int
    images: list[ImageInfo]


# Subset key -> metadata.
# data_subdir is the path under data/ that contains the images/ folder.
SUBSETS: dict[str, dict[str, str]] = {
    "train_long": {
        "label": "训练长文档",
        "data_subdir": "AFAC 训练数据集/finixdocbench_huge_long_100",
    },
    "train_table": {
        "label": "训练表格",
        "data_subdir": "AFAC 训练数据集/finixdocbench_huge_table_100",
    },
    "eval_long": {
        "label": "评测长文档",
        "data_subdir": "AFAC A榜评测数据集(2)/finix_huge_long_rest_A",
    },
    "eval_table": {
        "label": "评测表格",
        "data_subdir": "AFAC A榜评测数据集(2)/finix_huge_table_rest_A",
    },
}


def discover_images(data_root: Path) -> dict[str, SubsetInfo]:
    """Scan data_root for each subset's images, returning a dict keyed by subset.

    `image_path` in each entry is relative to data_root.parent (i.e., project root).
    Missing subset directories yield an empty image list rather than an error.
    """
    project_root = data_root.parent
    result: dict[str, SubsetInfo] = {}
    for key, meta in SUBSETS.items():
        images_dir = data_root / meta["data_subdir"] / "images"
        images: list[ImageInfo] = []
        if images_dir.is_dir():
            for jpg in sorted(images_dir.glob("*.jpg")):
                images.append(
                    {
                        "uuid": jpg.stem,
                        "image_path": str(jpg.relative_to(project_root)).replace("\\", "/"),
                        "size_bytes": jpg.stat().st_size,
                    }
                )
        result[key] = {"label": meta["label"], "count": len(images), "images": images}
    return result


THUMBNAIL_LONG_EDGE = 240


def generate_thumbnail(src: Path, dst: Path, long_edge: int = THUMBNAIL_LONG_EDGE) -> bool:
    """Generate a thumbnail at `dst` with the long edge capped at `long_edge` px.

    Returns True on success, False if the source image cannot be decoded.
    """
    try:
        with Image.open(src) as img:
            img = img.convert("RGB")
            w, h = img.size
            scale = long_edge / max(w, h)
            if scale < 1.0:
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
            dst.parent.mkdir(parents=True, exist_ok=True)
            img.save(dst, "JPEG", quality=85)
        return True
    except Exception as exc:  # noqa: BLE001 - log and skip corrupt files
        print(f"[warn] skipped {src}: {exc}")
        return False
