from .models import ImageChunk, ImageRecord


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
