from __future__ import annotations

import json
import re
import unicodedata

from .config import DEFAULT_LABELS
from .validation import parse_json_list


def normalize_label(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").upper()
    return value


def add_custom_label(custom_labels: list[str], value: str) -> list[str]:
    normalized = normalize_label(value)
    if not normalized:
        raise ValueError("Enter a label containing letters or numbers.")
    existing = {label.upper() for label in [*DEFAULT_LABELS, *custom_labels]}
    if normalized.upper() in existing:
        raise ValueError(f"Label {normalized} already exists.")
    return [*custom_labels, normalized]


def recover_custom_labels(gold_values, narratives=None) -> list[str]:
    recovered: set[str] = set()
    defaults = set(DEFAULT_LABELS)
    narratives = list(narratives) if narratives is not None else None
    for row_number, value in enumerate(gold_values):
        entities, error = parse_json_list(value, "gold_entities_json")
        if error:
            continue
        for entity in entities:
            if isinstance(entity, dict):
                label = entity.get("label")
                span_is_valid = True
                if narratives is not None:
                    narrative = str(narratives[row_number])
                    start, end, text = entity.get("start_char"), entity.get("end_char"), entity.get("text")
                    span_is_valid = (
                        isinstance(start, int) and not isinstance(start, bool)
                        and isinstance(end, int) and not isinstance(end, bool)
                        and 0 <= start < end <= len(narrative)
                        and narrative[start:end] == text
                    )
                if span_is_valid and isinstance(label, str) and normalize_label(label) == label and label not in defaults:
                    recovered.add(label)
    return sorted(recovered)


def label_schema_json(custom_labels: list[str]) -> str:
    return json.dumps({"default_labels": DEFAULT_LABELS, "custom_labels": custom_labels}, indent=2)
