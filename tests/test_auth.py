from src import auth
from src.auth import ACCESS_CODE_ENV_VAR, access_code_matches, load_access_code


def test_access_code_matches_exact_value_only():
    assert access_code_matches("correct horse", "correct horse")
    assert not access_code_matches("Correct horse", "correct horse")
    assert not access_code_matches("correct horse ", "correct horse")
    assert not access_code_matches("", "correct horse")


def test_access_code_supports_unicode():
    assert access_code_matches("annotatör-🔒", "annotatör-🔒")


def test_access_code_configuration_is_required(monkeypatch, tmp_path):
    monkeypatch.delenv(ACCESS_CODE_ENV_VAR, raising=False)
    monkeypatch.setattr(auth, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_access_code() is None


def test_access_code_can_come_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(ACCESS_CODE_ENV_VAR, "private-code")
    monkeypatch.setattr(auth, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_access_code() == "private-code"
