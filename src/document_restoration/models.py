from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageRecord:
    file_name: str
    path: Path


@dataclass(frozen=True)
class ImageChunk:
    source: ImageRecord
    chunk_id: int
    path: Path
    file_name: str
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class DocumentResult:
    file_name: str
    markdown: str
