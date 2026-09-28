import pytest

from src import config
from src.config import SESSION_TTL_MINUTES_ENV_VAR, load_session_ttl_minutes


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
