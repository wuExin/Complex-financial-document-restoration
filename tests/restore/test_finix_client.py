# tests/restore/test_finix_client.py
"""finix_client 模块的单元测试（Mock 部分）。"""
from __future__ import annotations

from PIL import Image

from src.restore.finix_client import FinixClient, MockFinixClient


def test_mock_returns_default_response():
    mock = MockFinixClient(default_response="# Default MD")
    img = Image.new("RGB", (100, 100))
    result = mock.recognize(img)
    assert result == "# Default MD"


def test_mock_counts_calls():
    mock = MockFinixClient()
    img = Image.new("RGB", (100, 100))
    assert mock.call_count == 0
    mock.recognize(img)
    mock.recognize(img)
    assert mock.call_count == 2


def test_mock_accepts_custom_responder():
    """responder 函数根据 image 返回不同响应。"""
    mock = MockFinixClient(responder=lambda img: f"Size: {img.size[0]}x{img.size[1]}")
    r1 = mock.recognize(Image.new("RGB", (100, 200)))
    r2 = mock.recognize(Image.new("RGB", (300, 400)))
    assert r1 == "Size: 100x200"
    assert r2 == "Size: 300x400"


def test_protocol_satisfied():
    client: FinixClient = MockFinixClient()
    img = Image.new("RGB", (10, 10))
    assert isinstance(client.recognize(img), str)


# ========== HTTPFinixClient Tests ==========
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.restore.finix_client import HTTPFinixClient


def _fake_api_response(markdown: str = "# Hello") -> dict:
    """构造一个 mimicking 真实 API 返回的字典。"""
    return {
        "success": True,
        "result": {
            "result": json.dumps(
                {"choices": [{"message": {"content": markdown}}]}
            )
        },
    }


def test_http_client_parses_response(tmp_path):
    client = HTTPFinixClient(
        user_id="u", api_key="k", cache_dir=tmp_path / "cache"
    )
    img = Image.new("RGB", (100, 100))
    with patch("src.restore.finix_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = _fake_api_response("# Hello MD")
        result = client.recognize(img)
    assert result == "# Hello MD"


def test_http_client_caches(tmp_path):
    """第二次调同样 image，不应再发 HTTP 请求。"""
    client = HTTPFinixClient(
        user_id="u", api_key="k", cache_dir=tmp_path / "cache"
    )
    img = Image.new("RGB", (100, 100))
    with patch("src.restore.finix_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = _fake_api_response("# Cached")
        r1 = client.recognize(img)
        r2 = client.recognize(img)
    assert r1 == r2 == "# Cached"
    assert mock_post.call_count == 1  # 只调了一次


def test_http_client_corrupt_cache_refetches(tmp_path):
    client = HTTPFinixClient(
        user_id="u", api_key="k", cache_dir=tmp_path / "cache"
    )
    img = Image.new("RGB", (100, 100))
    # 预先写入损坏的缓存
    from src.restore.finix_client import _cache_key_for_image
    key = _cache_key_for_image(img)
    (tmp_path / "cache" / f"{key}.json").write_text("not json {")

    with patch("src.restore.finix_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = _fake_api_response("# Fresh")
        result = client.recognize(img)
    assert result == "# Fresh"
    assert mock_post.call_count == 1


def test_http_client_retries_on_failure(tmp_path):
    client = HTTPFinixClient(
        user_id="u", api_key="k", cache_dir=tmp_path / "cache", max_retries=3
    )
    img = Image.new("RGB", (100, 100))
    with patch("src.restore.finix_client.requests.post") as mock_post, \
         patch("src.restore.finix_client.time.sleep"):  # 跳过真实等待
        # 前两次抛异常，第三次成功
        mock_post.side_effect = [
            RuntimeError("network error"),
            RuntimeError("network error"),
            MagicMock(status_code=200,
                      json=lambda: _fake_api_response("# Success")),
        ]
        result = client.recognize(img)
    assert result == "# Success"
    assert mock_post.call_count == 3


def test_http_client_returns_empty_after_max_retries(tmp_path):
    client = HTTPFinixClient(
        user_id="u", api_key="k", cache_dir=tmp_path / "cache", max_retries=3
    )
    img = Image.new("RGB", (100, 100))
    with patch("src.restore.finix_client.requests.post") as mock_post, \
         patch("src.restore.finix_client.time.sleep"):
        mock_post.side_effect = RuntimeError("always fails")
        result = client.recognize(img)
    assert result == ""
    assert mock_post.call_count == 3


def test_http_client_api_error_returns_empty(tmp_path):
    """success=false 时不重试，直接返回空。"""
    client = HTTPFinixClient(
        user_id="u", api_key="k", cache_dir=tmp_path / "cache", max_retries=3
    )
    img = Image.new("RGB", (100, 100))
    with patch("src.restore.finix_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "success": False, "message": "Invalid API key"
        }
        result = client.recognize(img)
    assert result == ""
    assert mock_post.call_count == 1  # success=false 是不可重试错误
