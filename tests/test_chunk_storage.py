import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from src.document_restoration.chunk_storage import clear, file_exists, write_jpeg


def _make_rgb(width: int, height: int, color=(128, 128, 128)) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


class FileExistsTests(unittest.TestCase):
    def test_returns_false_for_missing_path(self):
        with TemporaryDirectory() as tmp:
            self.assertFalse(file_exists(Path(tmp) / "missing.jpg"))

    def test_returns_false_for_empty_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jpg"
            path.write_bytes(b"")
            self.assertFalse(file_exists(path))

    def test_returns_true_for_non_empty_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "img.jpg"
            write_jpeg(path, _make_rgb(10, 10))
            self.assertTrue(file_exists(path))


class WriteJpegTests(unittest.TestCase):
    def test_writes_loadable_jpeg_with_default_quality(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jpg"
            write_jpeg(path, _make_rgb(50, 30, color=(200, 100, 50)))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)
            with Image.open(path) as im:
                self.assertEqual(im.size, (50, 30))
                self.assertEqual(im.format, "JPEG")

    def test_creates_parent_directory_if_missing(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "deep" / "out.jpg"
            write_jpeg(path, _make_rgb(10, 10))
            self.assertTrue(path.exists())

    def test_does_not_overwrite_existing_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jpg"
            write_jpeg(path, _make_rgb(10, 10, color=(255, 0, 0)))
            first_size = path.stat().st_size
            first_bytes = path.read_bytes()

            write_jpeg(path, _make_rgb(10, 10, color=(0, 255, 0)))

            self.assertEqual(path.stat().st_size, first_size)
            self.assertEqual(path.read_bytes(), first_bytes)


class ClearTests(unittest.TestCase):
    def test_removes_all_chunks_for_stem(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            for nn in ("01", "02", "03"):
                p = cache_dir / f"doc_p{nn}.jpg"
                write_jpeg(p, _make_rgb(10, 10))
            other = cache_dir / "other_p01.jpg"
            write_jpeg(other, _make_rgb(10, 10))

            clear("doc", cache_dir)

            remaining = sorted(p.name for p in cache_dir.iterdir())
            self.assertEqual(remaining, ["other_p01.jpg"])

    def test_silent_when_no_matching_files(self):
        with TemporaryDirectory() as tmp:
            clear("never_existed", Path(tmp))  # should not raise


if __name__ == "__main__":
    unittest.main()
