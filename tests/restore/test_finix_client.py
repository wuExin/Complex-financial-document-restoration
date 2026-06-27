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
