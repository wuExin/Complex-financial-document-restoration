# Task 1 Report: 数据模型与图片发现

## Scope

- Added the initial `src.document_restoration` package.
- Added immutable data models for `ImageRecord`, `ImageChunk`, and `DocumentResult`.
- Added `load_images(input_dir: Path) -> list[ImageRecord]`.
- Added MVP pipeline tests for supported image discovery, sorting, absolute paths, and missing input handling.

## TDD Evidence

### Red

Command:

```powershell
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
ModuleNotFoundError: No module named 'src.document_restoration'

FAILED (errors=1)
```

Before this expected red result, the same command initially failed to import `tests.test_mvp_pipeline` because this Python environment injects `E:\Project\github\private\Flux` into `sys.path`, where a different `tests` package exists. I added a local `tests/__init__.py` marker so the exact command resolves this worktree's tests.

### Green

Command:

```powershell
python -m unittest tests.test_mvp_pipeline -v
```

Result:

```text
test_load_images_fails_for_missing_directory (tests.test_mvp_pipeline.ImageLoaderTests.test_load_images_fails_for_missing_directory) ... ok
test_load_images_returns_supported_files_sorted_by_name (tests.test_mvp_pipeline.ImageLoaderTests.test_load_images_returns_supported_files_sorted_by_name) ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.007s

OK
```

## Implementation Notes

- Supported extensions are `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, and `.tiff`.
- `load_images` resolves the input directory and returned image paths to absolute paths.
- Results are sorted by `ImageRecord.file_name`.
- Missing input paths raise `FileNotFoundError`.
- Non-directory input paths raise `NotADirectoryError`.

## Concerns

- `tests/__init__.py` was required for this local environment to run the exact unittest module command because another repository's `tests` package is present on `sys.path`. This file is outside the original four task-owned paths, but without it the requested command does not load this worktree's test module.
