from pathlib import Path

from .models import ImageRecord


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def load_images(input_dir: Path) -> list[ImageRecord]:
    input_dir = input_dir.expanduser().resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    records: list[ImageRecord] = []
    for path in input_dir.iterdir():
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            records.append(ImageRecord(file_name=path.name, path=path.resolve()))

    return sorted(records, key=lambda record: record.file_name)
