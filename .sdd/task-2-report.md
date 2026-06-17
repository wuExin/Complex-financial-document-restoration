# Task 2 Report: 一图一 Chunk 与 Mock 客户端

## Scope

- Created `src/document_restoration/chunker.py`.
- Created `src/document_restoration/vl_client.py`.
- Appended Task 2 tests to `tests/test_mvp_pipeline.py` before the `if __name__ == "__main__":` block.

## TDD Evidence

### RED

Command:

```powershell
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
ModuleNotFoundError: No module named 'src.document_restoration.chunker'
FAILED (errors=1)
```

This matched the expected missing-module failure from the task brief.

### GREEN

Command:

```powershell
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
Ran 6 tests in 0.009s

OK
```

## Implementation Notes

- `create_chunks(image)` returns exactly one `ImageChunk` for the MVP, using `chunk_id=0`, the original image path, and full-image coordinates.
- `MockVLClient` reads `{stem}.md` from an explicit `gt_dir` when available.
- `MockVLClient` also checks the sibling `mds` directory relative to the image path.
- Without ground truth markdown, `MockVLClient` returns a deterministic fallback.
- `FinixDocVLClient.parse_chunk` explicitly raises `NotImplementedError`.

## Concerns

None.
