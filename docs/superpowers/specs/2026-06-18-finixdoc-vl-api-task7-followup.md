# FinixDoc-VL Phase 2 Task 7 跟进文档

> 本文档记录 Phase 2（FinixDoc-VL API 接入）的 Task 7 冒烟测试在真实 API 上未通过的当前状态、已收集的线索、以及解锁步骤。Phase 2 的代码（Task 1–6）已全部落地并通过单测，缺的是与真实 API schema 对齐的最后一公里。

## 上下文回顾

- 设计文档：`docs/superpowers/specs/2026-06-17-finixdoc-vl-api-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-17-finixdoc-vl-api.md`
- 已合并提交（按时间序）：`2822eb0` → `9700e75` → `d3ab423` → `c2b16c0` → `c7fd683` → `7dac885` → `fb05d9a`
- 单元测试：45 项全部通过（`python -m unittest discover -s tests`）

Task 7（计划里的最后一项）的目标是：用真实 FinixDoc-VL API 跑 ≥3 张样本图片，确认 `ground_truth` 列不再是 mock 占位文本。这条目前**没有达成**。

## Task 7 两次尝试结果

### 第一次：冒烟跑批

样本：从 `AFAC A榜评测数据集(2)/finix_huge_long_rest_A/images/` 拷出 3 张图片到 `data/smoke/`：

- `0e28acf1-b5e0-4925-808d-028affe0517a.jpg`
- `11d2c468-8853-410c-906b-e62eba4861fd.jpg`
- `14ed0d23-8f15-49d1-8f48-a616e5a7b750.jpg`

命令（大致）：

```bash
python main.py \
  --input_dir data/smoke \
  --output outputs/smoke_finixdoc.csv \
  --client finixdoc \
  --user_id finixB2002 \
  --cache_dir .cache/finixdoc_vl
```

结果：3 张图全部在 `_parse_response` 阶段抛出 `ValueError: Response did not contain parseable markdown.`。pipeline 的异常兜底正确工作——单图失败不会中断全局任务，输出 CSV 写出 3 行空 `ground_truth`：

```csv
file_name,ground_truth
0e28acf1-b5e0-4925-808d-028affe0517a.jpg,
11d2c468-8853-410c-906b-e62eba4861fd.jpg,
14ed0d23-8f15-49d1-8f48-a616e5a7b750.jpg,
```

关键观察：**API 在 180s 超时内正常返回了响应**（没有走 `_call_api` 的重试链），问题出在响应 schema 不匹配 `_extract_markdown` 的 4 档兜底（`markdown` / `data.markdown` / `result` / `data`-as-string）。

### 第二次：直连探测

为拿到真实响应体以便扩展 `_extract_markdown`，用一份临时脚本对 1 张样本直接打 API。结果：**180s ReadTimeout**。推测是连续 9 次（3 图 × 3 attempt 量级，或近段时间累计）的快速请求把官方 API 打进了限流/降速窗口。

## 当前未解决项

1. **真实响应 schema 未知**：没有拿到 200 OK 的响应体样本，无法判断官方到底把 markdown 放在哪个字段（或是不是直接给了 plain text）。
2. **API 当前慢/限流**：探测被超时卡住，无法立刻补抓 schema。
3. **Task 7 成功标准未达成**：spec 要求「至少抽样 3 张图片确认 ground_truth 不再是 mock 占位文本」——这条目前是红。

## 下一步解锁顺序

1. **冷却**：等 ≥10 分钟（或换时段），让官方 API 的限流窗口复位。
2. **抓响应体**：用一份最小脚本（不要走 pipeline，避免重试堆叠）单图打一次 API，把 `response.status_code` / `response.headers` / `response.text` 完整打印出来。建议路径：`scripts/probe_finixdoc.py`，不在本次提交范围内。
3. **扩展 `_extract_markdown`**：依据上一步拿到的真实 schema，在 `src/document_restoration/vl_client.py` 的 `_extract_markdown` 里补上对应字段路径。如果是 JSON 包别的字段名（例如 `content` / `text` / `response.markdown`），加一条新的兜底分支即可；如果 200 OK 的响应体直接是 plain text，说明 `_parse_response` 的 JSON 判定把它误归类了——可能需要调整 `looks_like_json` 的判定条件。
4. **加单测**：把真实响应样本（脱敏后）写成 `tests/test_finixdoc_client.py` 里新的 fixture，断言能正确抽出 markdown。防止后续 schema 又变。
5. **重跑冒烟**：

   ```bash
   python main.py \
     --input_dir data/smoke \
     --output outputs/smoke_finixdoc.csv \
     --client finixdoc \
     --user_id finixB2002 \
     --cache_dir .cache/finixdoc_vl
   ```

   确认 `outputs/smoke_finixdoc.csv` 的 `ground_truth` 列非空且不是 mock 占位文本。
6. **更新本文档**：把本文件标为「已解决」或归档，同时在 design doc 的 open questions 里补一笔最终 schema。

## 复跑前的可选加固（来自最终代码 review）

这些是 review 阶段发现、本次未一并修的「重要但不阻塞」项。等 Task 7 跑通后可一起处理：

- **I1 — cache 读失败未兜底**：`_read_cache` 里 `path.read_text(...)` 若遇到损坏的 cache 文件会抛 `OSError`，向上冒到 `parse_chunk` 后会被当成「无 cache」走重试链吞掉，但日志会出现误导性的 stack。建议捕获后当 cache miss 处理并 `LOGGER.warning`。
- **I2 — cache 写非原子**：`_write_cache` 直接覆盖写。若进程在写中途崩溃会留下半截文件，下次读到后触发 I1。建议 `tempfile + os.replace` 原子替换。
- **I3 — multipart files 未显式声明 content-type**：当前 `files={"file": (filename, file_obj)}`，`requests` 会自动推断，但保险起见可显式传 `image/jpeg`：`files={"file": (filename, file_obj, "image/jpeg")}`。等拿到真实响应后顺便确认是否影响识别准确率。

## 相关文件清单

- 实现层：`src/document_restoration/vl_client.py`（206 行）、`main.py`（101 行）
- 测试：`tests/test_finixdoc_client.py`（35 tests）、`tests/test_mvp_pipeline.py`（10 tests）
- 样本：`data/smoke/`（3 张）
- 冒烟输出：`outputs/smoke_finixdoc.csv`（3 行空 ground_truth）
- Cache：`.cache/finixdoc_vl/`（gitignored；目前为空或仅失败记录）
