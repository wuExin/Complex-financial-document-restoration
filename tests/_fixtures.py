"""Shared test fixtures for the document_restoration test suite."""

from pathlib import Path

from PIL import Image


def write_tiny_jpeg(path: Path) -> None:
    """Write a 16x16 grey JPEG for tests that need a readable image header."""
    Image.new("RGB", (16, 16), color=(128, 128, 128)).save(path, format="JPEG")
