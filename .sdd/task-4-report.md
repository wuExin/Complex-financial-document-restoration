# Task 4 Report: Pipeline and CLI Entry

## Summary

- Added `run_pipeline(input_dir, output_path, client)` in `src/document_restoration/pipeline.py`.
- Added CLI entry point in `main.py` with `--input_dir`, `--output`, `--gt_dir`, `--client`, and `--log_level`.
- Added pipeline and CLI tests to `tests/test_mvp_pipeline.py`.
- Added `requirements.txt` documenting that the MVP uses only the Python standard library.

## TDD Evidence

### RED

Command:

```text
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
ERROR: test_mvp_pipeline (unittest.loader._FailedTest.test_mvp_pipeline)
ModuleNotFoundError: No module named 'src.document_restoration.pipeline'
FAILED (errors=1)
```

This was the expected failure after appending the required tests and before adding production code.

### GREEN

Command:

```text
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
Ran 10 tests in 0.094s
OK
```

## Training Data Run

Command:

```text
python main.py --input_dir "data/AFAC 训练数据集/finixdocbench_huge_long_100/images" --output outputs/submission_long_mock.csv --client mock
```

Result:

```text
FileNotFoundError: Input directory does not exist: E:\Project\github\private\Complex-financial-document-restoration\.worktrees\mvp-document-restoration\data\AFAC 训练数据集\finixdocbench_huge_long_100\images
```

The isolated worktree does not contain the untracked root `data/` directory, matching the environment limitation noted in the task brief. No data was copied or committed.

## Files Changed

- `src/document_restoration/pipeline.py`
- `main.py`
- `tests/test_mvp_pipeline.py`
- `requirements.txt`
