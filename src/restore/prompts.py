# src/restore/prompts.py
"""给 FinixDoc-VL 的 prompt 模板集中管理。

Phase 1 只用一个通用 prompt。Phase 3 可以扩展为针对表格/长文档的多个 prompt。
"""
from __future__ import annotations


def default_prompt() -> str:
    """Phase 1 默认 prompt：要求识别为 Markdown。"""
    return (
        "请将图片中的内容识别为标准 Markdown 格式输出。要求：\n"
        "1. 完整保留所有文字、表格、标题、列表、脚注\n"
        "2. 标题用 # / ## / ### 等表示层级\n"
        "3. 表格用标准 Markdown 表格语法（| 分隔）\n"
        "4. 不要添加图片描述、不要输出无关说明，直接输出 Markdown 内容"
    )


def get_prompt() -> str:
    """获取当前生效的 prompt。预留扩展点。"""
    return default_prompt()
