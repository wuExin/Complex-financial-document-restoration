import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import chunk_storage
from .models import ImageChunk, ImageRecord


LOGGER = logging.getLogger(__name__)


STRIP_ASPECT_THRESHOLD = 3.0
PAGE_HEIGHT_RATIO = 1.414  # sqrt(2), A4 portrait
WHITE_ROW_THRESHOLD = 248
MIN_BAND_RATIO = 0.3
DOWNSCALE_WIDTH = 200
MAX_CHUNKS_PER_IMAGE = 100


@dataclass(frozen=True)
class ChunkerConfig:
    strip_aspect_threshold: float = STRIP_ASPECT_THRESHOLD
    page_height_ratio: float = PAGE_HEIGHT_RATIO
    chunk_cache_dir: Path | None = None


def create_chunks(
    image: ImageRecord, config: ChunkerConfig | None = None
) -> list[ImageChunk]:
    if config is None:
        config = ChunkerConfig()

    try:
        with Image.open(image.path) as pil_image:
            width, height = pil_image.size
    except Exception as exc:
        raise ChunkerError(f"Failed to read image header for {image.file_name}: {exc}") from exc

    aspect = height / width if width else float("inf")
    if aspect <= config.strip_aspect_threshold:
        return [
            ImageChunk(
                source=image,
                chunk_id=0,
                path=image.path,
                file_name=image.file_name,
                x=0,
                y=0,
                width=None,
                height=None,
            )
        ]

    return _split_strip(image, width, height, config)


def _split_strip(
    image: ImageRecord, width: int, height: int, config: ChunkerConfig
) -> list[ImageChunk]:
    with Image.open(image.path) as pil_image:
        cut_points = _detect_cut_points(pil_image, config)
    if len(cut_points) > MAX_CHUNKS_PER_IMAGE:
        LOGGER.warning(
            "Image %s produced %s chunks; truncated to %s",
            image.file_name,
            len(cut_points),
            MAX_CHUNKS_PER_IMAGE,
        )
        cut_points = cut_points[:MAX_CHUNKS_PER_IMAGE]
    return _materialize_chunks(image, width, cut_points, config)


def _materialize_chunks(
    image: ImageRecord,
    width: int,
    cut_points: list[tuple[int, int]],
    config: ChunkerConfig,
) -> list[ImageChunk]:
    cache_dir = config.chunk_cache_dir
    stem = image.path.stem
    chunks: list[ImageChunk] = []
    with Image.open(image.path) as pil_image:
        for idx, (y0, y1) in enumerate(cut_points):
            nn = f"{idx + 1:02d}"
            file_name = f"{stem}_p{nn}.jpg"
            if cache_dir is not None:
                path = cache_dir / file_name
            else:
                # No cache dir -> fall back to source path (single-chunk semantics)
                # Should not happen for strips, but stay safe.
                path = image.path
            if cache_dir is not None and not chunk_storage.file_exists(path):
                cropped = pil_image.crop((0, y0, width, y1))
                chunk_storage.write_jpeg(path, cropped)
            chunks.append(
                ImageChunk(
                    source=image,
                    chunk_id=idx,
                    path=path,
                    file_name=file_name,
                    x=0,
                    y=y0,
                    width=width,
                    height=y1 - y0,
                )
            )
    return chunks


def _detect_cut_points(image: Image.Image, config: ChunkerConfig) -> list[tuple[int, int]]:
    width, height = image.size
    expected_page_h = max(1, round(width * config.page_height_ratio))
    if height <= expected_page_h:
        return [(0, height)]

    bands = _find_white_bands(image, expected_page_h)
    if _bands_look_like_page_separators(bands, height, expected_page_h):
        return _cuts_from_bands(bands, height)

    return _fixed_height_cuts(height, expected_page_h)


def _find_white_bands(image: Image.Image, expected_page_h: int) -> list[tuple[int, int]]:
    width, height = image.size
    new_w = DOWNSCALE_WIDTH
    new_h = max(1, round(height * new_w / width))
    small = image.convert("L").resize((new_w, new_h), Image.BILINEAR)
    pixels = list(small.getdata())
    row_mean = [sum(pixels[r * new_w:(r + 1) * new_w]) / new_w for r in range(new_h)]

    min_band_downscaled = max(1, round(expected_page_h * new_w / width * MIN_BAND_RATIO))
    bands: list[tuple[int, int]] = []
    i = 0
    while i < new_h:
        if row_mean[i] >= WHITE_ROW_THRESHOLD:
            j = i
            while j < new_h and row_mean[j] >= WHITE_ROW_THRESHOLD:
                j += 1
            if j - i >= min_band_downscaled:
                y0 = round(i * height / new_h)
                y1 = round(j * height / new_h)
                bands.append((y0, y1))
            i = j
        else:
            i += 1
    return bands


def _bands_look_like_page_separators(
    bands: list[tuple[int, int]], height: int, expected_page_h: int
) -> bool:
    if len(bands) < 2:
        return False
    mids = [(b0 + b1) // 2 for b0, b1 in bands]
    distances = [mids[i + 1] - mids[i] for i in range(len(mids) - 1)]
    return all(expected_page_h * 0.5 <= d <= expected_page_h * 2.0 for d in distances)


def _cuts_from_bands(bands: list[tuple[int, int]], height: int) -> list[tuple[int, int]]:
    boundaries = [0] + [(b0 + b1) // 2 for b0, b1 in bands] + [height]
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def _fixed_height_cuts(height: int, expected_page_h: int) -> list[tuple[int, int]]:
    step = max(1, round(expected_page_h * 0.9))
    if height <= step:
        return [(0, height)]
    cuts: list[tuple[int, int]] = []
    y = 0
    while y < height:
        y1 = min(y + expected_page_h, height)
        cuts.append((y, y1))
        if y1 == height:
            break
        y += step
    # Note: do NOT cap here. _split_stream truncates and logs when len exceeds
    # MAX_CHUNKS_PER_IMAGE; capping internally would suppress that warning.
    return cuts


class ChunkerError(RuntimeError):
    pass
