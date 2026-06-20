"""File I/O for chunked images. Knows nothing about cut points or ImageChunk metadata."""

import logging
from pathlib import Path

from PIL import Image


LOGGER = logging.getLogger(__name__)


def file_exists(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def write_jpeg(path: Path, pil_image: Image.Image, quality: int = 90) -> None:
    if file_exists(path):
        LOGGER.info("Skipping write; chunk already cached at %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pil_image.convert("RGB").save(path, format="JPEG", quality=quality)


def clear(source_stem: str, cache_dir: Path) -> None:
    for entry in cache_dir.iterdir():
        if entry.is_file() and entry.name.startswith(f"{source_stem}_p") and entry.suffix == ".jpg":
            try:
                entry.unlink()
            except OSError:
                LOGGER.warning("Failed to remove %s", entry, exc_info=True)
