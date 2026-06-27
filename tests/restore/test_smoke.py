"""Live API smoke test。

默认 skip，避免单元测试触网。手动运行：
    pytest tests/restore/test_smoke.py -v -m live

需要环境变量 FINIX_USER_ID / FINIX_API_KEY。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from src.restore.chunking import FixedHeightChunker
from src.restore.config import Config
from src.restore.finix_client import HTTPFinixClient
from src.restore.pipeline import process_image

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def _skip_without_creds():
    if not os.environ.get("FINIX_USER_ID") or not os.environ.get("FINIX_API_KEY"):
        pytest.skip("FINIX_USER_ID / FINIX_API_KEY not set")


def test_smoke_one_small_image(tmp_path: Path):
    """跑一张小图，验证 API 端到端可用。"""
    cfg = Config.from_env()
    client = HTTPFinixClient(
        user_id=cfg.finix_user_id,
        api_key=cfg.finix_api_key,
        cache_dir=tmp_path / "cache",
    )
    img = Image.new("RGB", (500, 500), (255, 255, 255))
    result = process_image(
        image=img,
        image_id="smoke-test",
        client=client,
        chunker=FixedHeightChunker(),
    )
    # API 可能返回空字符串（如配额耗尽），但流程不应崩溃
    assert result.final_markdown is not None
    assert isinstance(result.final_markdown, str)
