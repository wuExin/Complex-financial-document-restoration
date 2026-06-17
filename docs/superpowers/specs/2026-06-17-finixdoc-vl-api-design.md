# 阶段二 FinixDoc-VL API 接入设计

## 目标

在现有 MVP pipeline 基础上接入赛事官方 FinixDoc-VL 文档解析 API，让输出的 `ground_truth` 从 mock 占位文本变为官方模型返回的 Markdown。

阶段二优先解决“真实解析结果可提交”，不在本阶段展开复杂版面切块、表格修复和阅读流重排。

## 背景

官方提供的 FinixDoc-VL API 用于金融文档解析，支持图片输入并返回 Markdown 解析结果。接口更关注金融场景中的文本识别、版面理解、表格结构还原、阅读顺序恢复和结构化输出。

接口地址：

```text
https://finixdocapi.alipay.com/api/finix_doc/call_with_file
```

调用方式：

```text
POST multipart/form-data
```

请求字段：

| 字段 | 说明 |
| --- | --- |
| `userId` | 白名单用户 ID。 |
| `apiKey` | 固定 API key。 |
| `fileName` | 上传图片文件名。 |
| `file` | 本地图片文件内容。 |

可用 `userId`：

- `finixA1001`
- `finixB2002`
- `finixC3003`
- `finixD4004`
- `finixE5005`

阶段二默认使用 `finixB2002`，允许通过命令行参数覆盖。

## 范围

本阶段包含：

- 新增 `--client finixdoc` 的真实 API 调用能力。
- 新增 `--user_id`、`--api_key`、`--endpoint`、`--timeout`、`--max_retries` 参数。
- 默认 endpoint 使用官方地址。
- 默认 userId 使用 `finixB2002`。
- 默认 apiKey 使用官方固定值。
- 使用 multipart 表单上传图片。
- 解析 API 返回中的 Markdown 文本。
- 单张图片调用失败时记录日志并继续处理其他图片。
- 支持本地响应缓存，避免重复调用同一图片。
- 保持 `file_name,ground_truth` CSV 输出格式不变。

本阶段不包含：

- 高级超大图切片。
- 重叠切块去重。
- 跨块表格合并。
- Markdown 表格修复。
- 多栏阅读流重排。
- MinerU 或其他第三方解析服务接入。

## 架构

沿用 MVP 的 `VLClient` 抽象，只替换解析客户端。

```text
main.py
  -> create_client("finixdoc")
  -> FinixDocVLClient
  -> run_pipeline
  -> create_chunks
  -> parse_chunk
  -> merge_chunk_markdown
  -> write_submission_csv
```

### `FinixDocVLClient`

职责：

- 接收 `ImageChunk`。
- 根据 chunk 图片路径构造 multipart 请求。
- 传入 `userId`、`apiKey`、`fileName`、`file`。
- 处理超时、网络错误、非 2xx 响应和空响应。
- 从响应中提取 Markdown 字符串。
- 将成功结果写入缓存。

建议接口：

```python
class FinixDocVLClient:
    def __init__(
        self,
        user_id: str,
        api_key: str,
        endpoint: str,
        timeout: float,
        max_retries: int,
        cache_dir: Path | None,
    ) -> None:
        ...

    def parse_chunk(self, chunk: ImageChunk) -> str:
        ...
```

### 响应解析

官方说明只明确“返回对应的 Markdown 解析结果”，未给出完整 JSON schema。因此阶段二采用兼容解析策略：

1. 如果响应 `Content-Type` 是 JSON：
   - 优先读取 `markdown`。
   - 其次读取 `data.markdown`。
   - 其次读取 `result`。
   - 其次读取 `data` 且其为字符串。
2. 如果响应不是 JSON：
   - 将响应正文按文本处理，作为 Markdown 返回。
3. 如果无法提取非空字符串：
   - 抛出明确异常，并由 pipeline 记录该图片失败。

这样可以在真实响应 schema 明确前保持可用，同时避免静默写入无效内容。

### 缓存

缓存目录默认：

```text
.cache/finixdoc_vl/
```

缓存 key 基于：

- 图片文件内容 hash；
- 文件名；
- client 类型；
- endpoint；
- userId。

缓存值为 Markdown 文本。命中缓存时不再调用 API。

MVP 当前 `outputs/` 和 `.sdd/` 已被忽略；阶段二需要把 `.cache/` 也加入 `.gitignore`。

## CLI

默认 mock 仍保留：

```powershell
python main.py --input_dir <images> --output submission.csv --client mock
```

真实 API 调用：

```powershell
python main.py ^
  --input_dir "data/AFAC A榜评测数据集(2)/finix_huge_long_rest_A/images" ^
  --output outputs/predict_A_long_finixdoc.csv ^
  --client finixdoc ^
  --user_id finixB2002
```

完整可配置形式：

```powershell
python main.py ^
  --input_dir <images> ^
  --output <csv> ^
  --client finixdoc ^
  --user_id finixB2002 ^
  --api_key F935A5503983FB19F26FA3F00A94EBF9 ^
  --endpoint https://finixdocapi.alipay.com/api/finix_doc/call_with_file ^
  --timeout 180 ^
  --max_retries 2 ^
  --cache_dir .cache/finixdoc_vl
```

## 错误处理

配置错误快速失败：

- `userId` 不在官方白名单中。
- `apiKey` 为空。
- endpoint 为空。
- timeout 小于等于 0。
- max retries 小于 0。

单图调用错误不中断全局任务：

- 请求超时。
- 网络连接失败。
- 服务端返回非 2xx。
- 响应无法解析出 Markdown。

这些错误由 `run_pipeline` 捕获并记录日志，该图片写入空字符串。后续阶段可增加失败重跑清单。

## 依赖

优先使用 `requests` 进行 multipart 上传，加入 `requirements.txt`：

```text
requests>=2.31.0
```

原因：

- multipart 文件上传简单稳定；
- 错误处理和超时控制清晰；
- 比手写 `urllib` multipart 更可靠。

## 测试

阶段二测试不直接访问真实 API，避免测试依赖网络和外部服务。

测试覆盖：

- CLI 可以创建 `FinixDocVLClient`。
- 非白名单 `userId` 快速失败。
- `FinixDocVLClient` 正确构造 multipart 请求字段。
- JSON 响应中的 `markdown` 可被提取。
- 文本响应可作为 Markdown 返回。
- 非 2xx 响应会抛出明确异常。
- 缓存命中时不发起网络请求。
- pipeline 中单张 API 调用失败不会中断其他图片。

## 成功标准

阶段二完成条件：

- `python main.py --client finixdoc ...` 可以调用官方 API。
- A 榜 long/table 两个目录都能生成 CSV。
- 合并后的 A 榜 CSV 文件名集合与官方 mock 提交文件完全一致。
- 输出字段仍严格为 `file_name` 和 `ground_truth`。
- 至少抽样 3 张图片确认 `ground_truth` 不再是 mock 占位文本。
- 单元测试通过。
- API 调用失败时有日志，整体任务不中断。

## 风险

| 风险 | 应对 |
| --- | --- |
| 官方响应 schema 与预期不一致 | 使用兼容响应解析，并在日志中记录无法解析的响应摘要。 |
| 图片过大导致超时 | 本阶段保留一图一 chunk；若超时频繁，下一阶段进入切块稳定。 |
| API 调用慢 | 使用缓存，避免重复请求。 |
| API 限流或不稳定 | 设置超时、重试和失败兜底。 |
| userId 无权限 | CLI 启动时校验白名单。 |

## 后续阶段

阶段二完成后，建议进入：

1. 超大图和长图切块。
2. 切块重叠去重。
3. 表格结构修复。
4. 基于训练集 GT 的本地评估与回归测试。
