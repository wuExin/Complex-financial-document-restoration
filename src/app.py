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

from flask import Flask, abort, jsonify, send_from_directory

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
