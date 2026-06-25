# AFAC 数据集图片浏览器 — 设计文档

**日期**：2026-06-25
**关联 PRD**：`doc/PRD.md`（"做一个 UI 页面，展示所有的图片。图片位置在 data 目录下。"）

## 目标

为 AFAC 金融文档还原挑战赛的本地数据集提供一个轻量浏览器，让用户能在 4 个子集（训练长文档、训练表格、评测长文档、评测表格，共 300 张）之间快速切换、浏览大图、缩放查看细节。

**非目标**：不展示 markdown 还原文、不做标注/编辑、不部署到生产环境。

## 范围与决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 用途 | 纯图片浏览 | PRD 明确"展示所有图片" |
| 数据范围 | 全部 300 张 | 4 个子集一次性纳入 |
| 布局 | 主从布局（左缩略图列表 + 右大图） | 适合连续浏览大图 |
| 列表组织 | 按子集分 4 个标签 | 子集天然分组，便于定位 |
| 技术栈 | Python Flask + 原生 HTML/JS | 与项目后续 ML 代码生态一致；前端零依赖 |
| 缩略图策略 | 预生成脚本 + 持久化缓存 | 浏览时零延迟；多一步命令可接受 |

## 架构

```
Complex-financial-document-restoration/
├── data/                          # 原始数据（只读）
├── src/
│   ├── app.py                     # Flask 服务（单文件）
│   ├── gen_thumbs.py              # 缩略图预生成脚本
│   └── static/
│       ├── index.html             # 页面骨架
│       ├── style.css              # 主从布局样式
│       └── app.js                 # 前端逻辑
├── outputs/
│   ├── thumbs/                    # 预生成缩略图（gitignore）
│   │   ├── train_long/<uuid>.jpg
│   │   ├── train_table/<uuid>.jpg
│   │   ├── eval_long/<uuid>.jpg
│   │   └── eval_table/<uuid>.jpg
│   └── manifest.json              # 图片清单（gitignore）
└── doc/PRD.md
```

### 模块职责

| 模块 | 职责 | 输入 → 输出 |
|---|---|---|
| `gen_thumbs.py` | 扫描 `data/`，为每张图生成 ~240px 缩略图，输出 manifest.json | `data/` → `outputs/thumbs/` + `outputs/manifest.json` |
| `app.py` | Flask 服务，提供页面与图片资源 | 4 个路由：`/`、`/api/manifest`、`/thumb/<subset>/<uuid>`、`/image/<path>` |
| `index.html` + `style.css` | 页面骨架与样式（顶栏标签 + 左侧缩略图列表 + 右侧大图区） | — |
| `app.js` | 加载 manifest、渲染标签/缩略图、处理点击/键盘/缩放 | fetch → DOM |

### 数据流

```
[启动] python src/gen_thumbs.py
         ↓ 扫描 data/
         ↓ Pillow 下采样至 240px
         ↓ 写入 outputs/thumbs/ + manifest.json（含 subset/uuid/原图路径）

[运行] python src/app.py
         ↓ Flask 监听 http://127.0.0.1:5000

[浏览] 浏览器 → GET / → 加载 index.html
         ↓ fetch /api/manifest
         ↓ 渲染 4 个标签 + 当前标签的缩略图列表
         ↓ 用户点击缩略图 → GET /image/<path> → 大图区显示
         ↓ 滚轮缩放 / 拖拽平移 / ←→ 键盘翻页
```

### 依赖

- 后端：`flask`、`pillow`（仅 2 个第三方包）
- 前端：0 依赖（原生 HTML/CSS/JS）

## UI 设计

### 布局

主从布局，分三个区域：

1. **顶栏**（高度 ~48px）：
   - 4 个标签按钮，每个含子集名称 + 数量徽章
   - 当前选中标签下方有蓝色下划线
   - 右上角：UUID 模糊搜索框（可选功能，输入时实时过滤当前标签内的缩略图）

2. **左侧缩略图列表**（宽度 ~260px）：
   - 2 列网格
   - 每张缩略图（约 120×160 px）下方显示 UUID 前 12 位
   - 当前选中的缩略图有 3px 蓝色边框高亮
   - `<img loading="lazy">` 仅渲染视口内图片
   - 子集标题 + 总数显示在列表顶部

3. **右侧大图区**（占剩余空间）：
   - **工具栏**（高度 ~36px）：文件名（等宽字体）、文件大小、分辨率、缩放百分比、`+`/`−` 按钮、旋转 90° 按钮、适配窗口按钮
   - **画布**（深色背景 `#2a2a2a`）：大图居中显示，左右两侧悬浮半透明圆形导航箭头
   - **状态栏**（高度 ~24px）：当前位置（"第 N / M 张 · 子集名"）+ 快捷键提示

### 交互

- **标签切换**：点击顶部标签，左侧列表切换为该子集的缩略图；默认选中第一个标签（训练长文档）
- **缩略图点击**：右侧大图区加载该图，工具栏更新元信息，状态栏更新位置
- **大图缩放**：
  - 默认适配窗口（fit-to-window）
  - 鼠标滚轮缩放，范围 10%–400%，以鼠标位置为缩放中心
  - 工具栏 `+`/`−` 按钮以 10% 步长缩放
- **大图平移**：缩放 > 100% 时，鼠标拖拽平移（cursor: grab/grabbing）
- **旋转**：工具栏旋转按钮，每次点击顺时针 90°
- **键盘翻页**：`←`/`→` 切换上/下一张（在当前子集内循环）
- **UUID 搜索**：右上角搜索框，模糊匹配 UUID，实时过滤当前子集的缩略图

## 错误处理

| 场景 | 处理方式 |
|---|---|
| `data/` 目录不存在或为空 | `gen_thumbs.py` 报错并提示路径 |
| `outputs/manifest.json` 不存在时启动 Flask | 服务端报错："请先运行 `python src/gen_thumbs.py`" |
| 单张图片损坏（PIL 无法解码） | `gen_thumbs.py` 记录到日志，跳过，继续处理其他图片 |
| 缩略图缺失（`data/` 新增图片未重新生成） | `/thumb/<path>` 返回 404，前端在该缩略图位置显示"重新生成"占位 |
| Flask 端口 5000 被占用 | 自动尝试 5001、5002... 直至可用，启动时打印实际端口 |
| 大图请求超时/失败 | 大图区显示错误图标 + "加载失败，点击重试" |

## 测试策略

本地工具，采用轻量测试：

1. **`gen_thumbs.py` 冒烟测试**（pytest）
   - 给定 3 张样本图片的临时目录，运行后断言生成 3 个缩略图 + manifest 包含 3 条记录
   - 断言幂等：再次运行不重复生成
2. **`app.py` 路由冒烟测试**（pytest + Flask test client）
   - `GET /` 返回 200 + HTML
   - `GET /api/manifest` 返回 JSON 含 4 个子集
   - `GET /thumb/train_long/<uuid>.jpg` 返回 200 + `image/jpeg`
   - `GET /image/...` 返回 200 + `image/jpeg`
3. **手动浏览器验收清单**
   - 4 个标签均可切换、数量正确（100/100/50/50）
   - 缩略图加载、点击可显示大图
   - 键盘 ←→、滚轮缩放、拖拽平移、旋转按钮均生效
   - 浏览器控制台无报错

## 已知限制

- 大图加载需 1–3 秒（13MB 本地文件 IO 瓶颈，无法避免）；缩略图列表 < 100ms
- 缩略图列表使用 `<img loading="lazy">`，仅渲染视口内的图片
- 路径含中文（"AFAC 训练数据集"），Flask 需正确处理 URL 编码
- 跨子集搜索未支持（搜索仅作用于当前标签）

## YAGNI（明确不做）

- 不展示 markdown 还原文（用户已选纯图片浏览）
- 不做用户认证、多用户、权限
- 不做图片标注、编辑、保存功能
- 不部署到生产（仅本地 127.0.0.1）
- 不做图片预处理（旋转校正、裁剪、OCR）
- 不支持服务端分页（300 张前端一次渲染即可）

## manifest.json 结构

```json
{
  "version": 1,
  "generated_at": "2026-06-25T20:40:00",
  "subsets": {
    "train_long": {
      "label": "训练长文档",
      "count": 100,
      "images": [
        {
          "uuid": "01ac6c2a-a9ce-4a19-bb55-096f62222450",
          "image_path": "data/AFAC 训练数据集/finixdocbench_huge_long_100/images/01ac6c2a-a9ce-4a19-bb55-096f62222450.jpg",
          "thumb_path": "train_long/01ac6c2a-a9ce-4a19-bb55-096f62222450.jpg",
          "size_bytes": 13439832
        }
      ]
    },
    "train_table": { "label": "训练表格", "count": 100, "images": [...] },
    "eval_long":   { "label": "评测长文档", "count": 50,  "images": [...] },
    "eval_table":  { "label": "评测表格", "count": 50,  "images": [...] }
  }
}
```
