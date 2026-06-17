# Task 3 Report: Markdown 合并与 CSV 导出

## Scope

- Added `merge_chunk_markdown` in `src/document_restoration/merge.py`.
- Added `write_submission_csv` in `src/document_restoration/exporter.py`.
- Appended merge and CSV export tests to `tests/test_mvp_pipeline.py`.

## TDD Evidence

### Red

Command:

```powershell
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
ModuleNotFoundError: No module named 'src.document_restoration.exporter'
FAILED (errors=1)
```

This matched the expected missing implementation state after adding the tests.

### Green

Command:

```powershell
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
Ran 8 tests in 0.011s

OK
```

## Implementation Notes

- `merge_chunk_markdown` sorts by `ImageChunk.chunk_id`, strips surrounding whitespace, skips empty markdown, and joins retained parts with blank lines.
- `write_submission_csv` writes `file_name` and `ground_truth` columns using the standard-library `csv.DictWriter`, preserving markdown newlines and escaping CSV-sensitive characters.

## Concerns

- Existing unrelated untracked files and `__pycache__` directories were present before this task and were not modified or staged.
