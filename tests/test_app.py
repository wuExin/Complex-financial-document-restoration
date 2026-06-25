"""Tests for src/app.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def app_client(sample_outputs_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a Flask test client wired to a temp outputs dir (with manifest).

    PROJECT_ROOT is set to the parent of `outputs/` so manifest `image_path`
    values (which are relative to project root) resolve correctly.
    """
    import app as app_module

    monkeypatch.setattr(app_module, "OUTPUTS_DIR", sample_outputs_dir)
    monkeypatch.setattr(app_module, "PROJECT_ROOT", sample_outputs_dir.parent)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_get_manifest_returns_json(app_client) -> None:
    resp = app_client.get("/api/manifest")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    data = resp.get_json()
    assert data["version"] == 1
    assert set(data["subsets"].keys()) == {
        "train_long",
        "train_table",
        "eval_long",
        "eval_table",
    }


def test_get_manifest_500_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app as app_module

    empty_outputs = tmp_path / "empty_outputs"
    empty_outputs.mkdir()
    monkeypatch.setattr(app_module, "OUTPUTS_DIR", empty_outputs)
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()

    resp = client.get("/api/manifest")
    assert resp.status_code == 500
    assert b"gen_thumbs" in resp.data


def test_get_thumb_returns_jpeg(app_client) -> None:
    resp = app_client.get("/thumb/train_long/aaaaaaaa-0000-0000-0000-000000000001.jpg")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_get_thumb_404_when_missing(app_client) -> None:
    resp = app_client.get("/thumb/train_long/does-not-exist.jpg")
    assert resp.status_code == 404


def test_get_thumb_404_on_unknown_subset(app_client) -> None:
    resp = app_client.get("/thumb/unknown_subset/anything.jpg")
    assert resp.status_code == 404


def test_get_image_returns_jpeg(app_client) -> None:
    resp = app_client.get("/image/train_long/aaaaaaaa-0000-0000-0000-000000000001")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_get_image_404_on_unknown_uuid(app_client) -> None:
    resp = app_client.get("/image/train_long/not-a-real-uuid")
    assert resp.status_code == 404


def test_get_index_returns_html(app_client) -> None:
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert b'<div id="app">' in resp.data


def test_get_static_asset(app_client) -> None:
    resp = app_client.get("/static/app.js")
    assert resp.status_code == 200
