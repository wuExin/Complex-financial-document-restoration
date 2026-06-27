# 还原流水线 Phase 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现"固定高度切块 + FinixDoc-VL 识别 + 编辑距离去重"端到端流水线，产出可提交 CSV，并支持本地 Text Edit 评测和浏览器库化调用。

**Architecture:** Protocol 抽象（`Chunker` / `Merger` / `FinixClient`）+ 单图同步 pipeline + 批处理 runner（图级并发 + 单 writer + 断点续跑）+ 本地评测。所有模块为可 import 的纯 Python，浏览器通过 Flask 路由调用。

**Tech Stack:** Python 3.10+、Pillow、requests、python-dotenv、pytest（现有）、Flask（现有）

**Spec:** `docs/superpowers/specs/2026-06-27-restore-pipeline-phase1-design.md`

---

## 前置说明

- **依赖项**：本计划新增 `requests`、`python-dotenv` 两个依赖
- **环境变量**：实现需要 `FINIX_USER_ID` 和 `FINIX_API_KEY`（仅在调用真实 API 时；单元测试用 MockFinixClient 不需要）
- **分支**：当前在 `feat/image-gallery`。本计划在该分支上继续提交。如果想隔离，可 `git checkout -b feat/restore-pipeline-phase1`
- **测试运行**：所有 pytest 命令从项目根目录运行
- **现有测试**：必须保持 `tests/test_app.py`、`tests/test_gen_thumbs.py` 通过（16 个用例）

---

## Task 1: 项目脚手架与依赖

**Files:**
- Create: `src/restore/__init__.py`
- Create: `tests/restore/__init__.py`
- Create: `.env.example`
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: 创建 `src/restore/__init__.py`（空文件标记 Python 包）**

```python
# src/restore/__init__.py
"""AFAC 还原流水线：图像 → Markdown。"""
```

- [ ] **Step 2: 创建 `tests/restore/__init__.py`（空文件）**

空文件，仅用于 pytest 包识别。

- [ ] **Step 3: 更新 `requirements.txt` 添加新依赖**

修改 `requirements.txt` 内容为：
```
flask>=3.0
pillow>=10.0
pytest>=8.0
requests>=2.31
python-dotenv>=1.0
```

- [ ] **Step 4: 创建 `.env.example`**

```
# FinixDoc-VL API 凭据（从钉钉群 179205019946 获取）
FINIX_USER_ID=your_user_id_here
FINIX_API_KEY=your_api_key_here

# 可选：覆盖默认配置
# RESTORE_CHUNK_THRESHOLD=8000
# RESTORE_CHUNK_HEIGHT=6000
# RESTORE_CHUNK_OVERLAP=1000
# RESTORE_CONCURRENCY=8
```

- [ ] **Step 5: 把 `.env` 加入 `.gitignore`**

在 `.gitignore` 顶部添加（如果还没有）：
```
.env
```

- [ ] **Step 6: 安装新依赖并验证 import**

```bash
pip install -r requirements.txt
python -c "import src.restore; print('OK')"
```

预期输出：`OK`

- [ ] **Step 7: 提交**

```bash
git add src/restore/__init__.py tests/restore/__init__.py .env.example requirements.txt .gitignore
git commit -m "feat(restore): scaffold restore package + add requests/dotenv deps"
```

---

## Task 2: types 模块（数据类）

**Files:**
- Create: `src/restore/types.py`
- Create: `tests/restore/test_types.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_types.py`**

```python
# tests/restore/test_types.py
"""types 模块的单元测试。"""
from __future__ import annotations

from PIL import Image

from src.restore.types import (
    Chunk,
    ChunkResult,
    MergeDecision,
    PipelineResult,
)


def test_chunk_construction():
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=50)
    assert c.bbox == (0, 0, 100, 200)
    assert c.overlap_top == 0
    assert c.overlap_bottom == 50


def test_chunk_to_dict_excludes_image():
    """image 字段不可 JSON 序列化，to_dict 必须排除。"""
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=0)
    d = c.to_dict()
    assert "image" not in d
    assert d["bbox"] == [0, 0, 100, 200]


def test_chunk_result_to_dict():
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=0)
    cr = ChunkResult(chunk=c, raw_markdown="# Hello", elapsed_ms=120, cached=False)
    d = cr.to_dict()
    assert d["raw_markdown"] == "# Hello"
    assert d["elapsed_ms"] == 120
    assert d["cached"] is False
    assert d["chunk"]["bbox"] == [0, 0, 100, 200]


def test_merge_decision_to_dict():
    md = MergeDecision(
        left_chunk_idx=0,
        right_chunk_idx=1,
        left_tail="tail text",
        right_head="head text",
        normalized_edit_distance=0.15,
        kept="merged",
    )
    d = md.to_dict()
    assert d["left_chunk_idx"] == 0
    assert d["kept"] == "merged"
    assert d["normalized_edit_distance"] == 0.15


def test_pipeline_result_to_dict():
    img = Image.new("RGB", (100, 200))
    c = Chunk(image=img, bbox=(0, 0, 100, 200), overlap_top=0, overlap_bottom=0)
    cr = ChunkResult(chunk=c, raw_markdown="text", elapsed_ms=100, cached=False)
    pr = PipelineResult(
        image_id="test-uuid",
        image_shape=(100, 200),
        chunker_name="fixed_height",
        chunks=[cr],
        merge_decisions=[],
        final_markdown="text",
        ground_truth=None,
        elapsed_ms=100,
    )
    d = pr.to_dict()
    assert d["image_id"] == "test-uuid"
    assert d["image_shape"] == [100, 200]
    assert d["chunker_name"] == "fixed_height"
    assert len(d["chunks"]) == 1
    assert d["final_markdown"] == "text"
    assert d["ground_truth"] is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_types.py -v
```

预期：`ImportError: cannot import name 'Chunk' from 'src.restore.types'`

- [ ] **Step 3: 实现 `src/restore/types.py`**

```python
# src/restore/types.py
"""流水线各阶段传递的数据结构。

所有 dataclass 提供 to_dict() 以便序列化为 JSON（给浏览器 /api/restore 用）。
PIL.Image 不可 JSON 序列化，所有 to_dict 都排除 image 字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from PIL import Image


@dataclass
class Chunk:
    """切块后的一张子图。"""

    image: Image.Image
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) 在原图坐标系
    overlap_top: int  # 与上一块顶部的重叠像素数
    overlap_bottom: int  # 与下一块底部的重叠像素数

    def to_dict(self) -> dict:
        """返回不含 image 的可序列化字典。"""
        return {
            "bbox": list(self.bbox),
            "overlap_top": self.overlap_top,
            "overlap_bottom": self.overlap_bottom,
        }


@dataclass
class ChunkResult:
    """单块识别结果。"""

    chunk: Chunk
    raw_markdown: str  # FinixDoc-VL 原始返回
    elapsed_ms: int
    cached: bool  # 是否命中磁盘缓存

    def to_dict(self) -> dict:
        return {
            "chunk": self.chunk.to_dict(),
            "raw_markdown": self.raw_markdown,
            "elapsed_ms": self.elapsed_ms,
            "cached": self.cached,
        }


@dataclass
class MergeDecision:
    """相邻块的一次去重决策记录。"""

    left_chunk_idx: int
    right_chunk_idx: int
    left_tail: str  # 左块参与比对的尾部文本
    right_head: str  # 右块参与比对的头部文本
    normalized_edit_distance: float
    kept: Literal["left", "right", "merged"]  # 最终保留策略

    def to_dict(self) -> dict:
        return {
            "left_chunk_idx": self.left_chunk_idx,
            "right_chunk_idx": self.right_chunk_idx,
            "left_tail": self.left_tail,
            "right_head": self.right_head,
            "normalized_edit_distance": self.normalized_edit_distance,
            "kept": self.kept,
        }


@dataclass
class PipelineResult:
    """单图流水线完整结果（含中间结构）。"""

    image_id: str
    image_shape: tuple[int, int]  # (width, height)
    chunker_name: str
    chunks: list[ChunkResult]  # 按位置顺序
    merge_decisions: list[MergeDecision]
    final_markdown: str
    ground_truth: str | None  # 训练集才有
    elapsed_ms: int

    def to_dict(self) -> dict:
        return {
            "image_id": self.image_id,
            "image_shape": list(self.image_shape),
            "chunker_name": self.chunker_name,
            "chunks": [c.to_dict() for c in self.chunks],
            "merge_decisions": [m.to_dict() for m in self.merge_decisions],
            "final_markdown": self.final_markdown,
            "ground_truth": self.ground_truth,
            "elapsed_ms": self.elapsed_ms,
        }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_types.py -v
```

预期：5 个用例全 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/types.py tests/restore/test_types.py
git commit -m "feat(restore): add typed dataclasses (Chunk/ChunkResult/MergeDecision/PipelineResult)"
```

---

## Task 3: config 模块

**Files:**
- Create: `src/restore/config.py`
- Create: `tests/restore/test_config.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_config.py`**

```python
# tests/restore/test_config.py
"""config 模块的单元测试。"""
from __future__ import annotations

import pytest


def test_defaults(monkeypatch):
    """未设置任何环境变量时，使用默认值。"""
    # 清空相关环境变量
    for key in [
        "FINIX_USER_ID",
        "FINIX_API_KEY",
        "RESTORE_CHUNK_THRESHOLD",
        "RESTORE_CHUNK_HEIGHT",
        "RESTORE_CHUNK_OVERLAP",
        "RESTORE_CONCURRENCY",
    ]:
        monkeypatch.delenv(key, raising=False)

    from src.restore.config import Config

    cfg = Config.from_env()
    assert cfg.finix_user_id == ""
    assert cfg.finix_api_key == ""
    assert cfg.chunk_threshold == 8000
    assert cfg.chunk_height == 6000
    assert cfg.chunk_overlap == 1000
    assert cfg.concurrency == 8


def test_env_override(monkeypatch):
    monkeypatch.setenv("FINIX_USER_ID", "user123")
    monkeypatch.setenv("FINIX_API_KEY", "keyABC")
    monkeypatch.setenv("RESTORE_CHUNK_THRESHOLD", "4000")
    monkeypatch.setenv("RESTORE_CHUNK_HEIGHT", "3000")
    monkeypatch.setenv("RESTORE_CHUNK_OVERLAP", "500")
    monkeypatch.setenv("RESTORE_CONCURRENCY", "16")

    from src.restore.config import Config

    cfg = Config.from_env()
    assert cfg.finix_user_id == "user123"
    assert cfg.finix_api_key == "keyABC"
    assert cfg.chunk_threshold == 4000
    assert cfg.chunk_height == 3000
    assert cfg.chunk_overlap == 500
    assert cfg.concurrency == 16


def test_paths_are_under_outputs(monkeypatch, tmp_path):
    from src.restore.config import Config

    cfg = Config.from_env()
    assert cfg.cache_dir.name == "finix_cache"
    assert cfg.cache_dir.parent.name == "outputs"
    assert cfg.submission_csv.name == "submission.csv"
    assert cfg.predictions_dir.name == "predictions"
    assert cfg.eval_dir.name == "eval"


def test_load_dotenv_does_not_crash_without_file(monkeypatch, tmp_path):
    """没有 .env 文件时 from_env 不应崩溃。"""
    monkeypatch.chdir(tmp_path)
    from src.restore.config import Config

    cfg = Config.from_env(load_dotenv=True)
    assert cfg is not None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_config.py -v
```

预期：`ImportError: cannot import name 'Config' from 'src.restore.config'`

- [ ] **Step 3: 实现 `src/restore/config.py`**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_config.py -v
```

预期：4 个用例全 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/config.py tests/restore/test_config.py
git commit -m "feat(restore): add Config with env-var loading and defaults"
```

---

## Task 4: prompts 模块

**Files:**
- Create: `src/restore/prompts.py`
- Create: `tests/restore/test_prompts.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_prompts.py`**

```python
# tests/restore/test_prompts.py
"""prompts 模块的单元测试。"""
from __future__ import annotations

from src.restore.prompts import default_prompt, get_prompt


def test_default_prompt_mentions_markdown():
    p = default_prompt()
    assert "Markdown" in p or "markdown" in p
    assert len(p) > 20  # 不是空字符串


def test_get_prompt_returns_string():
    p = get_prompt()
    assert isinstance(p, str)
    assert len(p) > 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_prompts.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `src/restore/prompts.py`**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_prompts.py -v
```

预期：2 个用例 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/prompts.py tests/restore/test_prompts.py
git commit -m "feat(restore): add default FinixDoc-VL prompt template"
```

---

## Task 5: chunking 模块

**Files:**
- Create: `src/restore/chunking.py`
- Create: `tests/restore/test_chunking.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_chunking.py`**

```python
# tests/restore/test_chunking.py
"""chunking 模块的单元测试。"""
from __future__ import annotations

from PIL import Image

from src.restore.chunking import Chunker, FixedHeightChunker


def test_small_image_returns_single_chunk():
    """小于阈值的图返回单块（整图）。"""
    img = Image.new("RGB", (1000, 2000))  # max=2000 < 8000
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    assert len(chunks) == 1
    assert chunks[0].bbox == (0, 0, 1000, 2000)
    assert chunks[0].overlap_top == 0
    assert chunks[0].overlap_bottom == 0


def test_tall_image_chunks_vertically():
    """长文档按高度切片，每块保留全宽。"""
    img = Image.new("RGB", (1500, 15000))  # 高度 15000 > 8000
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    # 15000 / (6000 - 1000) = 3 块（5000 步长）
    assert len(chunks) == 3
    # 所有块宽度都是原图全宽
    for c in chunks:
        assert c.bbox[0] == 0
        assert c.bbox[2] == 1500
    # 第一块从 0 开始
    assert chunks[0].bbox[1] == 0
    assert chunks[0].bbox[3] == 6000
    assert chunks[0].overlap_top == 0
    assert chunks[0].overlap_bottom == 1000
    # 最后一块到 15000 结束
    assert chunks[-1].bbox[3] == 15000
    assert chunks[-1].overlap_top == 1000
    assert chunks[-1].overlap_bottom == 0


def test_wide_table_image_chunks_vertically_too():
    """表格文档若超阈值也按高度切（保留全宽）。"""
    img = Image.new("RGB", (9000, 9000))  # 两边都超阈值
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    assert len(chunks) == 2
    for c in chunks:
        assert c.bbox[2] == 9000  # 宽度保留


def test_step_is_chunk_height_minus_overlap():
    """步长 = 块高 - 重叠。"""
    img = Image.new("RGB", (1000, 20000))
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    chunks = chunker.chunk(img, "test-id")
    # 第一块 [0, 6000]，第二块 [5000, 11000]，第三块 [10000, 16000]，第四块 [14000, 20000]
    assert chunks[0].bbox == (0, 0, 1000, 6000)
    assert chunks[1].bbox == (0, 5000, 1000, 11000)
    assert chunks[2].bbox == (0, 10000, 1000, 16000)
    assert chunks[3].bbox == (0, 14000, 1000, 20000)
    # 中间块两端都有 overlap
    assert chunks[1].overlap_top == 1000
    assert chunks[1].overlap_bottom == 1000


def test_protocol_satisfied():
    """FixedHeightChunker 应满足 Chunker Protocol。"""
    chunker: Chunker = FixedHeightChunker()
    img = Image.new("RGB", (100, 100))
    chunks = chunker.chunk(img, "id")
    assert isinstance(chunks, list)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_chunking.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `src/restore/chunking.py`**

```python
# src/restore/chunking.py
"""切块策略：Chunker Protocol + Phase 1 唯一实现 FixedHeightChunker。

Phase 2 会新增 LayoutAwareChunker（用 PP-Structure），实现同一个 Protocol，
pipeline 不需要改任何代码，只换 chunker 实例。
"""
from __future__ import annotations

from typing import Protocol

from PIL import Image

from .types import Chunk


class Chunker(Protocol):
    """切块策略接口。"""

    def chunk(self, image: Image.Image, image_id: str) -> list[Chunk]:
        ...


class FixedHeightChunker:
    """按固定高度切块。

    若 max(w, h) ≤ threshold，返回单块（整图）。
    否则沿高度方向以 (chunk_height - overlap) 为步长切片，最后一块对齐到原图底部。

    长文档与表格文档统一策略：始终保留全宽，沿高度切。
    """

    def __init__(
        self,
        threshold: int = 8000,
        chunk_height: int = 6000,
        overlap: int = 1000,
    ):
        if overlap >= chunk_height:
            raise ValueError(f"overlap ({overlap}) 必须 < chunk_height ({chunk_height})")
        self.threshold = threshold
        self.chunk_height = chunk_height
        self.overlap = overlap

    @property
    def name(self) -> str:
        return "fixed_height"

    def chunk(self, image: Image.Image, image_id: str) -> list[Chunk]:
        w, h = image.size
        if max(w, h) <= self.threshold:
            return [
                Chunk(
                    image=image,
                    bbox=(0, 0, w, h),
                    overlap_top=0,
                    overlap_bottom=0,
                )
            ]

        step = self.chunk_height - self.overlap
        chunks: list[Chunk] = []
        y = 0
        idx = 0
        while y < h:
            y0 = y
            y1 = min(y0 + self.chunk_height, h)
            cropped = image.crop((0, y0, w, y1))
            overlap_top = self.overlap if idx > 0 else 0
            # 是否是最后一块：如果 y1 已经到原图底部
            is_last = y1 >= h
            overlap_bottom = self.overlap if not is_last else 0
            chunks.append(
                Chunk(
                    image=cropped,
                    bbox=(0, y0, w, y1),
                    overlap_top=overlap_top,
                    overlap_bottom=overlap_bottom,
                )
            )
            if is_last:
                break
            y += step
            idx += 1
        return chunks
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_chunking.py -v
```

预期：5 个用例 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/chunking.py tests/restore/test_chunking.py
git commit -m "feat(restore): add Chunker Protocol + FixedHeightChunker"
```

---

## Task 6: dedup 模块

**Files:**
- Create: `src/restore/dedup.py`
- Create: `tests/restore/test_dedup.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_dedup.py`**

```python
# tests/restore/test_dedup.py
"""dedup 模块的单元测试。"""
from __future__ import annotations

from PIL import Image

from src.restore.dedup import EditDistanceMerger, Merger
from src.restore.types import Chunk, ChunkResult


def _make_chunk_result(text: str, idx: int = 0) -> ChunkResult:
    img = Image.new("RGB", (100, 100))
    return ChunkResult(
        chunk=Chunk(image=img, bbox=(0, idx * 100, 100, (idx + 1) * 100),
                    overlap_top=0, overlap_bottom=0),
        raw_markdown=text,
        elapsed_ms=10,
        cached=False,
    )


def test_no_overlap_just_concatenates():
    """两块无重叠内容时，直接拼接。"""
    merger = EditDistanceMerger(window=200, threshold=0.3)
    results = [
        _make_chunk_result("Hello world.", 0),
        _make_chunk_result("Goodbye world.", 1),
    ]
    merged, decisions = merger.merge(results)
    assert "Hello world." in merged
    assert "Goodbye world." in merged
    assert len(decisions) == 1
    assert decisions[0].kept == "left"  # 仅追加


def test_full_overlap_dedups():
    """右块头部与左块尾部完全相同时，去重保留一份。"""
    merger = EditDistanceMerger(window=200, threshold=0.3)
    overlap_text = "This is the overlapping tail content."
    left = "Header content.\n\n" + overlap_text
    right = overlap_text + "\n\nFooter content."
    results = [_make_chunk_result(left, 0), _make_chunk_result(right, 1)]
    merged, decisions = merger.merge(results)
    # 重叠段在结果里只出现一次
    assert merged.count(overlap_text) == 1
    assert "Header content." in merged
    assert "Footer content." in merged
    assert decisions[0].kept == "merged"
    assert decisions[0].normalized_edit_distance < 0.3


def test_three_chunks_merges_sequentially():
    """三块依次合并，生成两个 decision。"""
    merger = EditDistanceMerger(window=200, threshold=0.3)
    results = [
        _make_chunk_result("AAA common1", 0),
        _make_chunk_result("common1 BBB common2", 1),
        _make_chunk_result("common2 CCC", 2),
    ]
    merged, decisions = merger.merge(results)
    assert len(decisions) == 2
    assert "AAA" in merged
    assert "BBB" in merged
    assert "CCC" in merged


def test_single_chunk_no_decisions():
    merger = EditDistanceMerger()
    results = [_make_chunk_result("only one chunk", 0)]
    merged, decisions = merger.merge(results)
    assert merged == "only one chunk"
    assert decisions == []


def test_protocol_satisfied():
    merger: Merger = EditDistanceMerger()
    assert hasattr(merger, "merge")


def test_empty_input_returns_empty():
    merger = EditDistanceMerger()
    merged, decisions = merger.merge([])
    assert merged == ""
    assert decisions == []
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_dedup.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `src/restore/dedup.py`**

```python
# src/restore/dedup.py
"""拼接去重策略：Merger Protocol + Phase 1 唯一实现 EditDistanceMerger。

算法（每对相邻块）：
1. 取左块尾部 window 字符 + 右块头部 window 字符
2. 算归一化编辑距离（levenshtein / max(len)）
3. 若 < threshold，视为重叠；用最长公共子串定位切点
4. 保留：左块到 LCS 结束 + 右块从 LCS 结束之后

否则直接拼接。
"""
from __future__ import annotations

from typing import Protocol

from .types import ChunkResult, MergeDecision


def _levenshtein(a: str, b: str) -> int:
    """标准动态规划编辑距离。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _normalized_edit_distance(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    return _levenshtein(a, b) / max(len(a), len(b))


def _longest_common_substring(a: str, b: str) -> str:
    """返回 a 和 b 的最长公共子串。"""
    if not a or not b:
        return ""
    # dp[i][j] = 以 a[i-1]、b[j-1] 结尾的最长公共子串长度
    best_len = 0
    best_end_a = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len = cur[j]
                    best_end_a = i
        prev = cur
    return a[best_end_a - best_len : best_end_a]


class Merger(Protocol):
    """拼接去重接口。"""

    def merge(self, results: list[ChunkResult]) -> tuple[str, list[MergeDecision]]:
        ...


class EditDistanceMerger:
    """基于归一化编辑距离 + 最长公共子串的拼接去重。"""

    def __init__(self, window: int = 200, threshold: float = 0.3, min_lcs_len: int = 20):
        self.window = window
        self.threshold = threshold
        self.min_lcs_len = min_lcs_len  # LCS 太短不算真重叠

    def merge(self, results: list[ChunkResult]) -> tuple[str, list[MergeDecision]]:
        if not results:
            return "", []
        if len(results) == 1:
            return results[0].raw_markdown, []

        decisions: list[MergeDecision] = []
        accumulated = results[0].raw_markdown
        for i in range(1, len(results)):
            left = accumulated
            right = results[i].raw_markdown
            left_tail = left[-self.window :]
            right_head = right[: self.window]
            ned = _normalized_edit_distance(left_tail, right_head)

            if ned < self.threshold:
                lcs = _longest_common_substring(left_tail, right_head)
                if len(lcs) >= self.min_lcs_len:
                    # 在 right_head 里找 lcs 的结束位置
                    lcs_end_in_right_head = right_head.rfind(lcs) + len(lcs)
                    # 同样的位置对齐到完整 right
                    splice_point = lcs_end_in_right_head
                    accumulated = left + right[splice_point:]
                    decisions.append(
                        MergeDecision(
                            left_chunk_idx=i - 1,
                            right_chunk_idx=i,
                            left_tail=left_tail,
                            right_head=right_head,
                            normalized_edit_distance=ned,
                            kept="merged",
                        )
                    )
                else:
                    accumulated = left + right
                    decisions.append(
                        MergeDecision(
                            left_chunk_idx=i - 1,
                            right_chunk_idx=i,
                            left_tail=left_tail,
                            right_head=right_head,
                            normalized_edit_distance=ned,
                            kept="left",
                        )
                    )
            else:
                accumulated = left + right
                decisions.append(
                    MergeDecision(
                        left_chunk_idx=i - 1,
                        right_chunk_idx=i,
                        left_tail=left_tail,
                        right_head=right_head,
                        normalized_edit_distance=ned,
                        kept="left",
                    )
                )
        return accumulated, decisions
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_dedup.py -v
```

预期：6 个用例 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/dedup.py tests/restore/test_dedup.py
git commit -m "feat(restore): add Merger Protocol + EditDistanceMerger"
```

---

## Task 7: FinixClient Protocol + MockFinixClient

**Files:**
- Create: `src/restore/finix_client.py`
- Create: `tests/restore/test_finix_client.py`

此 Task 只定义 Protocol 和 Mock，真实 HTTP 实现 Task 8 加。

- [ ] **Step 1: 写失败测试 `tests/restore/test_finix_client.py`（先只测 Mock）**

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_finix_client.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `src/restore/finix_client.py`（仅 Protocol + Mock）**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_finix_client.py -v
```

预期：4 个用例 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/finix_client.py tests/restore/test_finix_client.py
git commit -m "feat(restore): add FinixClient Protocol + MockFinixClient"
```

---

## Task 8: HTTPFinixClient（真实 API 客户端）

**Files:**
- Modify: `src/restore/finix_client.py`（追加 HTTPFinixClient）
- Modify: `tests/restore/test_finix_client.py`（追加 HTTP 测试）

- [ ] **Step 1: 追加失败测试到 `tests/restore/test_finix_client.py`**

在文件末尾追加：

```python
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
    (tmp_path / "cache").mkdir()
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_finix_client.py -v
```

预期：6 个新用例都 `ImportError: cannot import name 'HTTPFinixClient'`

- [ ] **Step 3: 追加实现到 `src/restore/finix_client.py`**

在文件末尾追加：

```python
import hashlib
import json
import time
from io import BytesIO
from pathlib import Path

import requests


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
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_finix_client.py -v
```

预期：全部 10 个用例（Mock 4 + HTTP 6）PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/finix_client.py tests/restore/test_finix_client.py
git commit -m "feat(restore): add HTTPFinixClient with cache + retry + concurrency"
```

---

## Task 9: pipeline 模块（单图编排）

**Files:**
- Create: `src/restore/pipeline.py`
- Create: `tests/restore/test_pipeline.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_pipeline.py`**

```python
# tests/restore/test_pipeline.py
"""pipeline 模块的单元测试。"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from PIL import Image

from src.restore.chunking import FixedHeightChunker
from src.restore.dedup import EditDistanceMerger
from src.restore.finix_client import MockFinixClient
from src.restore.pipeline import process_image
from src.restore.types import PipelineResult


def test_process_small_image_single_chunk():
    """小图只产 1 块，无 merge decision。"""
    img = Image.new("RGB", (1000, 1000))
    client = MockFinixClient(default_response="# Small image MD")
    chunker = FixedHeightChunker(threshold=8000)
    merger = EditDistanceMerger()

    result = process_image(
        image=img,
        image_id="test-small",
        client=client,
        chunker=chunker,
        merger=merger,
    )
    assert isinstance(result, PipelineResult)
    assert result.image_id == "test-small"
    assert result.image_shape == (1000, 1000)
    assert result.chunker_name == "fixed_height"
    assert len(result.chunks) == 1
    assert result.chunks[0].raw_markdown == "# Small image MD"
    assert result.merge_decisions == []
    assert result.final_markdown == "# Small image MD"
    assert result.elapsed_ms >= 0


def test_process_large_image_multiple_chunks():
    """大图切多块，并发调 client，最后 merge。"""
    img = Image.new("RGB", (1500, 15000))
    # 模拟每块返回不同内容
    def responder(image):
        # 用图像高度作为内容标识
        return f"# Chunk h={image.size[1]}"

    client = MockFinixClient(responder=responder)
    chunker = FixedHeightChunker(threshold=8000, chunk_height=6000, overlap=1000)
    merger = EditDistanceMerger()

    result = process_image(
        image=img,
        image_id="test-large",
        client=client,
        chunker=chunker,
        merger=merger,
    )
    # 15000 / 5000 步长 = 3 块
    assert len(result.chunks) == 3
    assert client.call_count == 3
    # final_markdown 包含所有块的内容
    assert "h=6000" in result.final_markdown
    assert "h=5000" in result.final_markdown  # 中间块和最后块高 5000
    # 有 2 个 merge decision（3 块两两相邻）
    assert len(result.merge_decisions) == 2


def test_process_image_includes_ground_truth_when_provided():
    img = Image.new("RGB", (100, 100))
    client = MockFinixClient(default_response="x")
    result = process_image(
        image=img,
        image_id="x",
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        ground_truth="# Truth",
    )
    assert result.ground_truth == "# Truth"


def test_process_image_handles_empty_chunks():
    """理论上不会发生，但 pipeline 应能优雅处理。"""
    img = Image.new("RGB", (100, 100))
    client = MockFinixClient(default_response="x")
    chunker = FixedHeightChunker()
    merger = EditDistanceMerger()
    # 用一个返回空列表的假 chunker
    fake_chunker = MagicMock()
    fake_chunker.chunk.return_value = []
    fake_chunker.name = "empty"

    result = process_image(
        image=img,
        image_id="x",
        client=client,
        chunker=fake_chunker,
        merger=merger,
    )
    assert result.chunks == []
    assert result.final_markdown == ""
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_pipeline.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `src/restore/pipeline.py`**

```python
# src/restore/pipeline.py
"""单图编排：切块 → 并发识别 → 拼接去重 → 装配 PipelineResult。

process_image 是库入口，浏览器 /api/restore 直接调用。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from PIL import Image

from .chunking import Chunker, FixedHeightChunker
from .dedup import EditDistanceMerger, Merger
from .finix_client import FinixClient, MockFinixClient
from .types import ChunkResult, PipelineResult


def process_image(
    image: Image.Image,
    image_id: str,
    client: FinixClient,
    chunker: Chunker | None = None,
    merger: Merger | None = None,
    ground_truth: str | None = None,
    chunk_concurrency: int = 4,
) -> PipelineResult:
    """处理单张图像，返回完整 PipelineResult。

    Args:
        image: 输入 PIL 图像
        image_id: 图像标识（UUID 或文件名 stem）
        client: FinixDoc-VL 客户端（HTTP 或 Mock）
        chunker: 切块器，默认 FixedHeightChunker()
        merger: 合并器，默认 EditDistanceMerger()
        ground_truth: 训练集真值，可选（评测/可视化用）
        chunk_concurrency: 单图内块级并发上限

    Returns:
        PipelineResult，含每块识别结果与合并决策
    """
    if chunker is None:
        chunker = FixedHeightChunker()
    if merger is None:
        merger = EditDistanceMerger()

    start = time.monotonic()
    chunks = chunker.chunk(image, image_id)

    # 块级并发识别
    def _recognize(idx: int) -> tuple[int, ChunkResult]:
        chunk = chunks[idx]
        t0 = time.monotonic()
        md = client.recognize(chunk.image)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return idx, ChunkResult(
            chunk=chunk, raw_markdown=md, elapsed_ms=elapsed_ms, cached=False
        )

    results: list[ChunkResult | None] = [None] * len(chunks)
    if chunks:
        with ThreadPoolExecutor(max_workers=min(chunk_concurrency, len(chunks))) as ex:
            for idx, cr in ex.map(_recognize, range(len(chunks))):
                results[idx] = cr
    chunk_results: list[ChunkResult] = [r for r in results if r is not None]

    final_markdown, decisions = merger.merge(chunk_results)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    return PipelineResult(
        image_id=image_id,
        image_shape=image.size,
        chunker_name=getattr(chunker, "name", "unknown"),
        chunks=chunk_results,
        merge_decisions=decisions,
        final_markdown=final_markdown,
        ground_truth=ground_truth,
        elapsed_ms=elapsed_ms,
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_pipeline.py -v
```

预期：4 个用例 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/pipeline.py tests/restore/test_pipeline.py
git commit -m "feat(restore): add process_image orchestrator with chunk-level concurrency"
```

---

## Task 10: evaluate 模块

**Files:**
- Create: `src/restore/evaluate.py`
- Create: `tests/restore/test_evaluate.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_evaluate.py`**

```python
# tests/restore/test_evaluate.py
"""evaluate 模块的单元测试。"""
from __future__ import annotations

from pathlib import Path

from src.restore.evaluate import (
    EvalReport,
    evaluate_directory,
    text_edit_distance,
)


def test_identical_strings_distance_zero():
    assert text_edit_distance("hello", "hello") == 0.0


def test_completely_different_strings_distance_one():
    # 完全无公共字符（长度对齐）
    assert text_edit_distance("aaaa", "bbbb") == 1.0


def test_one_substitution():
    # hello vs hallo: 1 个替换 / 长度 5 = 0.2
    assert text_edit_distance("hello", "hallo") == 0.2


def test_empty_strings():
    assert text_edit_distance("", "") == 0.0


def test_one_empty_other_full():
    assert text_edit_distance("", "abc") == 1.0
    assert text_edit_distance("abc", "") == 1.0


def test_evaluate_directory(tmp_path: Path):
    pred_dir = tmp_path / "pred"
    truth_dir = tmp_path / "truth"
    pred_dir.mkdir()
    truth_dir.mkdir()

    # 两个样本
    (pred_dir / "uuid-1.md").write_text("hello world", encoding="utf-8")
    (truth_dir / "uuid-1.md").write_text("hello world", encoding="utf-8")
    (pred_dir / "uuid-2.md").write_text("hallo world", encoding="utf-8")
    (truth_dir / "uuid-2.md").write_text("hello world", encoding="utf-8")

    report = evaluate_directory(str(pred_dir), str(truth_dir))
    assert isinstance(report, EvalReport)
    assert len(report.per_sample) == 2
    # uuid-1 完美
    assert report.per_sample["uuid-1"] == 0.0
    # uuid-2 1 替换 / 11 = 约 0.09
    assert 0.05 < report.per_sample["uuid-2"] < 0.15
    # 均值在两者之间
    assert report.mean > 0


def test_evaluate_directory_missing_truth_skipped(tmp_path: Path):
    pred_dir = tmp_path / "pred"
    truth_dir = tmp_path / "truth"
    pred_dir.mkdir()
    truth_dir.mkdir()
    (pred_dir / "uuid-1.md").write_text("x", encoding="utf-8")
    (truth_dir / "uuid-1.md").write_text("x", encoding="utf-8")
    (pred_dir / "uuid-2.md").write_text("y", encoding="utf-8")
    # uuid-2 没有 truth

    report = evaluate_directory(str(pred_dir), str(truth_dir))
    assert "uuid-1" in report.per_sample
    assert "uuid-2" not in report.per_sample
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_evaluate.py -v
```

预期：`ImportError`

注意：上面 test_evaluate_directory 里有一处故意写错的语法 `(truth_dir / "uuid-2.md").write_text="hello world"`（应该是 `.write_text("hello world")`）。Step 3 之前先修正它：

- [ ] **Step 2.5: 修正测试文件中的语法错误**

把 `tests/restore/test_evaluate.py` 中：

```python
    (truth_dir / "uuid-2.md").write_text="hello world"
```

改成：

```python
    (truth_dir / "uuid-2.md").write_text("hello world", encoding="utf-8")
```

- [ ] **Step 3: 实现 `src/restore/evaluate.py`**

```python
# src/restore/evaluate.py
"""本地评测：text_edit_distance + 目录扫描评测。

Phase 1 仅实现 Text Edit（归一化字符级编辑距离）。
Phase 2 会加 TEDS（表格结构相似度）。
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def text_edit_distance(pred: str, truth: str) -> float:
    """归一化字符级编辑距离。

    Returns:
        0.0 = 完全相同；1.0 = 完全不同
    """
    if not pred and not truth:
        return 0.0
    return _levenshtein(pred, truth) / max(len(pred), len(truth))


@dataclass
class EvalReport:
    """评测报告。"""

    per_sample: dict[str, float] = field(default_factory=dict)
    mean: float = 0.0
    median: float = 0.0
    min: float = 0.0
    max: float = 0.0
    n_samples: int = 0

    def to_dict(self) -> dict:
        return {
            "per_sample": self.per_sample,
            "mean": self.mean,
            "median": self.median,
            "min": self.min,
            "max": self.max,
            "n_samples": self.n_samples,
        }


def evaluate_directory(pred_dir: str | Path, truth_dir: str | Path) -> EvalReport:
    """对比预测目录与真值目录下的同名 .md 文件，逐对算 text_edit。

    预测目录下存在但真值目录缺失的样本会被跳过（不计入）。
    """
    pred_dir = Path(pred_dir)
    truth_dir = Path(truth_dir)
    per_sample: dict[str, float] = {}
    for pred_file in pred_dir.glob("*.md"):
        stem = pred_file.stem
        truth_file = truth_dir / f"{stem}.md"
        if not truth_file.exists():
            continue
        pred = pred_file.read_text(encoding="utf-8")
        truth = truth_file.read_text(encoding="utf-8")
        per_sample[stem] = text_edit_distance(pred, truth)

    if not per_sample:
        return EvalReport()

    scores = list(per_sample.values())
    return EvalReport(
        per_sample=per_sample,
        mean=statistics.mean(scores),
        median=statistics.median(scores),
        min=min(scores),
        max=max(scores),
        n_samples=len(scores),
    )


def write_report(report: EvalReport, out_dir: str | Path) -> Path:
    """把报告写到 out_dir/report.json + summary.txt，返回 out_dir。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "summary.txt").write_text(
        f"n={report.n_samples} | mean={report.mean:.4f} | "
        f"median={report.median:.4f} | min={report.min:.4f} | max={report.max:.4f}\n",
        encoding="utf-8",
    )
    return out_dir
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_evaluate.py -v
```

预期：7 个用例 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/evaluate.py tests/restore/test_evaluate.py
git commit -m "feat(restore): add text_edit_distance + evaluate_directory"
```

---

## Task 11: runner 模块（批处理 + 并发 + 断点续跑）

**Files:**
- Create: `src/restore/runner.py`
- Create: `tests/restore/test_runner.py`

- [ ] **Step 1: 写失败测试 `tests/restore/test_runner.py`**

```python
# tests/restore/test_runner.py
"""runner 模块的单元测试。"""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image

from src.restore.chunking import FixedHeightChunker
from src.restore.dedup import EditDistanceMerger
from src.restore.finix_client import MockFinixClient
from src.restore.runner import run_directory


def _make_image(path: Path, size=(1000, 1000)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 200, 200)).save(path, "JPEG")


def test_run_directory_writes_csv(tmp_path: Path):
    img_dir = tmp_path / "imgs"
    _make_image(img_dir / "a.jpg")
    _make_image(img_dir / "b.jpg")
    _make_image(img_dir / "c.jpg")

    out_csv = tmp_path / "out.csv"
    client = MockFinixClient(default_response="# MD")
    run_directory(
        image_dirs=[img_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=2,
    )
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 3
    file_names = {r["file_name"] for r in rows}
    assert file_names == {"a.jpg", "b.jpg", "c.jpg"}
    for r in rows:
        assert r["ground_truth"] == "# MD"


def test_run_directory_resumes_from_existing_csv(tmp_path: Path):
    """已存在的 CSV 中的图被跳过，不重复耗 API。"""
    img_dir = tmp_path / "imgs"
    _make_image(img_dir / "a.jpg")
    _make_image(img_dir / "b.jpg")

    out_csv = tmp_path / "out.csv"
    # 预写入 a 的结果
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["file_name", "ground_truth"])
        w.writerow(["a.jpg", "# Previous run"])

    client = MockFinixClient(default_response="# Fresh MD")
    run_directory(
        image_dirs=[img_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=1,
    )
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 2
    by_name = {r["file_name"]: r["ground_truth"] for r in rows}
    # a 保持原值（跳过）
    assert by_name["a.jpg"] == "# Previous run"
    # b 是新跑的
    assert by_name["b.jpg"] == "# Fresh MD"
    # 只调了 1 次 API
    assert client.call_count == 1


def test_run_directory_eval_mode_writes_per_image_md(tmp_path: Path):
    """--eval-mode 时除了 CSV 还把 final_markdown 落到 predictions/<id>.md。"""
    img_dir = tmp_path / "imgs"
    _make_image(img_dir / "uuid-1.jpg")
    _make_image(img_dir / "uuid-2.jpg")

    out_csv = tmp_path / "out.csv"
    pred_dir = tmp_path / "pred"
    client = MockFinixClient(default_response="# MD")
    run_directory(
        image_dirs=[img_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=2,
        eval_mode=True,
        predictions_dir=pred_dir,
    )
    assert (pred_dir / "uuid-1.md").exists()
    assert (pred_dir / "uuid-2.md").exists()
    assert (pred_dir / "uuid-1.md").read_text(encoding="utf-8") == "# MD"


def test_run_directory_handles_multiple_dirs(tmp_path: Path):
    """支持多目录输入（长文档 + 表格文档）。"""
    long_dir = tmp_path / "long"
    table_dir = tmp_path / "table"
    _make_image(long_dir / "L1.jpg")
    _make_image(table_dir / "T1.jpg")

    out_csv = tmp_path / "out.csv"
    client = MockFinixClient(default_response="# MD")
    run_directory(
        image_dirs=[long_dir, table_dir],
        output_csv=out_csv,
        client=client,
        chunker=FixedHeightChunker(),
        merger=EditDistanceMerger(),
        max_workers=2,
    )
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 2
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/restore/test_runner.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 `src/restore/runner.py`**

```python
# src/restore/runner.py
"""批处理 runner：图级并发 + 单 writer 线程 + 断点续跑。

- 多目录输入：合并扫描所有目录的 *.jpg
- 断点续跑：output_csv 已存在的 file_name 跳过
- 单 writer：所有 worker 把结果投到 Queue，单一 writer 线程串行写 CSV
- eval_mode：额外把 final_markdown 落到 predictions_dir/<id>.md
"""
from __future__ import annotations

import csv
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from PIL import Image

from .chunking import Chunker, FixedHeightChunker
from .dedup import EditDistanceMerger, Merger
from .finix_client import FinixClient, MockFinixClient
from .pipeline import process_image


def _load_done_set(output_csv: Path) -> set[str]:
    """读 CSV 中已有的 file_name，用于断点续跑。"""
    if not output_csv.exists():
        return set()
    done: set[str] = set()
    with output_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "file_name" in row and row["file_name"]:
                done.add(row["file_name"])
    return done


def _ensure_csv_header(output_csv: Path) -> None:
    """CSV 不存在时写表头。存在时不破坏。"""
    if output_csv.exists():
        return
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["file_name", "ground_truth"])


def _scan_images(image_dirs: list[Path]) -> list[Path]:
    images: list[Path] = []
    for d in image_dirs:
        images.extend(sorted(Path(d).glob("*.jpg")))
        images.extend(sorted(Path(d).glob("*.png")))
    return images


def run_directory(
    image_dirs: list[Path | str],
    output_csv: Path | str,
    client: Optional[FinixClient] = None,
    chunker: Optional[Chunker] = None,
    merger: Optional[Merger] = None,
    max_workers: int = 8,
    time_budget_seconds: float = 2.8 * 3600,
    eval_mode: bool = False,
    predictions_dir: Path | str | None = None,
) -> dict:
    """批量跑流水线，写 CSV。

    Args:
        image_dirs: 图像目录列表
        output_csv: 输出 CSV 路径
        client: FinixClient（默认 MockFinixClient；生产应传 HTTPFinixClient）
        chunker: 切块器
        merger: 合并器
        max_workers: 图级并发上限
        time_budget_seconds: 时间预算，超过则停止派发新图（已派发的会完成）
        eval_mode: 是否额外写 predictions/<id>.md（评测用）
        predictions_dir: eval_mode 时的输出目录

    Returns:
        统计字典 {processed, skipped, failed, elapsed_s}
    """
    if client is None:
        client = MockFinixClient()
    if chunker is None:
        chunker = FixedHeightChunker()
    if merger is None:
        merger = EditDistanceMerger()

    output_csv = Path(output_csv)
    image_dirs_p = [Path(d) for d in image_dirs]
    images = _scan_images(image_dirs_p)

    _ensure_csv_header(output_csv)
    done = _load_done_set(output_csv)
    todo = [p for p in images if p.name not in done]

    print(f"[runner] total={len(images)} done={len(done)} todo={len(todo)}",
          file=sys.stderr)

    result_queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
    predictions_dir_p = Path(predictions_dir) if predictions_dir else None
    if eval_mode and predictions_dir_p:
        predictions_dir_p.mkdir(parents=True, exist_ok=True)

    stop_event = threading.Event()
    stats = {"processed": 0, "skipped": len(done), "failed": 0}

    def writer_thread() -> None:
        with output_csv.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            while True:
                item = result_queue.get()
                if item is None:
                    break
                file_name, md = item
                w.writerow([file_name, md])
                f.flush()
                if eval_mode and predictions_dir_p:
                    stem = Path(file_name).stem
                    (predictions_dir_p / f"{stem}.md").write_text(
                        md, encoding="utf-8"
                    )

    writer = threading.Thread(target=writer_thread, daemon=True)
    writer.start()

    def process_one(img_path: Path) -> tuple[str, str]:
        try:
            img = Image.open(img_path)
            img.load()
            result = process_image(
                image=img,
                image_id=img_path.stem,
                client=client,
                chunker=chunker,
                merger=merger,
            )
            return img_path.name, result.final_markdown
        except Exception as e:  # noqa: BLE001
            print(f"[runner] FAIL {img_path.name}: {e}", file=sys.stderr)
            return img_path.name, ""

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(process_one, p): p for p in todo}
        for fut in as_completed(future_map):
            if stop_event.is_set():
                break
            file_name, md = fut.result()
            result_queue.put((file_name, md))
            if md:
                stats["processed"] += 1
            else:
                stats["failed"] += 1
            done_count = stats["processed"] + stats["failed"] + stats["skipped"]
            elapsed = time.monotonic() - start
            print(
                f"[runner] {done_count}/{len(images)} | "
                f"elapsed={elapsed:.0f}s | "
                f"current={file_name}",
                file=sys.stderr,
            )
            if elapsed > time_budget_seconds:
                print("[runner] time budget exceeded, stopping new dispatch",
                      file=sys.stderr)
                stop_event.set()

    result_queue.put(None)
    writer.join(timeout=5)
    stats["elapsed_s"] = time.monotonic() - start
    return stats
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/restore/test_runner.py -v
```

预期：4 个用例 PASS

- [ ] **Step 5: 提交**

```bash
git add src/restore/runner.py tests/restore/test_runner.py
git commit -m "feat(restore): add batch runner with concurrency + resume + single-writer"
```

---

## Task 12: 浏览器路由 `/api/restore` 和 `/api/eval`

**Files:**
- Modify: `src/app.py`（追加 2 个路由）
- Create: `tests/test_app_restore_routes.py`

- [ ] **Step 1: 读现有 src/app.py 结构**

```bash
head -50 src/app.py
```

记录 Flask app 实例名（通常是 `app`）、manifest 路径加载方式。

- [ ] **Step 2: 写失败测试 `tests/test_app_restore_routes.py`**

```python
# tests/test_app_restore_routes.py
"""浏览器新增路由 /api/restore 和 /api/eval 的测试。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from src import app as app_module


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def test_api_restore_returns_pipeline_result(client, tmp_path, monkeypatch):
    """POST /api/restore 返回 PipelineResult JSON。"""
    # 造一张训练集图（mock _resolve_image_path 找到它）
    img_path = tmp_path / "test-uuid.jpg"
    Image.new("RGB", (500, 500), (200, 200, 200)).save(img_path, "JPEG")

    # 用真实 Chunk 构造最小 PipelineResult
    from src.restore.types import Chunk, ChunkResult, PipelineResult
    from PIL import Image as PI

    chunk = Chunk(
        image=PI.new("RGB", (500, 500)),
        bbox=(0, 0, 500, 500),
        overlap_top=0,
        overlap_bottom=0,
    )
    fake_result = PipelineResult(
        image_id="test-uuid",
        image_shape=(500, 500),
        chunker_name="fixed_height",
        chunks=[ChunkResult(chunk=chunk, raw_markdown="# Test",
                            elapsed_ms=10, cached=False)],
        merge_decisions=[],
        final_markdown="# Test",
        ground_truth=None,
        elapsed_ms=10,
    )

    # 同时 mock 图像解析和 pipeline（避免触网与读真图）
    with patch("src.app._resolve_image_path", return_value=img_path), \
         patch("src.app._process_image", return_value=fake_result):
        resp = client.post(
            "/api/restore",
            json={"image_id": "test-uuid"},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["image_id"] == "test-uuid"
    assert data["final_markdown"] == "# Test"
    assert data["chunker_name"] == "fixed_height"


def test_api_restore_400_missing_image_id(client):
    resp = client.post("/api/restore", json={})
    assert resp.status_code == 400


def test_api_eval_lists_reports(client, tmp_path, monkeypatch):
    """GET /api/eval 列出 outputs/eval/ 下的报告目录。"""
    # 把 outputs/eval 临时指向 tmp_path
    fake_eval_dir = tmp_path / "eval"
    fake_eval_dir.mkdir()
    (fake_eval_dir / "2026-06-27-1430").mkdir()
    (fake_eval_dir / "2026-06-27-1430" / "summary.txt").write_text("n=10 mean=0.5")

    with patch("src.app._eval_dir", return_value=fake_eval_dir):
        resp = client.get("/api/eval")
    assert resp.status_code == 200
    reports = resp.get_json()["reports"]
    assert "2026-06-27-1430" in [r["name"] for r in reports]
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
pytest tests/test_app_restore_routes.py -v
```

预期：404（路由不存在）或 `AttributeError: module 'src.app' has no attribute 'process_image'`

- [ ] **Step 4: 在 `src/app.py` 末尾追加路由**

```python
# ===== Restore Pipeline API Routes =====
# 这两个路由把流水线暴露给浏览器，便于交互式调参。
# Phase 1 只返回 JSON；前端可视化推迟到后续 phase。

import json as _json
from pathlib import Path as _Path
from typing import Any as _Any

from src.restore.config import Config as _RestoreConfig
from src.restore.pipeline import process_image as _process_image


def _resolve_image_path(image_id: str) -> _Path | None:
    """根据 image_id（UUID 或 filename stem）在 data/ 下找原图。"""
    data_root = _Path(__file__).resolve().parent.parent / "data"
    for pattern in (f"**/images/{image_id}.jpg", f"**/images/{image_id}.png"):
        matches = list(data_root.glob(pattern))
        if matches:
            return matches[0]
    return None


def _eval_dir() -> _Path:
    """返回 outputs/eval/ 目录。"""
    return _RestoreConfig.from_env().eval_dir


@app.route("/api/restore", methods=["POST"])
def api_restore() -> _Any:
    """跑单图流水线，返回 PipelineResult JSON。"""
    payload = request.get_json(silent=True) or {}
    image_id = payload.get("image_id")
    if not image_id:
        return jsonify({"error": "image_id required"}), 400

    img_path = _resolve_image_path(image_id)
    if img_path is None:
        return jsonify({"error": f"image not found: {image_id}"}), 404

    from PIL import Image as _PILImage

    try:
        img = _PILImage.open(img_path)
        img.load()
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"failed to open image: {e}"}), 500

    # 构造默认 client（HTTPFinixClient）；可选注入真值
    cfg = _RestoreConfig.from_env(load_dotenv=True)
    from src.restore.chunking import FixedHeightChunker as _FHC
    from src.restore.dedup import EditDistanceMerger as _EDM
    from src.restore.finix_client import HTTPFinixClient as _HTTP

    client = _HTTP(
        user_id=cfg.finix_user_id,
        api_key=cfg.finix_api_key,
        cache_dir=cfg.cache_dir,
        max_concurrency=cfg.concurrency,
    )

    # 训练集：尝试加载 ground truth
    gt_path = img_path.parent.parent / "mds" / f"{image_id}.md"
    ground_truth = None
    if gt_path.exists():
        ground_truth = gt_path.read_text(encoding="utf-8")

    result = _process_image(
        image=img,
        image_id=image_id,
        client=client,
        chunker=_FHC(
            threshold=cfg.chunk_threshold,
            chunk_height=cfg.chunk_height,
            overlap=cfg.chunk_overlap,
        ),
        merger=_EDM(),
        ground_truth=ground_truth,
    )
    return jsonify(result.to_dict())


@app.route("/api/eval", methods=["GET"])
def api_eval_list() -> _Any:
    """列出 outputs/eval/ 下所有评测报告。"""
    eval_d = _eval_dir()
    if not eval_d.exists():
        return jsonify({"reports": []})
    reports = []
    for sub in sorted(eval_d.iterdir(), reverse=True):
        if not sub.is_dir():
            continue
        summary_file = sub / "summary.txt"
        summary = (
            summary_file.read_text(encoding="utf-8").strip()
            if summary_file.exists()
            else ""
        )
        reports.append({"name": sub.name, "summary": summary})
    return jsonify({"reports": reports})
```

注意：以上代码假设 `src/app.py` 里有 `app`、`request`、`jsonify` 已 import。如果没有，在文件顶部追加：

```python
from flask import request, jsonify
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/test_app_restore_routes.py -v
```

预期：3 个用例 PASS

- [ ] **Step 6: 跑现有浏览器测试，确认无回归**

```bash
pytest tests/test_app.py tests/test_gen_thumbs.py -v
```

预期：原 16 个用例全 PASS

- [ ] **Step 7: 提交**

```bash
git add src/app.py tests/test_app_restore_routes.py
git commit -m "feat(app): expose /api/restore and /api/eval routes for browser integration"
```

---

## Task 13: CLI 入口 + Live Smoke Test

**Files:**
- Create: `src/restore/__main__.py`（CLI 入口）
- Create: `tests/restore/test_smoke.py`（默认 skip）

- [ ] **Step 1: 创建 CLI 入口 `src/restore/__main__.py`**

```python
# src/restore/__main__.py
"""命令行入口：python -m src.restore <command> [args]

Commands:
  run <images_dir> [<images_dir>...] --out <csv>
      批处理跑流水线，写 CSV。需要 FINIX_USER_ID / FINIX_API_KEY 环境变量。

  eval <pred_dir> <truth_dir>
      本地评测，输出到 outputs/eval/<timestamp>/
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .chunking import FixedHeightChunker
from .config import Config
from .dedup import EditDistanceMerger
from .evaluate import evaluate_directory, write_report
from .finix_client import HTTPFinixClient
from .runner import run_directory


def cmd_run(args: argparse.Namespace) -> int:
    cfg = Config.from_env(load_dotenv=True)
    if not cfg.finix_user_id or not cfg.finix_api_key:
        print(
            "ERROR: FINIX_USER_ID / FINIX_API_KEY not set. "
            "Get them from DingTalk group 179205019946 and put in .env",
            file=sys.stderr,
        )
        return 2

    client = HTTPFinixClient(
        user_id=cfg.finix_user_id,
        api_key=cfg.finix_api_key,
        cache_dir=cfg.cache_dir,
        max_concurrency=cfg.concurrency,
    )
    chunker = FixedHeightChunker(
        threshold=cfg.chunk_threshold,
        chunk_height=cfg.chunk_height,
        overlap=cfg.chunk_overlap,
    )
    stats = run_directory(
        image_dirs=args.images,
        output_csv=args.out,
        client=client,
        chunker=chunker,
        merger=EditDistanceMerger(),
        max_workers=cfg.concurrency,
        eval_mode=args.eval_mode,
        predictions_dir=cfg.predictions_dir if args.eval_mode else None,
    )
    print(f"[done] {stats}", file=sys.stderr)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    report = evaluate_directory(args.pred_dir, args.truth_dir)
    timestamp = time.strftime("%Y-%m-%d-%H%M%S")
    out_dir = Config.from_env().eval_dir / timestamp
    write_report(report, out_dir)
    print(f"[done] report written to {out_dir}", file=sys.stderr)
    print(f"  n={report.n_samples} mean={report.mean:.4f} "
          f"median={report.median:.4f}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.restore")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="batch run pipeline → CSV")
    p_run.add_argument("images", nargs="+", type=Path, help="image directories")
    p_run.add_argument("--out", type=Path, required=True, help="output CSV path")
    p_run.add_argument(
        "--eval-mode", action="store_true",
        help="also write predictions/<id>.md for local evaluation",
    )
    p_run.set_defaults(func=cmd_run)

    p_eval = sub.add_parser("eval", help="local evaluation")
    p_eval.add_argument("pred_dir", type=Path)
    p_eval.add_argument("truth_dir", type=Path)
    p_eval.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 创建 smoke test `tests/restore/test_smoke.py`**

```python
# tests/restore/test_smoke.py
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
```

- [ ] **Step 3: 在 `tests/conftest.py` 或新建 `pytest.ini` 注册 `live` mark**

检查项目根目录是否有 `pytest.ini` / `pyproject.toml` / `setup.cfg`：

```bash
ls pytest.ini pyproject.toml setup.cfg 2>/dev/null
```

如果没有，创建 `pytest.ini`：

```ini
[pytest]
markers =
    live: marks tests that hit the live API (deselect with -m "not live")
addopts = -m "not live"
```

- [ ] **Step 4: 验证 smoke test 默认 skip**

```bash
pytest tests/restore/test_smoke.py -v
```

预期：1 个用例 SKIPPED（无凭据）或 deselected（被 addopts 排除）

- [ ] **Step 5: 跑所有 restore 测试，确认整体绿**

```bash
pytest tests/restore/ -v --ignore=tests/restore/test_smoke.py
```

预期：所有用例 PASS

- [ ] **Step 6: 提交**

```bash
git add src/restore/__main__.py tests/restore/test_smoke.py pytest.ini
git commit -m "feat(restore): add CLI entry point + live API smoke test"
```

---

## Task 14: README 更新 + 最终验证

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在 `README.md` 末尾追加还原流水线章节**

在文件末尾追加（保留现有内容）：

```markdown

## 还原流水线（Phase 1）

`src/restore/` 实现文档还原流水线。详见
`docs/superpowers/specs/2026-06-27-restore-pipeline-phase1-design.md`。

### 配置

1. 复制 `.env.example` 为 `.env`
2. 填入从钉钉群 179205019946 获取的 `FINIX_USER_ID` 和 `FINIX_API_KEY`

### 跑批处理

```bash
# A 榜测试集
python -m src.restore run \
  "data/AFAC A榜评测数据集(2)/finix_huge_long_rest_A/images" \
  "data/AFAC A榜评测数据集(2)/finix_huge_table_rest_A/images" \
  --out outputs/submission.csv
```

### 跑训练集 + 本地评测

```bash
# 1. 跑训练集（带 eval_mode）
python -m src.restore run \
  "data/AFAC 训练数据集/finixdocbench_huge_long_100/images" \
  --out outputs/training_long.csv \
  --eval-mode

# 2. 本地评测
python -m src.restore eval \
  outputs/predictions/finixdocbench_huge_long_100 \
  "data/AFAC 训练数据集/finixdocbench_huge_long_100/mds"
```

### 浏览器 API

- `POST /api/restore` body `{"image_id": "<uuid>"}` — 跑单图流水线
- `GET /api/eval` — 列出本地评测报告
```

- [ ] **Step 2: 跑全量测试套件**

```bash
pytest tests/ -v
```

预期：
- 现有浏览器测试 16 个 PASS
- 新增 restore 测试全 PASS（除 smoke test SKIPPED）

- [ ] **Step 3: 手动验证 CLI（需要真实 API 凭据）**

如果已经有 API 凭据：

```bash
# 在 .env 里填好凭据后
python -m src.restore run \
  "data/AFAC 训练数据集/finixdocbench_huge_long_100/images" \
  --out outputs/training_long.csv \
  --eval-mode
```

观察：
- `[runner] 1/100 | elapsed=2s | current=xxx.jpg` 这样的进度行
- 中断后重跑，应跳过已完成的图
- 完成后 `outputs/training_long.csv` 有 100 行

然后评测：

```bash
python -m src.restore eval \
  outputs/predictions/finixdocbench_huge_long_100 \
  "data/AFAC 训练数据集/finixdocbench_huge_long_100/mds"
```

应输出 `n=100 mean=0.xx median=0.xx`。

- [ ] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs: add restore pipeline usage to README"
```

---

## 验收清单

完成所有 Task 后，逐项检查：

- [ ] `pytest tests/ -v` 全 PASS（除 live smoke 默认 skip）
- [ ] 现有 16 个浏览器测试保持 PASS
- [ ] `python -m src.restore run --help` 输出帮助文档
- [ ] `python -m src.restore eval --help` 输出帮助文档
- [ ] `outputs/finix_cache/` 在跑过 API 后有 `.json` 缓存文件
- [ ] `outputs/submission.csv` 跑完后包含 100 行（A 榜）
- [ ] `outputs/eval/<timestamp>/report.json` 评测后有报告
- [ ] `POST /api/restore` 在浏览器 dev tools 调用返回 PipelineResult JSON
- [ ] `GET /api/eval` 返回报告列表 JSON
- [ ] 第二次跑相同输入，API 调用次数为 0（缓存生效）

---

## Phase 2 衔接

Phase 2 升级版面感知切块时只需：
1. `pip install paddleocr` 加入 requirements.txt
2. 新增 `src/restore/layout_aware_chunker.py` 实现 `Chunker` Protocol
3. `src/restore/__main__.py` 加 `--chunker layout` 选项
4. 新增 `tests/restore/test_layout_aware_chunker.py`
5. `pipeline.py` / `runner.py` / `evaluate.py` 不改

这是接口抽象的回报。
