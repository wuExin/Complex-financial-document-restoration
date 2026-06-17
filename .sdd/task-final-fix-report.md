## Final Review Fix Report

### Scope

- Fixed FinixDoc reserved client path to fail before processing starts.
- Added direct regression coverage for single-image parse failure isolation.

### TDD Evidence

- Added failing test first:
  - `PipelineTests.test_create_finixdoc_client_fails_before_processing`
  - Initial run: `python -m unittest tests.test_mvp_pipeline -v`
  - Result: failed because `create_client("finixdoc", None)` did not raise `NotImplementedError`.
- Added regression test:
  - `PipelineTests.test_run_pipeline_keeps_global_task_when_single_image_parse_fails`
  - Existing pipeline behavior already satisfied the requirement, proving the test covers the intended behavior without needing production changes.

### Implementation

- `main.py`
  - Removed the `FinixDocVLClient` factory import.
  - Changed `create_client("finixdoc", ...)` to raise `NotImplementedError` immediately with the existing clear message:
    `FinixDoc-VL API details are not available yet. Use --client mock.`
- `tests/test_mvp_pipeline.py`
  - Imported `create_client` for direct factory coverage.
  - Added `FailingOneImageClient` fake.
  - Added CSV assertions proving both image rows are written and only the failed image has empty `ground_truth`.
  - Captured expected pipeline error logging with `assertLogs` to keep test output clean.

### Verification

- Command: `python -m unittest tests.test_mvp_pipeline -v`
- Final result: 12 tests ran successfully.
- Output summary: `Ran 12 tests in 0.100s` and `OK`.

### Files Changed

- `main.py`
- `tests/test_mvp_pipeline.py`
- `.sdd/task-final-fix-report.md`
