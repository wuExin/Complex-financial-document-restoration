# 还原流水线 Phase 1：固定高度切块 MVP

**Date:** 2026-06-27
**Status:** Approved (pending review)
**Scope:** Phase 1 of 3 — 参见"分阶段实施"小节
**Predecessors:** 无（这是还原流水线的首个 spec）

## 背景

本项目目录名虽为 Complex-financial-document-restoration（对应 AFAC2026 挑战组赛题二），但当前代码（`src/app.py` + `src/gen_thumbs.py`）仅为数据集图片浏览器。**还原流水线本身尚未实现**。

赛题约束（来自官方 baseline 与提分教程）：
- **唯一允许的 MLLM**：FinixDoc-VL（赛题方提供 HTTP API），禁止任何其他大模型
- **API 形式**：multipart 文件上传至 `https://finixdocapi.alipay.com/api/finix_doc/call_with_file`，鉴权 `userId + apiKey`，返回 `result.result`（JSON 字符串）→ `choices[0].message.content`（Markdown）
- **API key 来源**：钉钉群 179205019946 分发（baseline 中的 `finixB2002` / `F935A...` 是示例值）
- **提交格式**：CSV，两列 `file_name,ground_truth`，每张测试图一行
- **运行时限**：≤3 小时跑完整个测试集
- **代码语言**：Python + 详尽中文注释
- **允许工具**：传统 CV 工具（如 PaddleOCR/PP-Structure，不是大模型）

数据集：
- 训练集 200 张（100 长 + 100 表格），每张有同 UUID 的 markdown 真值
- A 榜测试集 100 张，仅图像无真值
- 长文档平均 1500×73650（极端长宽比 0.02）；表格文档平均 6326×5743

## 问题

Naive baseline（直接对整图调 FinixDoc-VL）在长文档上会触发 OOM 或服务端拒收；表格文档勉强能调但识别质量受下采样影响。需要"按需切块 → 块级识别 → 拼接去重"的流水线，且必须满足：
1. 全量测试集 ≤3 小时
2. 可在浏览器里调参（浏览器要能调用流水线、可视化中间结果）
3. 可本地评测（训练集真值对比，迭代不耗测试 API）
4. Phase 2 能无缝升级切块策略为版面感知（PP-Structure）

## 分阶段实施（总览）

本 spec 仅描述 **Phase 1**。整体路线：

| Phase | 范围 | 周期 |
|---|---|---|
| **Phase 1**（本 spec） | 固定高度切块 + 编辑距离去重 + Text Edit 本地评测 | 3-5 天 |
| Phase 2 | 引入 PP-Structure 版面感知切块 + 表格合并 + 本地 TEDS 评测 | 1-2 周 |
| Phase 3 | prompt 调优、参数扫描、并发策略 | 持续 |

## Goals (Phase 1)

1. **能跑通**：在训练集与 A 榜测试集上端到端产出合法 CSV
2. **超时合规**：A 榜全量在 3 小时内完成
3. **本地可评测**：训练集上跑出 Text Edit 分数（归一化字符级编辑距离）
4. **库化**：流水线可作为 Python 库被浏览器 import 调用，返回结构化中间结果
5. **断点续跑**：进程崩溃重启不丢已完成工作、不重复耗 API
6. **缓存有效**：改参数重跑时未变的块走缓存

## Non-goals (Phase 1)

- 不做 PP-Structure 版面分析（Phase 2）
- 不做表格跨块合并（Phase 2）
- 不做 TEDS / Read Order Edit 本地评测（Phase 2+）
- 不做浏览器前端可视化（Phase 1 只暴露 JSON 接口，前端 Phase 后续做）
- 不做 prompt 工程的细粒度优化（Phase 3）

## 约束与设计原则

1. **核心逻辑零 CLI 耦合**：所有模块是可 import 的纯 Python 类/函数。`if __name__ == '__main__'` 只出现在 thin entry point。
2. **接口抽象优先**：切块、合并都定义为 Protocol，Phase 2 通过新增实现类替换，不改上游。
3. **结构化中间结果**：流水线返回 `PipelineResult`（含每块的 raw_markdown、合并决策），便于浏览器可视化。
4. **凭据不进代码**：API 凭据从环境变量读。
5. **可重现**：相同输入 + 相同缓存 → 相同输出。
6. **现有浏览器测试全部保持通过**（16 个 pytest 用例）。

## 架构

### 接口抽象（关键）

```python
# src/restore/types.py

@dataclass
class Chunk:
    image: PIL.Image
    bbox: tuple[int, int, int, int]   # (x0, y0, x1, y1) 在原图中的坐标
    overlap_top: int                  # 与上一块顶部重叠的像素数
    overlap_bottom: int               # 与下一块底部重叠的像素数

@dataclass
class ChunkResult:
    chunk: Chunk
    raw_markdown: str                 # FinixDoc-VL 原始返回
    elapsed_ms: int
    cached: bool                      # 是否命中缓存

@dataclass
class MergeDecision:
    left_chunk_idx: int
    right_chunk_idx: int
    left_tail: str                    # 左块参与比对的尾部文本
    right_head: str                   # 右块参与比对的头部文本
    normalized_edit_distance: float
    kept: str                         # "left" | "right" | "merged"

@dataclass
class PipelineResult:
    image_id: str
    image_shape: tuple[int, int]
    chunker_name: str                 # "fixed_height" 等
    chunks: list[ChunkResult]         # 按位置顺序
    merge_decisions: list[MergeDecision]
    final_markdown: str
    ground_truth: str | None          # 训练集才有
    elapsed_ms: int
```

```python
# src/restore/chunking.py

class Chunker(Protocol):
    def chunk(self, image: PIL.Image, image_id: str) -> list[Chunk]: ...

class FixedHeightChunker:    # Phase 1 唯一实现
    """按固定高度切块，仅当 max(w,h) 超过阈值时触发。"""

class LayoutAwareChunker:    # Phase 2 占位，不实现
    """用 PP-Structure 检测区域，按语义边界切块。"""
```

```python
# src/restore/dedup.py

class Merger(Protocol):
    def merge(self, results: list[ChunkResult]) -> tuple[str, list[MergeDecision]]: ...

class EditDistanceMerger:    # Phase 1 唯一实现
    """基于归一化编辑距离识别重叠区，保留一份。"""
```

```python
# src/restore/finix_client.py

class FinixClient(Protocol):
    def recognize(self, image: PIL.Image, chunk_id: str) -> str: ...

class HTTPFinixClient:       # 真实实现
    """调 finixdocapi.alipay.com；含重试、限频、磁盘缓存。"""

class MockFinixClient:       # 测试用
    """返回预设 markdown，便于单元/集成测试。"""
```

### 模块清单

```
src/restore/
├── __init__.py
├── types.py              # 上述 dataclass
├── config.py             # 配置加载（env + 默认值）
├── prompts.py            # FinixDoc-VL prompt 模板
├── finix_client.py       # HTTPFinixClient + 缓存 + 重试
├── chunking.py           # Chunker Protocol + FixedHeightChunker + LayoutAwareChunker 占位
├── dedup.py              # Merger Protocol + EditDistanceMerger
├── pipeline.py           # process_image()：单图编排
├── runner.py             # run_directory()：批处理 + 并发 + 断点续跑
└── evaluate.py           # text_edit_distance + evaluate_directory
```

| 模块 | 职责 |
|---|---|
| `config.py` | 从环境变量读 `FINIX_USER_ID` / `FINIX_API_KEY`；提供默认切块阈值（8000px）、块高（6000px）、重叠（1000px）、并发（8）、超时（60s）；定义路径常量（`outputs/finix_cache/`、`outputs/submission.csv` 等） |
| `prompts.py` | Phase 1 单一 prompt："请将图片中的内容识别为 Markdown 格式输出"。后续可拆分多 prompt。 |
| `finix_client.py` | 接受 PIL.Image（编码为 JPEG bytes 上传）；指数退避重试 3 次；信号量限并发；磁盘缓存 key = `sha256(bytes) + bbox`；解析嵌套 JSON 提取 `choices[0].message.content`；429 时降并发 |
| `chunking.py` | `FixedHeightChunker`：`max(w,h) ≤ 8000px` 返回单块整图；否则按 6000px 块高、1000px 重重叠**纵向切片**（保留全宽，沿高度方向切）；长文档和表格文档**统一策略**，不做方向区分；每块填 `overlap_top` / `overlap_bottom` |
| `dedup.py` | `EditDistanceMerger`：顺序遍历相邻块对，取前块尾 200 字 + 后块头 200 字，算归一化编辑距离；<0.3 视为重叠；用最长公共子串定位切点，保留左块到切点 + 右块从切点之后；记录每个 `MergeDecision` |
| `pipeline.py` | 单图同步；调 `Chunker.chunk` → 每块并发调 `FinixClient.recognize`（共享全局信号量）→ `Merger.merge` → 装配 `PipelineResult` |
| `runner.py` | `run_directory(image_dirs, output_csv)`：扫描所有图；ThreadPoolExecutor 图级并发；单一 writer 线程串行写 CSV（worker 投队列）；已存在 CSV 的图跳过；进度打印；2.5h 警告 / 2.8h 停止派发新图 |
| `evaluate.py` | `text_edit_distance(pred, truth)` 标准动态规划；`evaluate_directory(pred_dir, truth_dir)` 扫描匹配 UUID，逐对算距离，输出 JSON + summary.txt + 可选 HTML diff |

## 数据流

### 单图（库/浏览器入口）

```
image_path
  → 加载 PIL.Image + image_id
  → Chunker.chunk(image) → list[Chunk]
  → 并发 FinixClient.recognize(chunk) → list[ChunkResult]（按位置排）
  → Merger.merge(results) → (final_markdown, merge_decisions)
  → 装配 PipelineResult 返回
```

### 批处理（runner）

```
A 榜 images/*.jpg
  → 扫描，过滤掉已在 submission.csv 的（断点续跑）
  → ThreadPoolExecutor(max_workers=8) 提交 pipeline.process_image
  → 每完成一张：(file_name, final_markdown) 投队列
  → 单一 writer 线程消费队列，追加写 CSV
  → 进度行：50/100 | 耗时 320s | 预估剩余 312s | 当前 xxxxx
  → 全部完成或触达 2.8h → 关闭 CSV
```

## 时间预算

| 假设 | 数值 |
|---|---|
| 长文档 / 表格文档 | 50 / 50 |
| 长文档平均块数 | 73650 / 6000 ≈ 13 |
| API 单次耗时（乐观/保守） | 5s / 20s |
| 全局并发 | 8 |

**乐观**：长文档单图 13×5/8 ≈ 8s × 50 ≈ 400s；表格 50×5/8 ≈ 32s；总 **~7 分钟**
**保守**：长文档单图 13×20/8 ≈ 33s × 50 ≈ 1650s；表格 50×20/8 ≈ 125s；总 **~30 分钟**

3 小时预算充裕。Phase 1 选并发=8 保稳定，不必激进到 16-32。

## 错误处理

| 场景 | 处理 |
|---|---|
| API 单次失败 | 重试 3 次，指数退避（1s/2s/4s） |
| 3 次都失败 | 该块 `raw_markdown=""`，记入 `outputs/failures.jsonl`，继续 |
| 整图所有块失败 | 仍写 CSV 行（`ground_truth=""`），不阻塞其他图 |
| 网络超时 | 单次 60s 超时，按失败重试 |
| 缓存文件损坏 | JSON 解析失败时删缓存，回退真实 API |
| 图像读取失败 | `PIL.Image.MAX_IMAGE_PIXELS = None` 关 DecompressionBomb；仍失败则跳过 |
| 进程崩溃 | CSV 已完成的行不丢；重启按 CSV 跳过；缓存仍有效 |
| 时间预算超限 | 2.5h 警告；2.8h 后停止派发新图，等当前批完成 |
| 并发限流被服务端拒（429） | 全局信号量降到一半，继续重试 |
| CSV 写入冲突 | 单 writer 线程，所有 worker 投队列，writer 串行消费 |

**关键不变量**：
- 相同输入 + 相同缓存 → 相同输出
- 中断重启不丢已完成工作，不重复耗 API

## 本地评测

### Phase 1 只做 Text Edit

赛题三项指标（Text Edit / Table TEDS / Read Order Edit）中，Phase 1 仅本地实现 Text Edit（字符级 Levenshtein，便宜）。理由：
- Text Edit 是字符级最强单一信号，绝大多数改动会先体现在它上面
- TEDS 需 Markdown 表格 AST 解析 + 树编辑距离算法（200-400 行），Phase 2 与表格合并一起做
- Read Order Edit 算法官方未公开，Phase 2+ 再做

**注意**：本地评不了 TEDS 不影响提交——提交 CSV 始终是完整 Markdown，官方三项都会算。这是有意识的妥协。

### 评测 API

```python
def text_edit_distance(pred: str, truth: str) -> float:
    """归一化字符级编辑距离，0=完全相同，1=完全不同。"""

def evaluate_directory(
    pred_dir: str,         # outputs/predictions/<subset>/ 下的 .md 目录
    truth_dir: str,        # 训练集 mds/
) -> EvalReport:
    """逐对算 text_edit，返回每张分数 + 均值/中位数/分布。"""
```

**评测输入来源**：`runner.py` 增 `--eval-mode` 标志，跑训练集时除了写 CSV，额外把每张 `final_markdown` 落到 `outputs/predictions/<subset>/<uuid>.md`。`evaluate_directory` 读这个目录对齐训练集 `mds/`。A 榜跑测试集时不开 `--eval-mode`（无真值，无意义）。

### 输出

```
outputs/eval/<timestamp>/
├── report.json          # 每张 uuid + 分数 + 聚合统计
├── summary.txt          # 一行汇总
└── diffs/<uuid>.html    # 可选 HTML diff（浏览器可查看）
```

### 标准迭代循环

```
改 chunker 参数/prompt
  → 跑 pipeline 在训练集子集（10 张）→ 看 text_edit 是否下降
  → 是 → 全量训练集 200 张
  → 是 → 跑 A 榜测试集 → 提交榜单
```

## 浏览器接入（Phase 1 仅骨架）

Phase 1 只在 `src/app.py` 暴露两个 JSON 路由，不改前端：

- **`POST /api/restore`**：body `{subset, uuid}` → 调 `pipeline.process_image(...)` → 返回 `PipelineResult` 的 JSON
- **`GET /api/eval`**：列出 `outputs/eval/` 下的报告

浏览器现有的 `/thumb`、`/open`、`/api/manifest` 等路由完全复用，无破坏性改动。

前端可视化（chunk bbox 画框、每块 raw_markdown、merge decisions 高亮、final vs ground_truth diff）推迟到 Phase 后续做（独立 spec）。

## 项目结构

```
Complex-financial-document-restoration/
├── data/                                  # 只读
├── src/
│   ├── app.py                             # 现有浏览器（保留，新增 2 个路由）
│   ├── gen_thumbs.py                      # 现有（保留）
│   ├── static/                            # 现有（保留）
│   └── restore/                           # 【新】还原流水线
│       └── ...（见上"模块清单"）
├── tests/
│   ├── conftest.py                        # 现有
│   ├── test_app.py                        # 现有
│   ├── test_gen_thumbs.py                 # 现有
│   └── restore/                           # 【新】流水线测试
│       ├── conftest.py                    # 共享 fixtures
│       ├── test_chunking.py
│       ├── test_dedup.py
│       ├── test_types.py
│       ├── test_finix_client.py
│       ├── test_pipeline.py
│       ├── test_runner.py
│       └── test_evaluate.py
├── outputs/                               # gitignored
│   ├── thumbs/, previews/, manifest.json  # 现有浏览器产物
│   ├── submission.csv                     # 【新】最终提交
│   ├── finix_cache/                       # 【新】API 响应缓存
│   ├── pipeline_runs/                     # 【新】单图 PipelineResult JSON
│   ├── predictions/                       # 【新】训练集预测 markdown（评测用）
│   └── eval/                              # 【新】评测报告
├── docs/superpowers/                      # 现有
└── .env.example                           # 【新】FINIX_USER_ID / FINIX_API_KEY 模板
```

## 测试策略（TDD）

| 层 | 文件 | 内容 | 触网 |
|---|---|---|---|
| 单元 | `test_chunking.py` | 合成各种尺寸 PIL 图，断言切块数、bbox、overlap_top/bottom | 否 |
| 单元 | `test_dedup.py` | 合成 ChunkResult（含已知重叠），断言 merge_decisions + 合并后文本无重复 | 否 |
| 单元 | `test_types.py` | dataclass 构造、to_dict | 否 |
| 客户端 | `test_finix_client.py` | mock `requests.post`：重试、缓存读写、嵌套 JSON 解析、429 降级 | 否 |
| 集成 | `test_pipeline.py` | 注入 MockFinixClient，跑 process_image，断言 PipelineResult 字段 | 否 |
| 集成 | `test_runner.py` | 临时目录造 5 张图，跑 run_directory，断言 CSV 行数 + 断点续跑 | 否 |
| 评测 | `test_evaluate.py` | 合成预测+真值对，断言 text_edit_distance 数值、目录扫描 | 否 |
| 冒烟 | `test_smoke.py` (`@pytest.mark.live`) | 真调一次 API（1280×1280 小图），断言非空 markdown | 是，默认 skip |

**Mock 策略**：`FinixClient` 为 duck-typed Protocol。测试注入 `MockFinixClient` 返回预设响应。真实 `HTTPFinixClient` 只是其中一种实现。

**TDD 节奏**：每模块先写测试（红）→ commit；实现到通过（绿）→ commit；重构（如需）→ commit。

**回归保护**：现有 16 个浏览器测试必须继续通过。

## 安全考量

- API 凭据从环境变量读，不进代码、不进 git
- `.env` 加入 `.gitignore`；`.env.example` 提供模板
- API 调用仅上传图像字节流，无其他用户数据
- 缓存目录可由用户配置；默认 `outputs/finix_cache/`（gitignored）

## Out of Scope (Phase 1)

- PP-Structure / 版面分析（Phase 2）
- 跨块表格合并（Phase 2）
- 本地 TEDS / Read Order Edit 评测（Phase 2+）
- 浏览器前端可视化（独立 spec）
- Prompt 工程细粒度优化（Phase 3）
- B 榜适配（无差异，但不在本 spec 范围）

## 验收标准

Phase 1 完成时需满足：

1. ✅ `tests/restore/` 全部测试通过（单元 + 集成）
2. ✅ 现有 16 个浏览器测试仍全部通过
3. ✅ `python -m src.restore.runner` 在训练集 200 张上跑完，产出 CSV（断点续跑测试通过）
4. ✅ `evaluate.py` 在训练集上输出 text_edit 平均分（首个 baseline 数字）
5. ✅ A 榜测试集 100 张跑完 ≤3 小时
6. ✅ 产出可提交的 `submission.csv`
7. ✅ 浏览器 `POST /api/restore` 路由可调，返回结构化 PipelineResult JSON
8. ✅ 缓存命中验证：第二次跑同样输入不产生新 API 调用

## Phase 2 衔接说明

Phase 2 升级版面感知切块时的工作量：
- 新增 `LayoutAwareChunker` 类（实现已有 `Chunker` Protocol）
- `config.py` 增 `chunker_strategy` 配置项
- 新增 `tests/restore/test_layout_chunking.py`
- 新增 PaddleOCR 依赖（requirements.txt）
- `pipeline.py` 不改（按 config 选 chunker）
- `runner.py` 不改
- `evaluate.py` 不改（TEDS 是新增函数，不改 Text Edit）

预期 Phase 2 改动文件数：3-5 个（不动 Phase 1 已稳定的模块）。这是接口抽象的回报。
