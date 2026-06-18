# 长条图切片设计（Phase 3）

## 目标

让 pipeline 能处理 `finix_huge_long_rest_A` 数据集中的竖向拼接多页扫描图（aspect ratio 1:25 ~ 1:64）。这些图当前会让 FinixDoc-VL API 单次调用承受 60M-144M 像素的输入，导致响应缓慢、限流、schema 兜底失败（详见 `2026-06-18-finixdoc-vl-api-task7-followup.md`）。

把长条切成页级 chunk，每个 chunk 单独打 API，再按 `chunk_id` 拼回单篇 markdown。同时顺手解决 FinixDoc client 当前对 chunk 接口的两处 bug（用了 `chunk.source.path` 而非 `chunk.path`；cache key 用原图 bytes 导致 chunk 间相互覆盖）。

## 范围

本期包含：

- chunker 长条切分：白边检测为主，固定高度为兜底
- `.cache/chunks/` 持久化切片文件，跨运行复用
- `ImageChunk` 数据模型加 `file_name` 字段
- `FinixDocVLClient` 3 处改动：上传用 chunk.path、cache key 区分 chunk、加可选请求间隔
- `MockVLClient` GT 查找优先 chunk-specific，回退 source stem
- CLI 4 个新参数

本期不包含：

- 表格图像（`finix_huge_table_rest_A`）的内部切分——这些图 aspect ≤ 1.5，走单 chunk 路径
- 切片后内容截断的 OCR 反馈校正（设计讨论时列为选项 D，已剔除）
- 多栏阅读顺序恢复
- chunk 级别 retry 策略变化（仍是现有的 `max_retries` 机制）

## 数据观察

`AFAC A榜评测数据集(2)/` 下的样本量得：

| 子集 | 样本尺寸 | aspect (h/w) |
|---|---|---|
| `finix_huge_long_rest_A` | 1500×40216 ~ 1500×95840 | 25 ~ 64 |
| `finix_huge_table_rest_A` | 3307×4676 ~ 8187×5785 | 0.71 ~ 1.42 |

对样本 `0e28acf1...jpg`（1508×42966）做行均值亮度探测（降采样到 200px 宽）：找到 199 条连续白行段（≥5 降采样 px），但其中绝大多数是段落空隙、表格留白，而非真正页缝。结论：**白边检测可行但需要按预期页高过滤短 band**。

## 架构

```text
main.py
  -> image_loader
  -> chunker
       ├── aspect ≤ STRIP_ASPECT_THRESHOLD → 单 chunk（MVP 路径）
       └── aspect > STRIP_ASPECT_THRESHOLD
            ├── chunk_storage.try_load_cached → 命中则直接返回 chunk 元数据
            └── 未命中：
                 1. PIL 降采样 + 行亮度分析找候选页缝
                 2. 候选通过 sanity check → 按页缝切
                    候选不足 / 间距异常 → 固定高度切（10% overlap）
                 3. chunk_storage.write 切片到 .cache/chunks/
  -> vl_client
       └── FinixDocVLClient._call_api 用 chunk.path / chunk.file_name
  -> merge
  -> exporter
```

## 模块边界

### `chunker.py`（扩展）

公开接口 `create_chunks(image: ImageRecord) -> list[ImageChunk]` 不变。

```text
create_chunks(image):
    读取 image 宽高（PIL 头部，不解码像素）
    aspect = height / width
    if aspect <= STRIP_ASPECT_THRESHOLD:
        return [单 chunk，path = image.path，file_name = image.file_name]
    return _split_strip(image)

_split_strip(image):
    cut_points = _detect_cut_points(image)   # 纯计算，无 I/O
    chunks = _materialize_chunks(image, cut_points, cache_dir)
    return chunks

_materialize_chunks(image, cut_points, cache_dir):
    对每个 cut_point (y0, y1)：
        构造 ImageChunk 元数据（chunk_id、x/y/w/h、file_name）
        path = cache_dir / f"{stem}_p{nn:02d}.jpg"
        if chunk_storage.file_exists(path):
            复用，不重新切
        else:
            PIL.crop + JPEG q=90 写盘
    返回 list[ImageChunk]

_detect_cut_points(image):
    # 白边优先
    expected_page_h = round(image.width * PAGE_HEIGHT_RATIO)  # √2
    bands = _find_white_bands(image, min_band_px=round(expected_page_h * 0.3))
    if _bands_look_like_page_separators(bands, expected_page_h):
        return [band 中线 for band in bands]
    # 固定高度兜底
    return _fixed_height_cuts(image.height, expected_page_h, overlap=0.1)
```

阈值定义（常量，可被 CLI 覆盖）：

- `STRIP_ASPECT_THRESHOLD = 3.0`
- `PAGE_HEIGHT_RATIO = 1.414`  # √2，A4 比例；`expected_page_h = round(image.width * PAGE_HEIGHT_RATIO)`
- 白行阈值：`mean_brightness ≥ 248`（0-255 灰度）
- 白边 band 最低长度：`round(expected_page_h × 0.3)`
- 降采样宽度：`200 px`（仅用于行亮度分析，切片在原图上做）
- `_bands_look_like_page_separators`: 候选 band 数 ≥ 2，且相邻间距 ∈ `[0.5×, 2×] expected_page_h`。"候选 band" 指已通过最低长度过滤的 band；顶部/底部边缘 band（y < expected_page_h × 0.5 或 y > height - expected_page_h × 0.5）不参与间距判定但可用作首/尾切点
- 固定高度切分：步长 = `round(expected_page_h × 0.9)`（即 overlap = 10% × expected_page_h），最后不足一步长的剩余部分单独成 chunk
- 单图最多 chunk 数：100（超出截断 + warning）

### `chunk_storage.py`（新）

职责：管理 `.cache/chunks/` 下的切片文件生命周期。**只负责文件 I/O，不负责切点计算或 ImageChunk 元数据构造**——后者由 chunker 主导。

```python
def file_exists(path: Path) -> bool:
    """路径存在且大小 > 0。"""

def write_jpeg(path: Path, pil_image: PIL.Image.Image, quality: int = 90) -> None:
    """把 PIL Image 以 JPEG 写到 path。
    父目录不存在时自动创建。已存在的文件不覆盖（chunker 调用前先 file_exists 判断）。"""

def clear(source_stem: str, cache_dir: Path) -> None:
    """删除某 source 对应的所有切片文件。chunker 内部不调用，留给未来 CLI 子命令。"""
```

切片文件名：`<source_stem>_p<NN>.jpg`，NN 从 `01` 起两位补零（支持到 99 页；超过 100 会在 chunker 层截断）。

切片文件名：`<source_stem>_p<NN>.jpg`，NN 从 `01` 起两位补零（支持到 99 页；超过 100 会在 chunker 层截断）。

### `models.py`

`ImageChunk` 加字段：

```python
@dataclass(frozen=True)
class ImageChunk:
    source: ImageRecord
    chunk_id: int
    path: Path
    file_name: str              # ← 新增
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
```

MVP 单 chunk 路径里 `file_name = source.file_name`、`path = source.path`、`x = y = 0`、`width = height = None`，向后兼容。

### `vl_client.py`

**FinixDocVLClient 改动：**

1. `_call_api`：上传 `files={"file": (chunk.file_name, file_obj)}`、读 `chunk.path.open("rb")`（替换 `chunk.source.path` 和 `chunk.source.file_name`）
2. `_cache_key`：哈希内容改为 `chunk.path.read_bytes()` + `chunk.file_name.encode()` + 固定盐 + endpoint + user_id（替换原图 bytes）
3. `__init__` 加 `min_request_interval: float = 0.0` 参数；`_call_api` 每次发请求前 `time.sleep(self.min_request_interval)`（0 时跳过 sleep）

**MockVLClient 改动：**

GT 查找按优先级：

1. `chunk.file_name` 去 `.jpg` 后缀 + `.md`（chunk-specific GT，用于切片测试）
2. `chunk.source.path.stem + ".md"`（整篇 GT，MVP 测试用）
3. 都找不到 → 返回 mock 占位文本

`_find_ground_truth` 同时检查 `self.gt_dir` 和原 sibling `mds/` 目录，保持现有逻辑。

### `main.py`

新增 CLI 参数：

```
--strip_aspect_threshold  FLOAT  默认 3.0
--page_height_ratio       FLOAT  默认 1.414
--chunk_cache_dir         PATH   默认 .cache/chunks
--min_request_interval    FLOAT  默认 0.0   # FinixDoc client 请求间隔（秒）
```

`create_client(args)` 把 `min_request_interval` 传给 `FinixDocVLClient`。`run_pipeline`/CLI 入口把 `strip_aspect_threshold`、`page_height_ratio`、`chunk_cache_dir` 通过环境或参数传给 `create_chunks`——具体走法：

- `create_chunks` 当前签名 `(image: ImageRecord) -> list[ImageChunk]`
- 改为 `(image: ImageRecord, config: ChunkerConfig | None = None) -> list[ImageChunk]`
- `ChunkerConfig` 是 dataclass，包含上述三个参数
- pipeline.run_pipeline 接收 ChunkerConfig 并透传

## 边界情况

| 场景 | 行为 |
|---|---|
| 长条 PIL 头部读不出宽高 | 抛 `ChunkerError`，pipeline try/except 兜底，写空 markdown + ERROR 日志 |
| 长条 PIL 解码触发 DecompressionBomb（>89M 像素） | 同上 |
| 切片后某 chunk 写盘失败 | 抛异常，整图失败 |
| aspect ≤ 阈值 | 单 chunk 路径 |
| aspect > 阈值但白边/固定都只切出 1 段 | 退化为单 chunk，正常处理 |
| chunk 数 > 100 | 截断到前 100，记 warning |
| `.cache/chunks/` 不可写 | 抛 `ChunkerError`，不静默吞掉 |
| 已有切片缓存（同 stem，文件齐全且非空） | 直接复用，不重新切 |

## 测试策略

`tests/test_chunker.py`（新）：

- 单 chunk 路径：普通 aspect 图返回 1 个 chunk，path == source.path
- 白边切分：构造一张明确有 ≥2 条 ≥30% 页高的白带图，断言切点位置
- 白边检测失败兜底：构造无显著白带的图，断言走固定高度切分
- 固定高度切分：断言 chunk 数 = ceil(height / (page_h × 0.9))，overlap 正确
- chunk_id 从 0 起递增
- file_name 格式正确：`<stem>_p01.jpg` 等
- max_chunks 截断

`tests/test_chunk_storage.py`（新）：

- `try_load_cached`：全部命中 → 返回 chunks；缺一个 → None；空文件 → None
- `write`：JPEG 质量可读；不覆盖已存在文件；目录不存在时自动创建

`tests/test_finixdoc_client.py`（扩展）：

- `_call_api` 用 `chunk.path` 而非 `chunk.source.path`（mock requests.post 验证 files 参数）
- `_cache_key` 不同 chunk 生成不同 key
- `min_request_interval > 0` 时 sleep 被调用（mock time.sleep）

`tests/test_mvp_pipeline.py`（扩展）：

- `test_create_chunks_with_config`：传 ChunkerConfig 长条阈值，验证生效
- pipeline 集成：长条输入 + mock client 返回 per-chunk GT，合并后 markdown 正确

## 性能预算

- 切片单图目标：< 5s（含 PIL 降采样 + 行分析 + 写盘）
- 切片缓存命中：< 50ms（仅文件存在性检查）
- 一张 1500×95840 图预期切出 ~25-30 个 chunk，每 chunk ~1500×2100 ~ 600KB JPEG

## 未包含 / 后续

- 切片后内容截断检测（OCR 反馈）
- `chunk_storage.clear` 的 CLI 子命令
- 调参 CLI：白行阈值、band 最小比例、降采样宽度（首版固定常量，按需再加）
- 多栏阅读顺序、表格内部结构识别
