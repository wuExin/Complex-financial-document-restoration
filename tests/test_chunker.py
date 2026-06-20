import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from src.document_restoration.chunker import ChunkerConfig, _detect_cut_points
from src.document_restoration.models import ImageRecord


def _make_strip(width: int, page_height: int, num_pages: int, gap_height: int = 120) -> Image.Image:
    """A tall strip of `num_pages` grey pages separated by white gaps.

    Fixtures use page_height ~= round(width * sqrt(2)) so the strip's pages
    match the algorithm's A4 heuristic. gap_height=120 is comfortably above
    the algorithm's MIN_BAND_RATIO threshold (~85 downscaled rows at width=200)
    so the white gaps reliably pass the band filter.
    """
    total_h = num_pages * page_height + (num_pages - 1) * gap_height
    img = Image.new("RGB", (width, total_h), color="white")
    draw = ImageDraw.Draw(img)
    for i in range(num_pages):
        y0 = i * (page_height + gap_height)
        draw.rectangle([0, y0, width - 1, y0 + page_height - 1], fill=(128, 128, 128))
    return img


def _make_uniform_strip(width: int, height: int) -> Image.Image:
    """A tall strip with no white gaps (forces fixed-height fallback)."""
    return Image.new("RGB", (width, height), color=(100, 100, 100))


class DetectCutPointsTests(unittest.TestCase):
    def test_three_pages_with_clear_gaps_cut_at_gap_midpoints(self):
        # width=200, page_h=283 -> A4 aspect matches the algorithm's heuristic.
        width, page_h, gap = 200, 283, 120
        img = _make_strip(width, page_h, 3, gap_height=gap)
        config = ChunkerConfig()

        cuts = _detect_cut_points(img, config)

        self.assertEqual(len(cuts), 3)
        for y0, y1 in cuts:
            self.assertGreater(y1, y0)
        # First chunk starts at 0, last chunk ends at image bottom
        self.assertEqual(cuts[0][0], 0)
        self.assertEqual(cuts[-1][1], img.size[1])
        # Internal boundaries should fall inside the gaps (y between pages)
        self.assertLess(cuts[0][1], page_h + gap)
        self.assertGreater(cuts[0][1], page_h)

    def test_uniform_strip_falls_back_to_fixed_height(self):
        width = 200
        # Width 200 -> expected_page_h = round(200 * 1.414) = 283
        # height = 1000 -> fixed-height fallback yields several ~283px chunks
        img = _make_uniform_strip(width, height=1000)
        config = ChunkerConfig()

        cuts = _detect_cut_points(img, config)

        self.assertGreater(len(cuts), 1)
        # Each cut's height should be roughly expected_page_h (allow overlap slack)
        expected_h = round(width * config.page_height_ratio)
        for y0, y1 in cuts[:-1]:  # ignore last (may be shorter)
            self.assertAlmostEqual(y1 - y0, expected_h, delta=expected_h * 0.2)

    def test_single_page_strip_returns_one_chunk(self):
        # page_h matches expected_page_h (283) so height <= expected_page_h -> single chunk
        img = _make_strip(200, 283, 1)
        config = ChunkerConfig()

        cuts = _detect_cut_points(img, config)

        self.assertEqual(cuts, [(0, img.size[1])])

    def test_respects_custom_page_height_ratio(self):
        # With a huge ratio, expected_page_h (2000) exceeds image height -> single chunk
        img = _make_strip(200, 283, 3, gap_height=120)
        config = ChunkerConfig(page_height_ratio=10.0)

        cuts = _detect_cut_points(img, config)

        self.assertEqual(cuts, [(0, img.size[1])])


if __name__ == "__main__":
    unittest.main()
