# tests/restore/test_config.py
"""config 模块的单元测试。"""
from __future__ import annotations


def test_defaults(monkeypatch):
    for key in [
        "FINIX_USER_ID",
        "FINIX_API_KEY",
        "RESTORE_CHUNK_THRESHOLD",
        "RESTORE_CHUNK_HEIGHT",
        "RESTORE_CHUNK_OVERLAP",
        "RESTORE_CONCURRENCY",
    ]:
        monkeypatch.delenv(key, raising=False)

    from src.restore.config import Config

    cfg = Config.from_env()
    assert cfg.finix_user_id == ""
    assert cfg.finix_api_key == ""
    assert cfg.chunk_threshold == 8000
    assert cfg.chunk_height == 6000
    assert cfg.chunk_overlap == 1000
    assert cfg.concurrency == 8


def test_env_override(monkeypatch):
    monkeypatch.setenv("FINIX_USER_ID", "user123")
    monkeypatch.setenv("FINIX_API_KEY", "keyABC")
    monkeypatch.setenv("RESTORE_CHUNK_THRESHOLD", "4000")
    monkeypatch.setenv("RESTORE_CHUNK_HEIGHT", "3000")
    monkeypatch.setenv("RESTORE_CHUNK_OVERLAP", "500")
    monkeypatch.setenv("RESTORE_CONCURRENCY", "16")

    from src.restore.config import Config

    cfg = Config.from_env()
    assert cfg.finix_user_id == "user123"
    assert cfg.finix_api_key == "keyABC"
    assert cfg.chunk_threshold == 4000
    assert cfg.chunk_height == 3000
    assert cfg.chunk_overlap == 500
    assert cfg.concurrency == 16


def test_paths_are_under_outputs(monkeypatch, tmp_path):
    from src.restore.config import Config

    cfg = Config.from_env()
    assert cfg.cache_dir.name == "finix_cache"
    assert cfg.cache_dir.parent.name == "outputs"
    assert cfg.submission_csv.name == "submission.csv"
    assert cfg.predictions_dir.name == "predictions"
    assert cfg.eval_dir.name == "eval"


def test_load_dotenv_does_not_crash_without_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from src.restore.config import Config

    cfg = Config.from_env(load_dotenv=True)
    assert cfg is not None
