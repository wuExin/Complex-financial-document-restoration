# Complex-financial-document-restoration

AFAC 金融文档还原挑战赛 — 数据集图片浏览器。

## 快速开始

```bash
# 1. 安装依赖（首次）
pip install -r requirements.txt

# 2. 生成缩略图与 manifest（首次或 data/ 变化后重跑）
python src/gen_thumbs.py

# 3. 启动浏览器
python src/app.py
```

打开终端中打印的 URL（默认 http://127.0.0.1:5000）。

## 使用

- **顶部标签**：切换 4 个子集（训练长文档 / 训练表格 / 评测长文档 / 评测表格）
- **左侧列表**：点击缩略图查看大图
- **大图区**：
  - 滚轮 / `+` `−` 缩放（10%–400%）
  - 拖拽平移（缩放 > 100% 时）
  - ⟲ 旋转 90° · ⤢ 适配窗口
  - ← → 键或 ‹ › 翻页
- **搜索框**：在当前子集内按 UUID 模糊过滤

## 目录结构

```
data/                 # 原始数据（只读）
src/
  gen_thumbs.py       # 缩略图 + manifest 生成脚本
  app.py              # Flask 服务
  static/             # HTML / CSS / JS
outputs/
  thumbs/             # 预生成缩略图（gitignored）
  manifest.json       # 图片清单（gitignored）
tests/                # pytest 测试
```

## 测试

```bash
pytest tests/ -v
```

## 设计文档

- 规格：`docs/superpowers/specs/2026-06-25-image-gallery-design.md`
- 实现计划：`docs/superpowers/plans/2026-06-25-image-gallery.md`
