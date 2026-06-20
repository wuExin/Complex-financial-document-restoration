import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from src.document_restoration.chunker import (
    ChunkerConfig,
    ChunkerError,
    _detect_cut_points,
    create_chunks,
)
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


class CreateChunksIntegrationTests(unittest.TestCase):
    def _save_image_record(self, tmp: str, name: str, img: Image.Image) -> ImageRecord:
        path = Path(tmp) / name
        img.save(path, format="JPEG")
        return ImageRecord(file_name=name, path=path)

    def test_short_image_returns_single_chunk_pointing_at_source(self):
        with TemporaryDirectory() as tmp:
            img = Image.new("RGB", (400, 300), color=(50, 50, 50))
            record = self._save_image_record(tmp, "page.jpg", img)
            config = ChunkerConfig()

            chunks = create_chunks(record, config)

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].path, record.path)
            self.assertEqual(chunks[0].file_name, "page.jpg")
            self.assertIsNone(chunks[0].width)

    def test_tall_image_splits_and_writes_chunk_files(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "chunks"
            # NOTE: gap_height=200 (not the plan's 120). At width=400 the
            # downscaled band is only ~60 rows, below MIN_BAND_RATIO's
            # min_band_downscaled=85 threshold, so the band filter rejects
            # the gaps and the algorithm falls back to fixed-height cuts
            # (yielding 4 chunks instead of 3). gap_height=200 keeps the
            # downscaled band at ~100 rows and yields the expected 3 chunks.
            strip = _make_strip(400, page_height=600, num_pages=3, gap_height=200)
            record = self._save_image_record(tmp, "tall.jpg", strip)
            config = ChunkerConfig(chunk_cache_dir=cache_dir)

            chunks = create_chunks(record, config)

            self.assertEqual(len(chunks), 3)
            for idx, chunk in enumerate(chunks):
                self.assertEqual(chunk.chunk_id, idx)
                self.assertEqual(chunk.source, record)
                self.assertTrue(chunk.path.exists(), f"chunk file missing: {chunk.path}")
                self.assertTrue(chunk.path.name.startswith("tall_p"))
                self.assertTrue(chunk.path.name.endswith(".jpg"))
                self.assertIsNotNone(chunk.x)
                self.assertIsNotNone(chunk.y)
                self.assertIsNotNone(chunk.width)
                self.assertIsNotNone(chunk.height)
                with Image.open(chunk.path) as im:
                    self.assertEqual(im.size, (chunk.width, chunk.height))

    def test_reuses_cached_chunks_without_rewriting(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "chunks"
            # gap_height=200 for the same reason as test_tall_image (see above).
            strip = _make_strip(400, page_height=600, num_pages=2, gap_height=200)
            record = self._save_image_record(tmp, "tall.jpg", strip)
            config = ChunkerConfig(chunk_cache_dir=cache_dir)

            first_chunks = create_chunks(record, config)
            # Tamper with mtime to detect rewrite
            import os
            for path in [c.path for c in first_chunks]:
                os.utime(path, (1_000_000_000, 1_000_000_000))

            second_chunks = create_chunks(record, config)

            self.assertEqual(
                [c.path for c in first_chunks], [c.path for c in second_chunks]
            )
            for path in [c.path for c in first_chunks]:
                self.assertEqual(path.stat().st_mtime, 1_000_000_000,
                                 "cache file was rewritten on second run")

    def test_max_chunks_cap_logs_warning_and_truncates(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "chunks"
            # JPEG's maximum supported dimension is 65500 px, so we cannot use
            # the plan's 100_000-tall fixture directly. height=30_000 with
            # width=200 -> expected_page_h=283, step=255 -> 118 fixed-height
            # chunks (well above MAX_CHUNKS_PER_IMAGE=100).
            strip = _make_uniform_strip(200, height=30_000)
            record = self._save_image_record(tmp, "huge.jpg", strip)
            config = ChunkerConfig(chunk_cache_dir=cache_dir)

            with self.assertLogs("src.document_restoration.chunker", level="WARNING") as logs:
                chunks = create_chunks(record, config)

            self.assertEqual(len(chunks), 100)
            self.assertIn(
                "truncated",
                "\n".join(logs.output).lower(),
            )

    def test_strip_with_no_cache_dir_raises_chunker_error(self):
        with TemporaryDirectory() as tmp:
            strip = _make_strip(400, page_height=600, num_pages=2, gap_height=200)
            record = self._save_image_record(tmp, "tall.jpg", strip)
            config = ChunkerConfig(chunk_cache_dir=None)

            with self.assertRaises(ChunkerError) as ctx:
                create_chunks(record, config)

            self.assertIn("chunk_cache_dir", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
