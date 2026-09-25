from __future__ import annotations

import json
from typing import Any, Iterable

from .config import REQUIRED_COLUMNS, VALID_STATUSES


def parse_json_list(value: Any, field_name: str = "JSON") -> tuple[list, str | None]:
    """Parse a JSON list without raising; blank cells are treated as empty lists."""
    if value is None or (isinstance(value, float) and value != value):
        return [], None
    if isinstance(value, list):
        return value, None
    if not str(value).strip():
        return [], None
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError) as exc:
        return [], f"Malformed {field_name}: {exc}"
    if not isinstance(parsed, list):
        return [], f"Malformed {field_name}: expected a JSON list."
    return parsed, None


def validate_span(entity: Any, narrative: str, active_labels: Iterable[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(entity, dict):
        return ["Entity must be an object."]
    start, end = entity.get("start_char"), entity.get("end_char")
    text, label = entity.get("text"), entity.get("label")
    if isinstance(start, bool) or not isinstance(start, int):
        errors.append("start_char must be an integer.")
    if isinstance(end, bool) or not isinstance(end, int):
        errors.append("end_char must be an integer.")
    if errors:
        return errors
    if not (0 <= start < end <= len(narrative)):
        errors.append(f"Invalid range [{start}, {end}) for narrative length {len(narrative)}.")
    elif narrative[start:end] != text:
        errors.append("Stored text does not match clean_narrative at its offsets.")
    if label not in set(active_labels):
        errors.append(f"Unknown label: {label!r}.")
    return errors


def validate_entities(entities: list, narrative: str, active_labels: Iterable[str]) -> list[str]:
    errors: list[str] = []
    for index, entity in enumerate(entities):
        errors.extend(f"Entity {index + 1}: {message}" for message in validate_span(entity, narrative, active_labels))
    valid_spans = [e for e in entities if isinstance(e, dict) and isinstance(e.get("start_char"), int) and isinstance(e.get("end_char"), int)]
    for left, right in zip(sorted(valid_spans, key=lambda e: (e["start_char"], e["end_char"])), sorted(valid_spans, key=lambda e: (e["start_char"], e["end_char"]))[1:]):
        if right["start_char"] < left["end_char"]:
            errors.append("Gold annotations overlap.")
            break
    return errors


def validate_dataset_columns(columns: Iterable[str]) -> list[str]:
    column_set = set(columns)
    return [name for name in REQUIRED_COLUMNS if name not in column_set]


def validate_status(status: str) -> bool:
    return status in VALID_STATUSES

