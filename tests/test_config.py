
import pytest

from memory import config


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMORY_ROOT", raising=False)
    monkeypatch.setattr(config, "config_file", lambda: tmp_path / "config.toml")


def test_explicit_root_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_ROOT", str(tmp_path / "env"))
    assert config.resolve_root(tmp_path / "cli") == tmp_path / "cli"


def test_env_then_file(tmp_path, monkeypatch):
    config.save({"root": str(tmp_path / "file")})
    assert config.resolve_root() == tmp_path / "file"
    monkeypatch.setenv("MEMORY_ROOT", str(tmp_path / "env"))
    assert config.resolve_root() == tmp_path / "env"


def test_unresolved_raises():
    with pytest.raises(config.RootNotFound):
        config.resolve_root()


def test_settings_defaults_and_override():
    config.save({"root": "x", "transcribe": {"model": "small"}})
    s = config.load()
    assert s["transcribe"]["model"] == "small"
    assert s["transcribe"]["engine"] == "whisper"
    assert s["summarize"]["model"] == "anthropic:claude-sonnet-5-5"


def test_generic_defaults():
    s = config.load()
    assert s["lang"] == "en"
    assert s["transcribe"]["language"] == ""


def test_config_lives_in_project_dir():
    assert config.config_file().name == "config.toml"
    assert (config.PROJECT_DIR / "pyproject.toml").is_file()
