from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


SESSION_TTL_MINUTES_ENV_VAR = "PII_ANNOTATION_SESSION_TTL_MINUTES"
RUNTIME_ENVIRONMENT_ENV_VAR = "PII_ANNOTATION_ENVIRONMENT"
DATABASE_PATH_ENV_VAR = "PII_ANNOTATION_DB_PATH"
DEFAULT_SESSION_TTL_MINUTES = 15
PROJECT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_session_ttl_minutes() -> int:
    """Read a positive whole-number session timeout from the environment."""
    load_dotenv(PROJECT_ENV_FILE, override=False)
    raw_value = os.getenv(SESSION_TTL_MINUTES_ENV_VAR)
    if raw_value is None or not raw_value.strip():
        return DEFAULT_SESSION_TTL_MINUTES
    try:
        minutes = int(raw_value.strip())
    except ValueError as exc:
        raise ValueError(f"{SESSION_TTL_MINUTES_ENV_VAR} must be a positive whole number.") from exc
    if minutes <= 0:
        raise ValueError(f"{SESSION_TTL_MINUTES_ENV_VAR} must be greater than zero.")
    return minutes


def load_runtime_environment() -> str:
    """Return the configured persistence mode: local or prod."""
    load_dotenv(PROJECT_ENV_FILE, override=False)
    value = os.getenv(RUNTIME_ENVIRONMENT_ENV_VAR, "prod").strip().lower()
    if value not in {"local", "prod"}:
        raise ValueError(f"{RUNTIME_ENVIRONMENT_ENV_VAR} must be 'local' or 'prod'.")
    return value


def load_database_path(runtime_environment: str | None = None) -> Path:
    """Return the optional local override or the project-root deployment database."""
    load_dotenv(PROJECT_ENV_FILE, override=False)
    environment = runtime_environment or load_runtime_environment()
    configured = os.getenv(DATABASE_PATH_ENV_VAR, "").strip()
    if environment == "local" and configured:
        return Path(os.path.expandvars(configured)).expanduser().resolve()
    return (PROJECT_ENV_FILE.parent / "annotations.db").resolve()


DEFAULT_LABELS = [
    "PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "SSN", "PASSPORT_NUMBER",
    "DRIVER_LICENSE_NUMBER", "VEHICLE_IDENTIFIER", "INSURANCE_NUMBER", "DATE",
    "ADDRESS", "LOCATION", "EMS_IDENTIFIER", "REPORT_IDENTIFIER",
    "MEDICAL_FACILITY", "OTHER_FACILITY", "NUMERIC_VALUE", "OTHER", "UNCERTAIN",
]

VALID_STATUSES = ["NOT_ANNOTATED", "COMPLETED", "NEEDS_REVIEW"]
REQUIRED_COLUMNS = ["crash_id", "clean_narrative", "weak_pii_entities_json"]
ANNOTATION_COLUMNS = {
    "annotation_status": "NOT_ANNOTATED",
    "gold_entities_json": "",
    "annotator_notes": "",
}

