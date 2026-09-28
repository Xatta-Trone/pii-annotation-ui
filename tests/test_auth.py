from src import auth
from src.auth import ACCESS_CODE_ENV_VAR, access_code_matches, load_access_code, load_access_codes, parse_access_codes


def test_access_code_matches_exact_value_only():
    expected = ("correct horse",)
    assert access_code_matches("correct horse", expected)
    assert not access_code_matches("Correct horse", expected)
    assert not access_code_matches("correct horse ", expected)
    assert not access_code_matches("", expected)


def test_access_code_supports_unicode():
    assert access_code_matches("annotatör-🔒", ("annotatör-🔒",))


def test_multiple_access_codes_are_trimmed_and_each_can_authenticate():
    codes = parse_access_codes(" 7K3P-N9WX-4MQR,4V2A-BMXM-XUWV , THIRD-CODE ")
    assert codes == ("7K3P-N9WX-4MQR", "4V2A-BMXM-XUWV", "THIRD-CODE")
    assert access_code_matches("7K3P-N9WX-4MQR", codes)
    assert access_code_matches("4V2A-BMXM-XUWV", codes)
    assert access_code_matches("THIRD-CODE", codes)
    assert not access_code_matches("UNKNOWN", codes)


def test_empty_access_code_entries_are_ignored():
    assert parse_access_codes(" , FIRST,, SECOND, ") == ("FIRST", "SECOND")
    assert parse_access_codes(None) == ()


def test_access_code_configuration_is_required(monkeypatch, tmp_path):
    monkeypatch.delenv(ACCESS_CODE_ENV_VAR, raising=False)
    monkeypatch.setattr(auth, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_access_codes() == ()


def test_access_code_can_come_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(ACCESS_CODE_ENV_VAR, "private-code,backup-code")
    monkeypatch.setattr(auth, "PROJECT_ENV_FILE", tmp_path / "missing.env")
    assert load_access_code() == "private-code,backup-code"
    assert load_access_codes() == ("private-code", "backup-code")


def test_access_code_matcher_preserves_single_code_api():
    assert access_code_matches("FIRST", "FIRST")
    assert not access_code_matches("SECOND", "FIRST")
