# MVP 文档还原系统设计

## 目标

构建 AFAC 复杂金融文档还原项目的最小端到端 baseline。MVP 需要在暂时不知道 FinixDoc-VL API 细节的情况下，从图片目录运行到合法的提交 CSV。

第一版优先保证工程链路跑通，不追求榜单效果。

## 范围

本期包含：

- 扫描输入目录中的图片文件。
- 在输出中保留每张图片的原始文件名。
- MVP 阶段将每张图片视为一个 chunk。
- 定义可替换的 `VLClient` 图片块解析接口。
- 提供不依赖网络的本地 mock client。
- 将 chunk Markdown 合并为每张图片的一篇文档。
- 写出 UTF-8 CSV，字段严格为 `file_name` 和 `ground_truth`。
- 输出运行日志，并在单张图片失败时继续处理其他图片。

本期不包含：

- 真实 FinixDoc-VL HTTP 接入。
- 高级长图切片。
- 多栏阅读顺序恢复。
- 重叠切块去重。
- Markdown 表格修复。
- 线上评分或 TEDS 评估。

## 架构

MVP 使用一个小型 Python package 加 `main.py` 入口。

```text
main.py
  -> image_loader
  -> chunker
  -> vl_client
  -> merge
  -> exporter
```

### `image_loader`

在 `--input_dir` 下查找支持的图片文件，并按文件名排序，保证输出顺序可复现。支持扩展名包括 `.jpg`、`.jpeg`、`.png`、`.bmp`、`.tif`、`.tiff`。

MVP 中只返回轻量图片记录，包括文件名和绝对路径，不解码完整图片像素。

### `chunker`

MVP 中每张图片生成一个 chunk：

```text
chunk_id = 0
x = 0
y = 0
width = null
height = null
path = 原始图片路径
```

这样既能保持后续真实切片的接口形态，又能避免 baseline 阶段引入图片内存风险。

### `vl_client`

定义图片解析边界：

```python
parse_chunk(chunk) -> str
```

MVP 实现：

- `MockVLClient` 在指定 `--gt_dir` 或可推断的同级 `mds` 目录中查找 `{图片 stem}.md`。
- 如果找不到对应 Markdown 文件，则返回包含源图片名的确定性兜底文本。

后续实现：

- `FinixDocVLClient` 在官方 endpoint、鉴权方式、请求格式和响应结构明确后，再负责调用真实 FinixDoc-VL API。

### `merge`

按 `chunk_id` 排序，将非空 Markdown 片段用空行拼接。MVP 中每张图片只有一个 chunk，所以合并逻辑保持简单。

### `exporter`

使用 Python 标准库 `csv` 写 CSV，确保 Markdown 中的换行、逗号和引号被正确转义。导出时校验：

- 表头严格为 `file_name,ground_truth`；
- 输出行数等于已处理图片数；
- 每张输入图片都有一行输出。

## CLI

主命令：

```bash
python main.py --input_dir "data/AFAC 训练数据集/finixdocbench_huge_long_100/images" --output submission.csv
```

可选参数：

- `--gt_dir`：包含 `{image_stem}.md` 的目录。
- `--client`：默认 `mock`。`finixdoc` 作为预留选项，在官方 API 细节明确前应给出清晰的未实现错误。
- `--log_level`：默认 `INFO`。

## 错误处理

单张图片处理失败时不应中断整个任务。系统记录错误日志，并仅在解析异常时为该图片写入空字符串作为 `ground_truth`。

配置错误需要快速失败，例如输入目录不存在或 client 名称不支持。

## 测试

MVP 测试覆盖：

- 图片发现和确定性排序；
- 每张图片一个 chunk；
- mock client 读取 `{stem}.md`；
- mock client 兜底文本；
- CSV 输出转义和精确字段；
- 基于临时图片/Markdown fixture 的端到端运行。

## 成功标准

MVP 完成条件：

- `python main.py --input_dir <images> --output submission.csv` 可以成功运行。
- 输出 CSV 严格包含两列：`file_name` 和 `ground_truth`。
- 对带有同级 `mds` 目录的训练集运行时，可以从本地 GT Markdown 填充结果。
- 对没有 GT 的目录运行时，也能生成合法 CSV，并使用确定性兜底文本。
- 代码结构允许后续替换 `MockVLClient` 为真实 FinixDoc-VL client，而不改变主流程。
