# FinixDoc-VL API 接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MVP pipeline 基础上接入赛事官方 FinixDoc-VL API，让 `--client finixdoc` 真实调用官方接口，将图片解析为 Markdown 并写入 CSV。

**Architecture:** 复用 MVP 已有的 `VLClient` 协议、`run_pipeline` 主流程和 CSV 导出。新增 `FinixDocVLClient` 实现真实的 multipart 上传与响应解析；CLI 增加 `--user_id`、`--api_key`、`--endpoint`、`--timeout`、`--max_retries`、`--cache_dir` 参数；引入本地缓存避免重复请求。

**Tech Stack:** Python 3.10+，新增 `requests>=2.31.0`；测试使用 `unittest` 和 `unittest.mock`，不访问真实网络。

## Global Constraints

- `--client mock` 行为必须保持不变，现有 MVP 测试全部通过。
- 真实 API 调用必须支持缓存命中跳过网络。
- 单图 API 失败不得中断 pipeline；该图写入空字符串。
- 配置错误必须在 client 构造时快速失败。
- 测试不得访问真实 `finixdocapi.alipay.com`，必须 mock 网络层。
- 输出 CSV 字段仍严格为 `file_name` 和 `ground_truth`。

---

## File Structure

- Modify: `requirements.txt`
  新增 `requests>=2.31.0` 依赖。
- Modify: `.gitignore`
  新增 `.cache/` 忽略规则。
- Modify: `src/document_restoration/vl_client.py`
  替换 `FinixDocVLClient` stub：构造时校验白名单和参数；实现 multipart 上传、响应解析和缓存。
- Modify: `main.py`
  CLI 新增 `--user_id`、`--api_key`、`--endpoint`、`--timeout`、`--max_retries`、`--cache_dir`；`create_client` 在选择 `finixdoc` 时构造真实 client。
- Modify: `tests/test_mvp_pipeline.py`
  移除两个旧的 `NotImplementedError` 断言测试。
- Create: `tests/test_finixdoc_client.py`
  FinixDocVLClient 的白名单、配置校验、响应解析、缓存、multipart 请求和 pipeline 集成测试。

---

### Task 1: 新增 requests 依赖并更新 .gitignore

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- 仅环境准备，不引入新 API。

- [ ] **Step 1: 更新 `requirements.txt`**

替换 `requirements.txt` 内容为：

```text
requests>=2.31.0
```

- [ ] **Step 2: 更新 `.gitignore`**

替换 `.gitignore` 内容为：

```text
.worktrees/
.sdd/
__pycache__/
outputs/
.cache/
```

- [ ] **Step 3: 安装依赖**

Run: `pip install -r requirements.txt`

Expected: `Successfully installed requests-...`（如已存在则显示 `Requirement already satisfied`）。

- [ ] **Step 4: 运行现有测试，确认未引入回归**

Run: `python -m unittest tests.test_mvp_pipeline -v`

Expected: 全部现有测试 PASS（8 个测试）。

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "chore: add requests dep and ignore cache dir"
```

---

### Task 2: 引入常量与 FinixDocVLClient 构造校验

**Files:**
- Modify: `src/document_restoration/vl_client.py`
- Modify: `tests/test_mvp_pipeline.py`
- Create: `tests/test_finixdoc_client.py`

**Interfaces:**
- Produces: `FinixDocVLClient(user_id, api_key, endpoint, timeout, max_retries, cache_dir)`
- Produces: 常量 `ALLOWED_USER_IDS`、`DEFAULT_USER_ID`、`DEFAULT_API_KEY`、`DEFAULT_ENDPOINT`、`DEFAULT_TIMEOUT`、`DEFAULT_MAX_RETRIES`、`DEFAULT_CACHE_DIR`
- `FinixDocVLClient.parse_chunk` 仍保留为 stub，Task 5 实现。

- [ ] **Step 1: Write the failing tests**

Create `tests/test_finixdoc_client.py`:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.document_restoration.chunker import create_chunks
from src.document_restoration.models import ImageRecord
from src.document_restoration.vl_client import (
    ALLOWED_USER_IDS,
    DEFAULT_API_KEY,
    DEFAULT_CACHE_DIR,
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_ID,
    FinixDocVLClient,
)


class FinixDocClientConstructionTests(unittest.TestCase):
    def test_default_constants_match_spec(self):
        self.assertEqual(DEFAULT_USER_ID, "finixB2002")
        self.assertEqual(DEFAULT_API_KEY, "F935A5503983FB19F26FA3F00A94EBF9")
        self.assertEqual(
            DEFAULT_ENDPOINT,
            "https://finixdocapi.alipay.com/api/finix_doc/call_with_file",
        )
        self.assertEqual(DEFAULT_TIMEOUT, 180)
        self.assertEqual(DEFAULT_MAX_RETRIES, 2)
        self.assertEqual(DEFAULT_CACHE_DIR, Path(".cache/finixdoc_vl"))
        self.assertEqual(
            ALLOWED_USER_IDS,
            {"finixA1001", "finixB2002", "finixC3003", "finixD4004", "finixE5005"},
        )

    def test_construction_succeeds_with_valid_whitelist_user(self):
        with TemporaryDirectory() as tmp:
            client = FinixDocVLClient(
                user_id="finixA1001",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=30,
                max_retries=1,
                cache_dir=Path(tmp),
            )
            self.assertEqual(client.user_id, "finixA1001")

    def test_construction_uses_none_cache_dir_when_disabled(self):
        client = FinixDocVLClient(
            user_id=DEFAULT_USER_ID,
            api_key=DEFAULT_API_KEY,
            endpoint=DEFAULT_ENDPOINT,
            timeout=DEFAULT_TIMEOUT,
            max_retries=DEFAULT_MAX_RETRIES,
            cache_dir=None,
        )
        self.assertIsNone(client.cache_dir)

    def test_construction_fails_when_user_id_not_in_whitelist(self):
        with self.assertRaisesRegex(ValueError, "userId"):
            FinixDocVLClient(
                user_id="rogue",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=30,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_api_key_empty(self):
        with self.assertRaisesRegex(ValueError, "apiKey"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="",
                endpoint=DEFAULT_ENDPOINT,
                timeout=30,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_endpoint_empty(self):
        with self.assertRaisesRegex(ValueError, "endpoint"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="key",
                endpoint="",
                timeout=30,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_timeout_non_positive(self):
        with self.assertRaisesRegex(ValueError, "timeout"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="key",
                endpoint=DEFAULT_ENDPOINT,
                timeout=0,
                max_retries=0,
                cache_dir=None,
            )

    def test_construction_fails_when_max_retries_negative(self):
        with self.assertRaisesRegex(ValueError, "max_retries"):
            FinixDocVLClient(
                user_id=DEFAULT_USER_ID,
                api_key="key",
                endpoint=DEFAULT_ENDPOINT,
                timeout=30,
                max_retries=-1,
                cache_dir=None,
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_finixdoc_client -v`

Expected: FAIL with `ImportError: cannot import name 'ALLOWED_USER_IDS'`。

- [ ] **Step 3: Write minimal implementation**

Replace `src/document_restoration/vl_client.py` with:

```python
import hashlib
import logging
from pathlib import Path
from typing import Protocol

import requests

from .models import ImageChunk


LOGGER = logging.getLogger(__name__)


ALLOWED_USER_IDS = frozenset(
    {"finixA1001", "finixB2002", "finixC3003", "finixD4004", "finixE5005"}
)
DEFAULT_USER_ID = "finixB2002"
DEFAULT_API_KEY = "F935A5503983FB19F26FA3F00A94EBF9"
DEFAULT_ENDPOINT = "https://finixdocapi.alipay.com/api/finix_doc/call_with_file"
DEFAULT_TIMEOUT = 180
DEFAULT_MAX_RETRIES = 2
DEFAULT_CACHE_DIR = Path(".cache/finixdoc_vl")


class VLClient(Protocol):
    def parse_chunk(self, chunk: ImageChunk) -> str:
        raise NotImplementedError


class MockVLClient:
    def __init__(self, gt_dir: Path | None = None) -> None:
        self.gt_dir = gt_dir.expanduser().resolve() if gt_dir else None

    def parse_chunk(self, chunk: ImageChunk) -> str:
        gt_path = self._find_ground_truth(chunk)
        if gt_path is not None:
            return gt_path.read_text(encoding="utf-8").strip()

        return f"# {chunk.source.file_name}\n\nMock parse result for {chunk.source.file_name}."

    def _find_ground_truth(self, chunk: ImageChunk) -> Path | None:
        stem = chunk.source.path.stem
        candidates: list[Path] = []
        if self.gt_dir is not None:
            candidates.append(self.gt_dir / f"{stem}.md")

        sibling_mds = chunk.source.path.parent.parent / "mds"
        candidates.append(sibling_mds / f"{stem}.md")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None


class FinixDocVLClient:
    def __init__(
        self,
        user_id: str,
        api_key: str,
        endpoint: str,
        timeout: float,
        max_retries: int,
        cache_dir: Path | None,
    ) -> None:
        if user_id not in ALLOWED_USER_IDS:
            raise ValueError(
                f"userId '{user_id}' is not in the official whitelist: {sorted(ALLOWED_USER_IDS)}"
            )
        if not api_key:
            raise ValueError("apiKey must not be empty.")
        if not endpoint:
            raise ValueError("endpoint must not be empty.")
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}.")
        if max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {max_retries}.")

        self.user_id = user_id
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_dir = cache_dir.expanduser().resolve() if cache_dir else None

    def parse_chunk(self, chunk: ImageChunk) -> str:
        raise NotImplementedError(
            "FinixDocVLClient.parse_chunk will be implemented in a later task."
        )
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `python -m unittest tests.test_finixdoc_client -v`

Expected: 8 个测试全部 PASS。

- [ ] **Step 5: 移除旧的 NotImplementedError 断言测试**

Modify `tests/test_mvp_pipeline.py`：

1. 删除 `MockVLClientTests.test_finixdoc_client_is_explicitly_not_implemented` 整个方法。
2. 删除 `PipelineTests.test_create_finixdoc_client_fails_before_processing` 整个方法。

完成后 `MockVLClientTests` 和 `PipelineTests` 类中其余测试不受影响。

- [ ] **Step 6: Run all tests to verify no regressions**

Run: `python -m unittest discover tests -v`

Expected: 全部测试 PASS（旧的两个 NotImplementedError 测试已删除，新的 8 个构造测试通过，原 6 个 MVP 测试仍 PASS）。

- [ ] **Step 7: Commit**

```bash
git add src/document_restoration/vl_client.py tests/test_finixdoc_client.py tests/test_mvp_pipeline.py
git commit -m "feat: validate finixdoc whitelist and config"
```

---

### Task 3: 响应解析（兼容多种 schema）

**Files:**
- Modify: `src/document_restoration/vl_client.py`
- Modify: `tests/test_finixdoc_client.py`

**Interfaces:**
- Produces: `FinixDocVLClient._parse_response(response: requests.Response) -> str`
- Produces: `FinixDocVLClient._extract_markdown(payload: dict | None) -> str | None`（私有静态方法）

- [ ] **Step 1: Write the failing tests**

在 `tests/test_finixdoc_client.py` 顶部 import 块新增：

```python
import json
from typing import Any
from unittest.mock import MagicMock
```

在 `if __name__ == "__main__":` 之前新增：

```python
def _make_response(
    status_code: int = 200,
    body: Any = None,
    content_type: str | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"Content-Type": content_type} if content_type else {}
    if isinstance(body, str):
        response.text = body
        response.json.side_effect = ValueError("not json")
    elif body is None:
        response.text = ""
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body
        response.text = json.dumps(body)
    return response


class FinixDocResponseParsingTests(unittest.TestCase):
    def _client(self) -> FinixDocVLClient:
        return FinixDocVLClient(
            user_id=DEFAULT_USER_ID,
            api_key=DEFAULT_API_KEY,
            endpoint=DEFAULT_ENDPOINT,
            timeout=30,
            max_retries=0,
            cache_dir=None,
        )

    def test_parse_response_reads_top_level_markdown(self):
        response = _make_response(body={"markdown": "# 标题\n\n正文"})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "# 标题\n\n正文")

    def test_parse_response_reads_data_markdown_when_top_level_missing(self):
        response = _make_response(body={"data": {"markdown": "从 data 取出"}})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "从 data 取出")

    def test_parse_response_reads_result_field_when_no_markdown(self):
        response = _make_response(body={"result": "从 result 取出"})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "从 result 取出")

    def test_parse_response_reads_data_string_when_no_other_fields(self):
        response = _make_response(body={"data": "纯字符串"})

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "纯字符串")

    def test_parse_response_returns_plain_text_when_not_json(self):
        response = _make_response(
            body="直接返回的 markdown", content_type="text/markdown"
        )

        markdown = self._client()._parse_response(response)

        self.assertEqual(markdown, "直接返回的 markdown")

    def test_parse_response_raises_when_markdown_blank(self):
        response = _make_response(body={"markdown": "   "})

        with self.assertRaisesRegex(ValueError, "markdown"):
            self._client()._parse_response(response)

    def test_parse_response_raises_when_body_empty(self):
        response = _make_response(body=None)

        with self.assertRaisesRegex(ValueError, "markdown"):
            self._client()._parse_response(response)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_finixdoc_client.FinixDocResponseParsingTests -v`

Expected: FAIL with `AttributeError: 'FinixDocVLClient' object has no attribute '_parse_response'`。

- [ ] **Step 3: Write minimal implementation**

Modify `src/document_restoration/vl_client.py`：在 `FinixDocVLClient.parse_chunk` 之前插入两个新方法（保留 `parse_chunk` stub）：

```python
    def _parse_response(self, response: requests.Response) -> str:
        content_type = response.headers.get("Content-Type", "")
        body = response.text or ""

        if "application/json" in content_type or body.lstrip().startswith(("{", "[")):
            try:
                payload = response.json()
            except ValueError:
                payload = None
            extracted = self._extract_markdown(payload)
            if extracted is not None:
                return extracted

        if body.strip():
            return body.strip()

        raise ValueError("Response did not contain parseable markdown.")

    @staticmethod
    def _extract_markdown(payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None

        top = payload.get("markdown")
        if isinstance(top, str) and top.strip():
            return top.strip()

        data = payload.get("data")
        if isinstance(data, dict):
            inner = data.get("markdown")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()

        result = payload.get("result")
        if isinstance(result, str) and result.strip():
            return result.strip()

        if isinstance(data, str) and data.strip():
            return data.strip()

        return None
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `python -m unittest tests.test_finixdoc_client.FinixDocResponseParsingTests -v`

Expected: 7 个测试全部 PASS。

- [ ] **Step 5: Run all tests to confirm no regressions**

Run: `python -m unittest discover tests -v`

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/vl_client.py tests/test_finixdoc_client.py
git commit -m "feat: parse finixdoc response with schema fallbacks"
```

---

### Task 4: 缓存读写

**Files:**
- Modify: `src/document_restoration/vl_client.py`
- Modify: `tests/test_finixdoc_client.py`

**Interfaces:**
- Produces: `FinixDocVLClient._cache_key(chunk: ImageChunk) -> str`
- Produces: `FinixDocVLClient._read_cache(key: str) -> str | None`
- Produces: `FinixDocVLClient._write_cache(key: str, markdown: str) -> None`
- `cache_dir=None` 时禁用缓存。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_finixdoc_client.py` 的 `if __name__ == "__main__":` 之前新增：

```python
class FinixDocCacheTests(unittest.TestCase):
    def _make_chunk(
        self,
        root: Path,
        content: bytes = b"image-bytes",
        file_name: str = "doc.jpg",
    ) -> object:
        path = root / file_name
        path.write_bytes(content)
        image = ImageRecord(file_name=file_name, path=path)
        return create_chunks(image)[0]

    def _client(
        self,
        cache_dir: Path | None,
        user_id: str = "finixA1001",
    ) -> FinixDocVLClient:
        return FinixDocVLClient(
            user_id=user_id,
            api_key="key",
            endpoint="https://example.invalid/api",
            timeout=30,
            max_retries=0,
            cache_dir=cache_dir,
        )

    def test_cache_key_is_stable_for_same_inputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(root)

            key_a = client._cache_key(chunk)
            key_b = client._cache_key(chunk)

            self.assertEqual(key_a, key_b)
            self.assertTrue(key_a.endswith(".md"))

    def test_cache_key_changes_with_user_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client_a = self._client(root, user_id="finixA1001")
            client_b = self._client(root, user_id="finixB2002")

            self.assertNotEqual(client_a._cache_key(chunk), client_b._cache_key(chunk))

    def test_cache_key_changes_with_file_content(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk_a = self._make_chunk(root, b"bytes-a", file_name="a.jpg")
            chunk_b = self._make_chunk(root, b"bytes-b", file_name="b.jpg")
            client = self._client(root)

            self.assertNotEqual(client._cache_key(chunk_a), client._cache_key(chunk_b))

    def test_write_and_read_cache_round_trip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            cache_dir = root / "cache"
            client = self._client(cache_dir)

            key = client._cache_key(chunk)
            client._write_cache(key, "# 标题\n\n正文")

            self.assertEqual(client._read_cache(key), "# 标题\n\n正文")

    def test_read_cache_returns_none_when_missing(self):
        with TemporaryDirectory() as tmp:
            client = self._client(Path(tmp))

            self.assertIsNone(client._read_cache("nonexistent.md"))

    def test_cache_disabled_returns_none_on_read(self):
        client = self._client(cache_dir=None)

        self.assertIsNone(client._read_cache("any.md"))

    def test_cache_disabled_write_is_noop(self):
        client = self._client(cache_dir=None)

        client._write_cache("any.md", "value")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_finixdoc_client.FinixDocCacheTests -v`

Expected: FAIL with `AttributeError: 'FinixDocVLClient' object has no attribute '_cache_key'`。

- [ ] **Step 3: Write minimal implementation**

Modify `src/document_restoration/vl_client.py`：在 `_extract_markdown` 之后、`parse_chunk` 之前插入：

```python
    def _cache_key(self, chunk: ImageChunk) -> str:
        hasher = hashlib.sha256()
        hasher.update(chunk.source.path.read_bytes())
        hasher.update(chunk.source.file_name.encode("utf-8"))
        hasher.update(b"finixdoc")
        hasher.update(self.endpoint.encode("utf-8"))
        hasher.update(self.user_id.encode("utf-8"))
        return f"{hasher.hexdigest()}.md"

    def _read_cache(self, key: str) -> str | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / key
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def _write_cache(self, key: str, markdown: str) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / key).write_text(markdown, encoding="utf-8")
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `python -m unittest tests.test_finixdoc_client.FinixDocCacheTests -v`

Expected: 7 个测试全部 PASS。

- [ ] **Step 5: Run all tests to confirm no regressions**

Run: `python -m unittest discover tests -v`

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/vl_client.py tests/test_finixdoc_client.py
git commit -m "feat: add finixdoc response cache"
```

---

### Task 5: 实现 parse_chunk 与重试

**Files:**
- Modify: `src/document_restoration/vl_client.py`
- Modify: `tests/test_finixdoc_client.py`

**Interfaces:**
- 实现: `FinixDocVLClient.parse_chunk(chunk: ImageChunk) -> str`
- 内部使用: `_parse_response`、`_cache_key`、`_read_cache`、`_write_cache`
- 缓存命中跳过网络；全部重试失败抛 `RuntimeError`，由上层 pipeline 捕获。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_finixdoc_client.py` 顶部 import 块新增：

```python
from unittest.mock import patch

import requests as requests_lib
```

（`import requests` 已在 `vl_client` 中使用，这里在测试中重新引入以便构造异常实例。）

在 `if __name__ == "__main__":` 之前新增：

```python
class FinixDocParseChunkTests(unittest.TestCase):
    def _make_chunk(self, root: Path, file_name: str = "doc.jpg") -> object:
        path = root / file_name
        path.write_bytes(b"image-bytes")
        image = ImageRecord(file_name=file_name, path=path)
        return create_chunks(image)[0]

    def _client(
        self,
        cache_dir: Path | None,
        max_retries: int = 2,
    ) -> FinixDocVLClient:
        return FinixDocVLClient(
            user_id="finixA1001",
            api_key="key",
            endpoint="https://example.invalid/api",
            timeout=30,
            max_retries=max_retries,
            cache_dir=cache_dir,
        )

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_returns_markdown_from_api(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.return_value = _make_response(body={"markdown": "# 标题"})

            markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# 标题")
            mock_post.assert_called_once()

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_writes_cache_on_success(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            cache_dir = root / "cache"
            client = self._client(cache_dir=cache_dir)
            mock_post.return_value = _make_response(body={"markdown": "# 标题"})

            client.parse_chunk(chunk)

            cached_files = list(cache_dir.iterdir())
            self.assertEqual(len(cached_files), 1)
            self.assertIn("# 标题", cached_files[0].read_text(encoding="utf-8"))

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_skips_api_when_cache_hit(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            cache_dir = root / "cache"
            client = self._client(cache_dir=cache_dir)
            key = client._cache_key(chunk)
            client._write_cache(key, "# 来自缓存")

            markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# 来自缓存")
            mock_post.assert_not_called()

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_sends_multipart_fields(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root, file_name="report.png")
            client = self._client(cache_dir=None)
            mock_post.return_value = _make_response(body={"markdown": "# ok"})

            client.parse_chunk(chunk)

            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertEqual(kwargs["data"]["userId"], "finixA1001")
            self.assertEqual(kwargs["data"]["apiKey"], "key")
            self.assertEqual(kwargs["data"]["fileName"], "report.png")
            self.assertEqual(kwargs["timeout"], 30)
            self.assertIn("file", kwargs["files"])

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_retries_on_transient_failure(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.side_effect = [
                requests_lib.exceptions.Timeout("timeout 1"),
                _make_response(body={"markdown": "# retry succeeded"}),
            ]

            markdown = client.parse_chunk(chunk)

            self.assertEqual(markdown, "# retry succeeded")
            self.assertEqual(mock_post.call_count, 2)

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_raises_when_all_attempts_fail(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.side_effect = requests_lib.exceptions.Timeout("always times out")

            with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
                client.parse_chunk(chunk)
            self.assertEqual(mock_post.call_count, 3)

    @patch("src.document_restoration.vl_client.requests.post")
    def test_parse_chunk_retries_on_non_2xx(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk = self._make_chunk(root)
            client = self._client(cache_dir=None)
            mock_post.return_value = MagicMock(
                status_code=500, headers={}, text="server error"
            )

            with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
                client.parse_chunk(chunk)
            self.assertEqual(mock_post.call_count, 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_finixdoc_client.FinixDocParseChunkTests -v`

Expected: 多数测试 FAIL（`parse_chunk` 仍抛 `NotImplementedError`），少数 FAIL on assertion。

- [ ] **Step 3: Write minimal implementation**

Modify `src/document_restoration/vl_client.py`：替换 `parse_chunk` 方法（保留 `_parse_response`、`_extract_markdown`、`_cache_key`、`_read_cache`、`_write_cache`）：

```python
    def parse_chunk(self, chunk: ImageChunk) -> str:
        if self.cache_dir is not None:
            key = self._cache_key(chunk)
            cached = self._read_cache(key)
            if cached is not None:
                LOGGER.info("Cache hit for %s", chunk.source.file_name)
                return cached

        markdown = self._call_api(chunk)

        if self.cache_dir is not None:
            self._write_cache(self._cache_key(chunk), markdown)
        return markdown

    def _call_api(self, chunk: ImageChunk) -> str:
        total_attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(total_attempts):
            try:
                with chunk.source.path.open("rb") as file_obj:
                    response = requests.post(
                        self.endpoint,
                        data={
                            "userId": self.user_id,
                            "apiKey": self.api_key,
                            "fileName": chunk.source.file_name,
                        },
                        files={"file": (chunk.source.file_name, file_obj)},
                        timeout=self.timeout,
                    )
                if not 200 <= response.status_code < 300:
                    raise RuntimeError(
                        f"FinixDoc-VL API returned status {response.status_code}"
                    )
                return self._parse_response(response)
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "FinixDoc-VL attempt %s/%s failed for %s: %s",
                    attempt + 1,
                    total_attempts,
                    chunk.source.file_name,
                    exc,
                )

        raise RuntimeError(
            f"FinixDoc-VL API failed after {total_attempts} attempts for {chunk.source.file_name}"
        ) from last_error
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `python -m unittest tests.test_finixdoc_client.FinixDocParseChunkTests -v`

Expected: 7 个测试全部 PASS。

- [ ] **Step 5: Run all tests to confirm no regressions**

Run: `python -m unittest discover tests -v`

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/document_restoration/vl_client.py tests/test_finixdoc_client.py
git commit -m "feat: call finixdoc api with retries and cache"
```

---

### Task 6: CLI 参数与 pipeline 集成

**Files:**
- Modify: `main.py`
- Modify: `tests/test_finixdoc_client.py`

**Interfaces:**
- CLI 新增: `--user_id`、`--api_key`、`--endpoint`、`--timeout`、`--max_retries`、`--cache_dir`
- 修改: `create_client(args: argparse.Namespace) -> VLClient`（签名变更，由 `(client_name, gt_dir)` 改为接收完整 `args`）

- [ ] **Step 1: Write the failing tests**

先把 `tests/test_finixdoc_client.py` 顶部的 import 块整体替换为以下完整版本（覆盖前几个任务累积下来的 import，确保 Task 6 测试可用）：

```python
import argparse
import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import requests as requests_lib

from main import create_client
from src.document_restoration.chunker import create_chunks
from src.document_restoration.models import ImageRecord
from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import (
    ALLOWED_USER_IDS,
    DEFAULT_API_KEY,
    DEFAULT_CACHE_DIR,
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_ID,
    FinixDocVLClient,
    MockVLClient,
)
```

在 `if __name__ == "__main__":` 之前新增：

```python
def _build_args(**overrides: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "client": "mock",
        "gt_dir": None,
        "user_id": DEFAULT_USER_ID,
        "api_key": DEFAULT_API_KEY,
        "endpoint": DEFAULT_ENDPOINT,
        "timeout": DEFAULT_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "cache_dir": "none",
        "input_dir": "ignored",
        "output": "ignored",
        "log_level": "INFO",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class CreateClientTests(unittest.TestCase):
    def test_returns_mock_for_mock_choice(self):
        client = create_client(_build_args(client="mock"))

        self.assertIsInstance(client, MockVLClient)

    def test_returns_finixdoc_for_finixdoc_choice(self):
        client = create_client(_build_args(client="finixdoc", cache_dir="none"))

        self.assertIsInstance(client, FinixDocVLClient)
        self.assertIsNone(client.cache_dir)

    def test_converts_cache_dir_path_when_provided(self):
        with TemporaryDirectory() as tmp:
            client = create_client(_build_args(client="finixdoc", cache_dir=tmp))

            self.assertEqual(client.cache_dir, Path(tmp).resolve())

    def test_passes_user_id_and_endpoint_to_client(self):
        client = create_client(
            _build_args(
                client="finixdoc",
                user_id="finixC3003",
                endpoint="https://custom.invalid/api",
                cache_dir="none",
            )
        )

        self.assertEqual(client.user_id, "finixC3003")
        self.assertEqual(client.endpoint, "https://custom.invalid/api")


class FinixDocPipelineIntegrationTests(unittest.TestCase):
    @patch("src.document_restoration.vl_client.requests.post")
    def test_run_pipeline_with_finixdoc_client_writes_csv(self, mock_post):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            (images / "doc.jpg").write_bytes(b"fake-image")
            output = root / "submission.csv"
            mock_post.return_value = _make_response(body={"markdown": "# 真实解析"})

            client = FinixDocVLClient(
                user_id="finixA1001",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=10,
                max_retries=0,
                cache_dir=None,
            )
            results = run_pipeline(images, output, client)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].markdown, "# 真实解析")
            with output.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["ground_truth"], "# 真实解析")

    def test_main_cli_runs_with_finixdoc_client_via_cache(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            image_path = images / "doc.jpg"
            image_path.write_bytes(b"fake-image")
            output = root / "submission.csv"
            cache_dir = root / "cache"
            cache_dir.mkdir()

            seed_client = FinixDocVLClient(
                user_id="finixA1001",
                api_key="key",
                endpoint="https://example.invalid/api",
                timeout=10,
                max_retries=0,
                cache_dir=cache_dir,
            )
            chunk = create_chunks(ImageRecord(file_name="doc.jpg", path=image_path))[0]
            seed_client._write_cache(seed_client._cache_key(chunk), "# 来自缓存")

            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--input_dir",
                    str(images),
                    "--output",
                    str(output),
                    "--client",
                    "finixdoc",
                    "--user_id",
                    "finixA1001",
                    "--api_key",
                    "key",
                    "--endpoint",
                    "https://example.invalid/api",
                    "--cache_dir",
                    str(cache_dir),
                ],
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["ground_truth"], "# 来自缓存")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_finixdoc_client.CreateClientTests tests.test_finixdoc_client.FinixDocPipelineIntegrationTests -v`

Expected: `CreateClientTests` FAIL（`create_client` 当前签名 `(client_name, gt_dir)`，单参数 args 调用 TypeError）；`FinixDocPipelineIntegrationTests` 第二个测试 FAIL（CLI 仍走 `NotImplementedError` 路径）。

- [ ] **Step 3: Write minimal implementation**

Replace `main.py` with:

```python
import argparse
import logging
from pathlib import Path

from src.document_restoration.pipeline import run_pipeline
from src.document_restoration.vl_client import (
    DEFAULT_API_KEY,
    DEFAULT_CACHE_DIR,
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_ID,
    FinixDocVLClient,
    MockVLClient,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run document restoration pipeline.")
    parser.add_argument(
        "--input_dir", required=True, help="Directory containing input images."
    )
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument(
        "--gt_dir",
        default=None,
        help="Optional directory containing ground-truth Markdown files (mock client only).",
    )
    parser.add_argument(
        "--client",
        choices=["mock", "finixdoc"],
        default="mock",
        help="VL client implementation.",
    )
    parser.add_argument(
        "--user_id",
        default=DEFAULT_USER_ID,
        help=f"FinixDoc-VL whitelist userId (default: {DEFAULT_USER_ID}).",
    )
    parser.add_argument(
        "--api_key",
        default=DEFAULT_API_KEY,
        help="FinixDoc-VL apiKey (default: official fixed key).",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="FinixDoc-VL API endpoint.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--max_retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum number of retries per image.",
    )
    parser.add_argument(
        "--cache_dir",
        default=str(DEFAULT_CACHE_DIR),
        help="Local cache directory for parsed markdown (pass 'none' to disable).",
    )
    parser.add_argument("--log_level", default="INFO", help="Python logging level.")
    return parser


def create_client(args: argparse.Namespace):
    if args.client == "mock":
        return MockVLClient(Path(args.gt_dir) if args.gt_dir else None)
    if args.client == "finixdoc":
        cache_arg = (args.cache_dir or "").strip()
        cache_dir = None if cache_arg.lower() == "none" else Path(cache_arg)
        return FinixDocVLClient(
            user_id=args.user_id,
            api_key=args.api_key,
            endpoint=args.endpoint,
            timeout=args.timeout,
            max_retries=args.max_retries,
            cache_dir=cache_dir,
        )
    raise ValueError(f"Unsupported client: {args.client}")


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = create_client(args)
    run_pipeline(Path(args.input_dir), Path(args.output), client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `python -m unittest tests.test_finixdoc_client.CreateClientTests tests.test_finixdoc_client.FinixDocPipelineIntegrationTests -v`

Expected: 6 个测试全部 PASS。

- [ ] **Step 5: Run all tests to confirm no regressions**

Run: `python -m unittest discover tests -v`

Expected: 全部 PASS，包括 `test_mvp_pipeline.py` 中的 `test_main_cli_runs_with_mock_client`。

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_finixdoc_client.py
git commit -m "feat: wire finixdoc client into cli"
```

---

### Task 7: 真实 API 冒烟测试（手动）

**Files:**
- 无代码改动。仅人工验证。

**目的：** 满足 spec 的成功标准「至少抽样 3 张图片确认 `ground_truth` 不再是 mock 占位文本」。该步骤无法在单元测试中自动化（依赖真实网络），需手动执行。

- [ ] **Step 1: 找到测试集图片目录**

确认以下目录存在：

```text
F:/private/Complex-financial-document-restoration/AFAC A榜评测数据集(2)/finix_huge_long_rest_A/images
```

若目录结构不同，请替换为真实路径。

- [ ] **Step 2: 准备少量样本**

从测试集 images 目录中复制 3 张图片到一个临时目录，例如 `F:/private/Complex-financial-document-restoration/data/smoke/`。

- [ ] **Step 3: 执行 finixdoc 客户端冒烟运行**

Run:

```bash
python main.py ^
  --input_dir "data/smoke" ^
  --output "outputs/smoke_finixdoc.csv" ^
  --client finixdoc ^
  --user_id finixB2002 ^
  --cache_dir ".cache/finixdoc_vl"
```

Expected: 命令 exit 0；输出 CSV 包含 3 行 `file_name,ground_truth`；每行 `ground_truth` 不再是 `# <name>\n\nMock parse result for <name>.` 占位文本。

- [ ] **Step 4: 检查日志和缓存**

确认：

- 控制台日志显示 `Processing <name>` 和 `Wrote 3 rows`。
- `.cache/finixdoc_vl/` 目录下生成 3 个 `.md` 缓存文件。
- 重复运行同一命令应在日志中看到 `Cache hit for <name>`，且不发起实际网络请求（可用 Wireshark 或日志确认；缓存命中即视为通过）。

- [ ] **Step 5: 失败兜底验证**

将 `--api_key` 改为空字符串运行，确认 client 构造时抛 `ValueError: apiKey must not be empty.` 并退出非 0。

将 `--user_id` 改为 `rogue` 运行，确认 client 构造时抛 `ValueError: userId 'rogue' is not in the official whitelist` 并退出非 0。

- [ ] **Step 6: Commit smoke artifacts 忽略验证**

确认 `outputs/smoke_finixdoc.csv` 和 `.cache/finixdoc_vl/` 都被 `.gitignore` 正确忽略。

```bash
git status
```

Expected: 上述路径不出现在 `Untracked files` 列表。

---

## Self-Review

**Spec coverage：**

- `--client finixdoc` 真实调用 → Task 5 / Task 6。
- `--user_id` / `--api_key` / `--endpoint` / `--timeout` / `--max_retries` → Task 6 CLI；Task 2 默认值常量。
- 默认 endpoint / userId / apiKey → Task 2 常量；Task 6 CLI 默认值引用。
- multipart 表单上传 → Task 5 `_call_api`。
- 解析 API 返回 Markdown → Task 3 `_parse_response`。
- 单图失败不中断 → MVP pipeline 已有，由 Task 6 集成测试覆盖。
- 本地缓存命中跳过网络 → Task 4 + Task 5 `parse_chunk` 入口判断。
- CSV 字段不变 → MVP 既有，Task 6 集成测试覆盖。
- userId 白名单 → Task 2 校验。
- apiKey 为空 → Task 2 校验。
- endpoint 为空 → Task 2 校验。
- timeout ≤ 0 → Task 2 校验。
- max_retries < 0 → Task 2 校验。
- `requests` 依赖 → Task 1。
- `.gitignore .cache/` → Task 1。

**Spec 测试覆盖：**

- CLI 可创建 `FinixDocVLClient` → `CreateClientTests`。
- 非白名单快速失败 → `FinixDocClientConstructionTests`。
- multipart 字段正确 → `FinixDocParseChunkTests.test_parse_chunk_sends_multipart_fields`。
- JSON markdown 提取 → `FinixDocResponseParsingTests`。
- 文本响应作 Markdown → `FinixDocResponseParsingTests.test_parse_response_returns_plain_text_when_not_json`。
- 非 2xx 抛异常 → `FinixDocParseChunkTests.test_parse_chunk_retries_on_non_2xx`。
- 缓存命中不请求 → `FinixDocParseChunkTests.test_parse_chunk_skips_api_when_cache_hit`。
- 单图失败不中断 → MVP `test_run_pipeline_keeps_global_task_when_single_image_parse_fails` 仍 PASS。

**Placeholder scan：**

- 无 TODO / TBD / 「类似上一个任务」。
- Task 7 步骤明确，包含真实路径、命令和期望输出。

**Type consistency：**

- `FinixDocVLClient.__init__` 参数在 Task 2 定义；Task 5 / Task 6 引用一致（`user_id`、`api_key`、`endpoint`、`timeout`、`max_retries`、`cache_dir`）。
- `_cache_key(chunk) -> str` / `_read_cache(key) -> str | None` / `_write_cache(key, markdown) -> None` 在 Task 4 定义，Task 5 使用签名一致。
- `_parse_response(response) -> str` 在 Task 3 定义，Task 5 `_call_api` 调用一致。
- `create_client(args: argparse.Namespace)` 在 Task 6 定义；测试中 `_build_args` 构造的 Namespace 字段覆盖 `args.client`、`args.gt_dir`、`args.user_id`、`args.api_key`、`args.endpoint`、`args.timeout`、`args.max_retries`、`args.cache_dir`，与 `build_parser` 输出对齐。
- `ImageChunk` / `ImageRecord` 在 MVP Task 1 定义，本计划沿用，未引入新模型。
