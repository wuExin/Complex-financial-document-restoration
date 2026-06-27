# src/restore/finix_client.py
"""FinixDoc-VL 客户端接口。

- FinixClient: Protocol，所有上游模块依赖这个抽象
- MockFinixClient: 测试替身，返回确定性响应
- HTTPFinixClient: 真实实现（Task 8 加入此文件）
"""
from __future__ import annotations

from typing import Callable, Protocol

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
