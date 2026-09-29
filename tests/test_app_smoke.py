from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.config import DATABASE_PATH_ENV_VAR, RUNTIME_ENVIRONMENT_ENV_VAR


def test_local_mode_starts_with_sqlite_after_authentication(monkeypatch, tmp_path):
    monkeypatch.setenv(RUNTIME_ENVIRONMENT_ENV_VAR, "local")
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(tmp_path / "smoke.db"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15)
    app.session_state["authenticated"] = True
    app.run()
    assert not app.exception
    assert (tmp_path / "smoke.db").exists()
