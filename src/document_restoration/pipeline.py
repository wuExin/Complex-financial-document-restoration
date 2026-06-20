import logging
from pathlib import Path

from .chunker import ChunkerConfig, ChunkerError, create_chunks
from .exporter import write_submission_csv
from .image_loader import load_images
from .merge import merge_chunk_markdown
from .models import DocumentResult
from .vl_client import VLClient


LOGGER = logging.getLogger(__name__)


def run_pipeline(
    input_dir: Path,
    output_path: Path,
    client: VLClient,
    chunker_config: ChunkerConfig | None = None,
) -> list[DocumentResult]:
    images = load_images(input_dir)
    results: list[DocumentResult] = []

    for image in images:
        LOGGER.info("Processing %s", image.file_name)
        try:
            chunks = create_chunks(image, chunker_config)
            parsed = [(chunk, client.parse_chunk(chunk)) for chunk in chunks]
            markdown = merge_chunk_markdown(parsed)
        except ChunkerError as exc:
            LOGGER.error("Chunker failed for %s: %s", image.file_name, exc)
            markdown = ""
        except Exception:
            LOGGER.exception("Failed to process %s", image.file_name)
            markdown = ""

        results.append(DocumentResult(file_name=image.file_name, markdown=markdown))

    write_submission_csv(results, output_path)
    LOGGER.info("Wrote %s rows to %s", len(results), output_path)
    return results
