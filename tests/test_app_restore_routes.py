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
