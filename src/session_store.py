from __future__ import annotations

import copy
import hashlib
import time
from typing import Any


SESSION_TTL_SECONDS = 15 * 60


def create_session_id(file_identity: str, now: float | None = None) -> str:
    """Create a URL-safe file-hash + timestamp session identifier."""
    timestamp_ms = int((time.time() if now is None else now) * 1000)
    digest = hashlib.sha256(file_identity.encode("utf-8")).hexdigest()[:16]
    return f"{digest}-{timestamp_ms}"


def prune_expired_sessions(
    store: dict[str, dict[str, Any]],
    ttl_seconds: int = SESSION_TTL_SECONDS,
    now: float | None = None,
) -> list[str]:
    current_time = time.time() if now is None else now
    expired = [
        session_id
        for session_id, record in store.items()
        if current_time - float(record.get("last_activity", 0)) > ttl_seconds
    ]
    for session_id in expired:
        store.pop(session_id, None)
    return expired


def save_session(
    store: dict[str, dict[str, Any]],
    session_id: str,
    snapshot: dict[str, Any],
    now: float | None = None,
) -> None:
    store[session_id] = {
        "last_activity": time.time() if now is None else now,
        "snapshot": copy.deepcopy(snapshot),
    }


def restore_session(
    store: dict[str, dict[str, Any]],
    session_id: str,
    ttl_seconds: int = SESSION_TTL_SECONDS,
    now: float | None = None,
) -> dict[str, Any] | None:
    current_time = time.time() if now is None else now
    record = store.get(session_id)
    if not record or current_time - float(record.get("last_activity", 0)) > ttl_seconds:
        store.pop(session_id, None)
        return None
    record["last_activity"] = current_time
    return copy.deepcopy(record["snapshot"])

