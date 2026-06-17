# MVP Document Restoration Design

## Goal

Build a minimal end-to-end baseline for the AFAC complex financial document restoration project. The MVP must run from an image directory to a valid submission CSV without depending on the unavailable FinixDoc-VL API details.

The first version optimizes for a working engineering pipeline, not leaderboard quality.

## Scope

In scope:

- Scan an input directory for image files.
- Preserve each image file name in the output.
- Represent each image as one chunk in the MVP.
- Define a replaceable `VLClient` interface for image chunk parsing.
- Provide a mock local client that can run without network access.
- Merge chunk Markdown into one document per image.
- Write a UTF-8 CSV with exactly `file_name` and `ground_truth`.
- Log progress and continue processing when one image fails.

Out of scope for MVP:

- Real FinixDoc-VL HTTP integration.
- Advanced long-image slicing.
- Multi-column reading order recovery.
- Deduplication across overlapping chunks.
- Markdown table repair.
- Online scoring or TEDS evaluation.

## Architecture

The MVP uses a small Python package plus `main.py`.

```text
main.py
  -> image_loader
  -> chunker
  -> vl_client
  -> merge
  -> exporter
```

### `image_loader`

Finds supported image files under `--input_dir`, sorted by file name for deterministic output. Supported extensions are `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, and `.tiff`.

It returns lightweight image records with file name and absolute path. It does not decode full image pixels in the MVP.

### `chunker`

Creates one chunk per image:

```text
chunk_id = 0
x = 0
y = 0
width = null
height = null
path = original image path
```

This keeps the interface compatible with later real slicing while avoiding image memory risk in the baseline.

### `vl_client`

Defines the parsing boundary:

```python
parse_chunk(chunk) -> str
```

MVP implementation:

- `MockVLClient` looks for a matching ground-truth Markdown file when `--gt_dir` is provided or can be inferred from a sibling `mds` directory.
- If no Markdown file exists, it returns a deterministic placeholder that includes the source image name.

Future implementation:

- `FinixDocVLClient` will send chunk images to the official API after endpoint, authentication, request format, and response schema are known.

### `merge`

Sorts chunks by `chunk_id` and joins non-empty Markdown fragments with blank lines. For MVP, each image has one chunk, so merge is intentionally simple.

### `exporter`

Writes CSV using Python's standard `csv` module to ensure quoting of newlines, commas, and quotes. It validates:

- header is exactly `file_name,ground_truth`;
- row count equals processed image count;
- every input image has one output row.

## CLI

Primary command:

```bash
python main.py --input_dir "data/AFAC 训练数据集/finixdocbench_huge_long_100/images" --output submission.csv
```

Optional arguments:

- `--gt_dir`: directory containing `{image_stem}.md` files.
- `--client`: `mock` by default. `finixdoc` is reserved and should fail with a clear "not implemented" error until official API details are available.
- `--log_level`: defaults to `INFO`.

## Error Handling

Image-level failures must not abort the whole run. The pipeline logs the failure and writes an empty string for that image's `ground_truth` only if parsing fails unexpectedly.

Configuration errors, such as missing input directory or unsupported client name, fail fast.

## Testing

MVP tests should cover:

- image discovery and deterministic ordering;
- one-image-one-chunk behavior;
- mock client reading `{stem}.md`;
- mock client placeholder fallback;
- CSV output escaping and exact columns;
- end-to-end run on a temporary image/Markdown fixture.

## Success Criteria

The MVP is complete when:

- `python main.py --input_dir <images> --output submission.csv` runs successfully.
- The output CSV has exactly two columns: `file_name` and `ground_truth`.
- Running against a training image directory with sibling `mds` can populate Markdown from local GT files.
- Running against a directory without GT still produces a valid CSV with deterministic placeholders.
- The code structure allows replacing `MockVLClient` with a real FinixDoc-VL client without changing the pipeline.
