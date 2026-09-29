import pytest

from src import config
from src.config import (
    DATABASE_PATH_ENV_VAR,
    RUNTIME_ENVIRONMENT_ENV_VAR,
    SESSION_TTL_MINUTES_ENV_VAR,
    load_database_path,
    load_runtime_environment,
    load_session_ttl_minutes,
)


def test_session_ttl_defaults_to_fifteen_minutes(monkeypatch, tmp_path):
    monkeypatch.delenv(SESSION_TTL_MINUTES_ENV_VAR, raising=False)
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_session_ttl_minutes() == 15


def test_session_ttl_loads_positive_whole_minutes(monkeypatch, tmp_path):
    monkeypatch.setenv(SESSION_TTL_MINUTES_ENV_VAR, " 45 ")
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_session_ttl_minutes() == 45


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "invalid"])
def test_session_ttl_rejects_invalid_values(monkeypatch, tmp_path, value):
    monkeypatch.setenv(SESSION_TTL_MINUTES_ENV_VAR, value)
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    with pytest.raises(ValueError):
        load_session_ttl_minutes()


def test_runtime_environment_defaults_to_prod_and_accepts_local(monkeypatch, tmp_path):
    monkeypatch.delenv(RUNTIME_ENVIRONMENT_ENV_VAR, raising=False)
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_runtime_environment() == "prod"
    monkeypatch.setenv(RUNTIME_ENVIRONMENT_ENV_VAR, "LOCAL")
    assert load_runtime_environment() == "local"


def test_runtime_environment_rejects_unknown_value(monkeypatch, tmp_path):
    monkeypatch.setenv(RUNTIME_ENVIRONMENT_ENV_VAR, "staging")
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    with pytest.raises(ValueError):
        load_runtime_environment()


def test_database_path_can_be_configured(monkeypatch, tmp_path):
    expected = tmp_path / "annotations.db"
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(expected))
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_database_path("local") == expected.resolve()


def test_prod_ignores_local_override_and_uses_project_root(monkeypatch, tmp_path):
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(tmp_path / "local.db"))
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "project" / ".env")
    assert load_database_path("prod") == (tmp_path / "project" / "annotations.db").resolve()


def test_local_without_override_uses_project_root(monkeypatch, tmp_path):
    monkeypatch.delenv(DATABASE_PATH_ENV_VAR, raising=False)
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / "project" / ".env")
    assert load_database_path("local") == (tmp_path / "project" / "annotations.db").resolve()
