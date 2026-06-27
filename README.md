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
- **左侧列表**：点击缩略图，用系统默认图片查看器打开原图
- **状态面板**：显示当前选中的文件名、缩略图预览、打开状态
- **上一张 / 下一张**：‹ › 按钮 或 ← → 键
- **搜索框**：在当前子集内按 UUID 模糊过滤

> 为什么用系统查看器？真实的 AFAC 长文档扫描图可达 1500×92024（1.38 亿像素），
> 超过 Chrome 的 `<img>` 解码上限（约 1 亿像素）。系统查看器（Windows 照片等）
> 可以正常显示原始分辨率。

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
- OS 查看器重构：`docs/superpowers/specs/2026-06-27-open-in-os-viewer-design.md` · `docs/superpowers/plans/2026-06-27-open-in-os-viewer.md`
