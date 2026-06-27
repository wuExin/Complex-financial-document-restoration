# src/restore/finix_client.py
"""FinixDoc-VL 客户端接口。

- FinixClient: Protocol，所有上游模块依赖这个抽象
- MockFinixClient: 测试替身，返回确定性响应
- HTTPFinixClient: 真实实现（Task 8 加入此文件）
"""
from __future__ import annotations

import hashlib
import json
import time
from io import BytesIO
from pathlib import Path
from typing import Callable, Protocol

import requests
from PIL import Image


class FinixClient(Protocol):
    """FinixDoc-VL 客户端接口。"""

    def recognize(self, image: Image.Image) -> str:
        """识别图像，返回 Markdown 字符串。"""
        ...


class MockFinixClient:
    """测试用 Mock 客户端。

    - default_response: 默认返回值
    - responder: 可选 callable，输入 image 返回字符串（覆盖 default）
    """

    def __init__(
        self,
        default_response: str = "# Mock markdown",
        responder: Callable[[Image.Image], str] | None = None,
    ):
        self.default_response = default_response
        self.responder = responder
        self.call_count = 0

    def recognize(self, image: Image.Image) -> str:
        self.call_count += 1
        if self.responder is not None:
            return self.responder(image)
        return self.default_response


# ========== HTTPFinixClient ==========

def _encode_image_jpeg(image: Image.Image) -> bytes:
    """PIL.Image → JPEG bytes（API 要求 multipart 文件）。"""
    buf = BytesIO()
    rgb = image.convert("RGB") if image.mode != "RGB" else image
    rgb.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _cache_key_for_image(image: Image.Image) -> str:
    """缓存 key：图像字节的 sha256。"""
    return hashlib.sha256(_encode_image_jpeg(image)).hexdigest()


class _ApiError(Exception):
    """API 业务级错误（success=false），不可重试。"""


class HTTPFinixClient:
    """真实 FinixDoc-VL 客户端。

    - 缓存：sha256(image bytes) → markdown，存磁盘 JSON
    - 重试：网络/超时/5xx 重试 max_retries 次（指数退避）；4xx 业务错误不重试
    - 并发：实例级 Semaphore（pipeline 与 runner 共享一个实例）
    """

    URL = "https://finixdocapi.alipay.com/api/finix_doc/call_with_file"

    def __init__(
        self,
        user_id: str,
        api_key: str,
        cache_dir: Path,
        timeout: int = 60,
        max_retries: int = 3,
        max_concurrency: int = 8,
    ):
        self.user_id = user_id
        self.api_key = api_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        import threading

        self._sem = threading.Semaphore(max_concurrency)

    def recognize(self, image: Image.Image) -> str:
        """识别图像，返回 Markdown。失败返回空字符串。"""
        key = _cache_key_for_image(image)
        cache_file = self.cache_dir / f"{key}.json"

        # 1. 缓存命中？
        cached = self._read_cache(cache_file)
        if cached is not None:
            return cached

        # 2. 调 API（限并发）
        image_bytes = _encode_image_jpeg(image)
        with self._sem:
            markdown = self._call_with_retry(image_bytes)

        # 3. 成功才写缓存
        if markdown:
            self._write_cache(cache_file, markdown)
        return markdown

    def _read_cache(self, cache_file: Path) -> str | None:
        if not cache_file.exists():
            return None
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))["markdown"]
        except (json.JSONDecodeError, KeyError, OSError):
            # 损坏的缓存删掉
            try:
                cache_file.unlink()
            except OSError:
                pass
            return None

    def _write_cache(self, cache_file: Path, markdown: str) -> None:
        try:
            cache_file.write_text(
                json.dumps({"markdown": markdown}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass  # 缓存写失败不影响主流程

    def _call_with_retry(self, image_bytes: bytes) -> str:
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self._post_and_parse(image_bytes)
            except _ApiError:
                # 业务级错误不重试
                return ""
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
        # 全部重试失败
        return ""

    def _post_and_parse(self, image_bytes: bytes) -> str:
        files = {"file": ("image.jpg", BytesIO(image_bytes), "image/jpeg")}
        data = {
            "userId": self.user_id,
            "apiKey": self.api_key,
            "fileName": "image.jpg",
        }
        resp = requests.post(self.URL, data=data, files=files, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        resp_json = resp.json()
        if not resp_json.get("success"):
            raise _ApiError(resp_json.get("message", "unknown API error"))
        result_str = resp_json.get("result", {}).get("result")
        if not result_str:
            raise _ApiError("empty result field")
        parsed = json.loads(result_str)
        return parsed["choices"][0]["message"]["content"]
