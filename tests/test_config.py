from pathlib import Path

import pytest

from pipeline.config import Config, ConfigError


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text("llm:\n  provider: anthropic\n", encoding="utf-8")
    return tmp_path


def test_load_reads_yaml(tmp_path):
    config = Config.load(make_root(tmp_path))
    assert config.data["llm"]["provider"] == "anthropic"
    assert config.root == tmp_path


def test_env_returns_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_KEY", "abc")
    config = Config.load(make_root(tmp_path))
    assert config.env("SOME_KEY") == "abc"


def test_env_missing_names_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT_KEY", raising=False)
    config = Config.load(make_root(tmp_path))
    with pytest.raises(ConfigError, match="ABSENT_KEY"):
        config.env("ABSENT_KEY")


def test_load_missing_config_fails_fast(tmp_path):
    with pytest.raises(ConfigError, match="config.yaml"):
        Config.load(tmp_path)
