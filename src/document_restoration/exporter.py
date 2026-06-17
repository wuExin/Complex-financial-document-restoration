import csv
from pathlib import Path

from .models import DocumentResult


FIELD_NAMES = ["file_name", "ground_truth"]


def write_submission_csv(results: list[DocumentResult], output_path: Path) -> None:
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "file_name": result.file_name,
                    "ground_truth": result.markdown,
                }
            )
