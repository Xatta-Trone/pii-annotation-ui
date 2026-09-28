from __future__ import annotations

import hmac
import os
from pathlib import Path

from dotenv import load_dotenv


ACCESS_CODE_ENV_VAR = "PII_ANNOTATION_ACCESS_CODE"
PROJECT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_access_code() -> str | None:
    """Load the access code from the project .env or hosting environment."""
    load_dotenv(PROJECT_ENV_FILE, override=False)
    value = os.getenv(ACCESS_CODE_ENV_VAR)
    return value if value else None


def access_code_matches(provided: str, expected: str) -> bool:
    """Compare access codes without an early-exit string comparison."""
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))
