from .models import ImageChunk


def merge_chunk_markdown(chunks_and_markdown: list[tuple[ImageChunk, str]]) -> str:
    parts: list[str] = []
    for _chunk, markdown in sorted(chunks_and_markdown, key=lambda item: item[0].chunk_id):
        normalized = markdown.strip()
        if normalized:
            parts.append(normalized)
    return "\n\n".join(parts)
