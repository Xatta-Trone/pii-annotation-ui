from __future__ import annotations

import hmac
import os
from pathlib import Path

from dotenv import load_dotenv


ACCESS_CODE_ENV_VAR = "PII_ANNOTATION_ACCESS_CODE"
PROJECT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def parse_access_codes(value: str | None) -> tuple[str, ...]:
    """Parse non-empty comma-separated access codes from configuration."""
    if not value:
        return ()
    return tuple(code.strip() for code in value.split(",") if code.strip())


def load_access_code() -> str | None:
    """Load the raw access-code setting using the original stable API name."""
    load_dotenv(PROJECT_ENV_FILE, override=False)
    value = os.getenv(ACCESS_CODE_ENV_VAR)
    return value if value else None


def load_access_codes() -> tuple[str, ...]:
    """Load and parse all configured access codes."""
    return parse_access_codes(load_access_code())


def access_code_matches(provided: str, expected_codes: str | tuple[str, ...]) -> bool:
    """Compare an entered code against one or more configured codes without early exit."""
    if isinstance(expected_codes, str):
        expected_codes = (expected_codes,)
    provided_bytes = provided.encode("utf-8")
    matched = False
    for expected in expected_codes:
        matched |= hmac.compare_digest(provided_bytes, expected.encode("utf-8"))
    return matched
