from dataclasses import dataclass

from PIL import Image

from .models import ImageChunk, ImageRecord


STRIP_ASPECT_THRESHOLD = 3.0
PAGE_HEIGHT_RATIO = 1.414  # sqrt(2), A4 portrait
WHITE_ROW_THRESHOLD = 248  # 0..255 grayscale mean
MIN_BAND_RATIO = 0.3       # band >= 30% of expected page height
DOWNSCALE_WIDTH = 200      # for row-brightness analysis
MAX_CHUNKS_PER_IMAGE = 100


@dataclass(frozen=True)
class ChunkerConfig:
    strip_aspect_threshold: float = STRIP_ASPECT_THRESHOLD
    page_height_ratio: float = PAGE_HEIGHT_RATIO
    chunk_cache_dir: "Path | None" = None  # resolved by pipeline; chunker treats None as "no cache"


def create_chunks(image: ImageRecord) -> list[ImageChunk]:
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
    pixels = list(small.getdata())  # row-major
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
                # Map back to original-y coordinates
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
    # Internal band-to-band distances
    mids = [(b0 + b1) // 2 for b0, b1 in bands]
    distances = [mids[i + 1] - mids[i] for i in range(len(mids) - 1)]
    return all(expected_page_h * 0.5 <= d <= expected_page_h * 2.0 for d in distances)


def _cuts_from_bands(bands: list[tuple[int, int]], height: int) -> list[tuple[int, int]]:
    # Use each band's midpoint as a cut boundary, plus image top and bottom
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
    return cuts[:MAX_CHUNKS_PER_IMAGE]
