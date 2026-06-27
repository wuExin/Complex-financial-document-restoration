# tests/restore/test_prompts.py
"""prompts 模块的单元测试。"""
from __future__ import annotations

from src.restore.prompts import default_prompt, get_prompt


def test_default_prompt_mentions_markdown():
    p = default_prompt()
    assert "Markdown" in p or "markdown" in p
    assert len(p) > 20


def test_get_prompt_returns_string():
    p = get_prompt()
    assert isinstance(p, str)
    assert len(p) > 0
