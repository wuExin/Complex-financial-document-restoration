import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.document_restoration.chunker import create_chunks
from src.document_restoration.image_loader import load_images
from src.document_restoration.models import ImageRecord
from src.document_restoration.vl_client import FinixDocVLClient, MockVLClient


class ImageLoaderTests(unittest.TestCase):
    def test_load_images_returns_supported_files_sorted_by_name(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.png").write_bytes(b"fake")
            (root / "a.jpg").write_bytes(b"fake")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")

            records = load_images(root)

            self.assertEqual([r.file_name for r in records], ["a.jpg", "b.png"])
            self.assertTrue(all(r.path.is_absolute() for r in records))

    def test_load_images_fails_for_missing_directory(self):
        with self.assertRaises(FileNotFoundError):
            load_images(Path("missing-input-directory"))


class ChunkerTests(unittest.TestCase):
    def test_create_chunks_returns_one_chunk_for_mvp(self):
        image = ImageRecord(file_name="doc.jpg", path=Path("doc.jpg").resolve())

        chunks = create_chunks(image)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, 0)
        self.assertEqual(chunks[0].source, image)
        self.assertEqual(chunks[0].path, image.path)


class MockVLClientTests(unittest.TestCase):
    def test_mock_client_reads_matching_markdown_from_gt_dir(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt_dir = root / "mds"
            gt_dir.mkdir()
            image_path = root / "abc.jpg"
            image_path.write_bytes(b"fake")
            (gt_dir / "abc.md").write_text("# 标题\n\n正文", encoding="utf-8")
            chunk = create_chunks(ImageRecord(file_name="abc.jpg", path=image_path))[0]

            markdown = MockVLClient(gt_dir=gt_dir).parse_chunk(chunk)

            self.assertEqual(markdown, "# 标题\n\n正文")

    def test_mock_client_returns_deterministic_fallback_without_gt(self):
        image = ImageRecord(file_name="missing.jpg", path=Path("missing.jpg").resolve())
        chunk = create_chunks(image)[0]

        markdown = MockVLClient().parse_chunk(chunk)

        self.assertEqual(markdown, "# missing.jpg\n\nMock parse result for missing.jpg.")

    def test_finixdoc_client_is_explicitly_not_implemented(self):
        image = ImageRecord(file_name="doc.jpg", path=Path("doc.jpg").resolve())
        chunk = create_chunks(image)[0]

        with self.assertRaises(NotImplementedError):
            FinixDocVLClient().parse_chunk(chunk)


if __name__ == "__main__":
    unittest.main()
