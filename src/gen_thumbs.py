"""Generate thumbnails and manifest for the AFAC image browser.

Usage:
    python src/gen_thumbs.py [--data-dir DATA] [--outputs-dir OUTPUTS]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from PIL import Image

# Real AFAC dataset images can be up to 400M pixels (large financial document scans).
# Disable PIL's decompression bomb check — these are trusted local files.
Image.MAX_IMAGE_PIXELS = None


class ImageInfo(TypedDict, total=False):
    uuid: str
    image_path: str  # path relative to project root
    size_bytes: int
    thumb_path: str  # added by main() after thumbnail generation
    preview_path: str  # browser-safe downsampled preview, added by main()


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
PREVIEW_LONG_EDGE = 2000  # browser-safe preview (Chrome decodes <img> up to ~100M px)


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


def write_manifest(outputs_dir: Path, subsets: dict[str, SubsetInfo]) -> Path:
    """Write the manifest JSON to outputs_dir/manifest.json and return its path."""
    manifest = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "subsets": subsets,
    }
    outputs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = outputs_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data",
        help="Path to the data/ directory (default: <project>/data)",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "outputs",
        help="Path to the outputs/ directory (default: <project>/outputs)",
    )
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"[error] data directory not found: {args.data_dir}", file=sys.stderr)
        sys.exit(2)

    subsets = discover_images(args.data_dir)
    total = sum(s["count"] for s in subsets.values())
    print(f"[info] discovered {total} images across {len(subsets)} subsets")

    thumbs_root = args.outputs_dir / "thumbs"
    previews_root = args.outputs_dir / "previews"
    for subset_key, subset in subsets.items():
        for img in subset["images"]:
            src = args.data_dir.parent / img["image_path"]
            uuid = img["uuid"]
            generate_thumbnail(src, thumbs_root / subset_key / f"{uuid}.jpg")
            # Browser-safe preview: real AFAC scans reach 1500x92024 (138M px),
            # which exceeds Chrome's <img> decode limit. Serve downsampled preview.
            generate_thumbnail(
                src, previews_root / subset_key / f"{uuid}.jpg", long_edge=PREVIEW_LONG_EDGE
            )

    # Add thumb_path + preview_path to each image record before writing manifest
    for subset_key, subset in subsets.items():
        for img in subset["images"]:
            uuid = img["uuid"]
            img["thumb_path"] = f"{subset_key}/{uuid}.jpg"
            img["preview_path"] = f"{subset_key}/{uuid}.jpg"

    manifest_path = write_manifest(args.outputs_dir, subsets)
    print(f"[info] wrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()
