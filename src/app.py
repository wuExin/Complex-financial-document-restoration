"""Flask server for the AFAC image browser.

Usage:
    python src/app.py [--port PORT]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

# Project root is parent of src/
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
STATIC_DIR: Path = Path(__file__).resolve().parent / "static"

app = Flask(__name__, static_folder=None)


def _load_manifest() -> dict:
    """Read and parse outputs/manifest.json, or raise FileNotFoundError."""
    manifest_path = OUTPUTS_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@app.route("/api/manifest")
def get_manifest() -> tuple:
    try:
        return jsonify(_load_manifest())
    except FileNotFoundError:
        return (
            jsonify(
                {
                    "error": "manifest not found",
                    "hint": "run `python src/gen_thumbs.py` first",
                }
            ),
            500,
        )


@app.route("/thumb/<subset>/<path:filename>")
def get_thumb(subset: str, filename: str):
    # Block path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    subset_dir = OUTPUTS_DIR / "thumbs" / subset
    if not subset_dir.is_dir():
        abort(404)
    return send_from_directory(subset_dir, filename)


def _open_in_default_viewer(path: Path) -> None:
    """Launch the OS default image viewer on `path`.

    os.startfile (Windows) returns immediately. Popen (macOS/Linux) is
    non-blocking. Either way the HTTP response stays fast.
    """
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _find_original_path(subset: str, uuid: str) -> Path | None:
    """Look up the original image path for (subset, uuid) in the manifest."""
    try:
        manifest = _load_manifest()
    except FileNotFoundError:
        return None
    subset_data = manifest.get("subsets", {}).get(subset)
    if not subset_data:
        return None
    for img in subset_data.get("images", []):
        if img["uuid"] == uuid:
            rel = img.get("image_path")
            if not rel:
                return None
            return PROJECT_ROOT / rel
    return None


@app.route("/open/<subset>/<uuid>", methods=["POST"])
def open_image(subset: str, uuid: str):
    if "/" in subset or "\\" in subset or ".." in subset:
        abort(404)
    if "/" in uuid or "\\" in uuid or ".." in uuid:
        abort(404)
    img_path = _find_original_path(subset, uuid)
    if img_path is None or not img_path.is_file():
        abort(404)
    try:
        _open_in_default_viewer(img_path)
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@app.route("/")
def get_index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:filename>")
def get_static(filename: str):
    return send_from_directory(STATIC_DIR, filename)


def find_port(start: int = 5000, end: int = 5010) -> int:
    """Return the first available port in [start, end]."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no available port in [{start}, {end}]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=None, help="Port (default: auto-pick 5000+)")
    args = parser.parse_args()
    port = args.port or find_port()
    print(f"[info] serving on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()


# ===== Restore Pipeline API Routes =====
# 这两个路由把流水线暴露给浏览器，便于交互式调参。
# Phase 1 只返回 JSON；前端可视化推迟到后续 phase。

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
