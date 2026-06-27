# src/restore/config.py
"""配置加载：从环境变量读，提供合理默认值。

API 凭据必须通过环境变量提供，不进代码、不进 git。
其他参数（切块阈值等）有默认值，可被环境变量覆盖。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _project_root() -> Path:
    """返回项目根目录（包含 src/ 的那一层）。"""
    return Path(__file__).resolve().parent.parent.parent


@dataclass
class Config:
    """流水线运行配置。"""

    finix_user_id: str
    finix_api_key: str
    chunk_threshold: int  # 触发切块的最长边像素
    chunk_height: int  # 单块高度像素
    chunk_overlap: int  # 相邻块重叠像素
    concurrency: int  # 全局并发上限
    cache_dir: Path
    submission_csv: Path
    predictions_dir: Path
    eval_dir: Path

    @classmethod
    def from_env(cls, load_dotenv: bool = False) -> "Config":
        """从环境变量构造 Config。

        Args:
            load_dotenv: 是否尝试加载项目根的 .env 文件。测试默认 False 避免污染。
        """
        if load_dotenv:
            try:
                from dotenv import load_dotenv as _load

                _load(_project_root() / ".env")
            except ImportError:
                pass  # python-dotenv 未装也不影响

        outputs = _project_root() / "outputs"
        return cls(
            finix_user_id=os.environ.get("FINIX_USER_ID", ""),
            finix_api_key=os.environ.get("FINIX_API_KEY", ""),
            chunk_threshold=int(os.environ.get("RESTORE_CHUNK_THRESHOLD", "8000")),
            chunk_height=int(os.environ.get("RESTORE_CHUNK_HEIGHT", "6000")),
            chunk_overlap=int(os.environ.get("RESTORE_CHUNK_OVERLAP", "1000")),
            concurrency=int(os.environ.get("RESTORE_CONCURRENCY", "8")),
            cache_dir=outputs / "finix_cache",
            submission_csv=outputs / "submission.csv",
            predictions_dir=outputs / "predictions",
            eval_dir=outputs / "eval",
        )
