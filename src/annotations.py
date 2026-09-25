from __future__ import annotations

import json

from .validation import validate_span


class AnnotationError(ValueError):
    pass


def spans_overlap(a: dict, b: dict) -> bool:
    return a["start_char"] < b["end_char"] and b["start_char"] < a["end_char"]


def add_annotation(entities: list[dict], entity: dict, narrative: str, active_labels: list[str]) -> list[dict]:
    errors = validate_span(entity, narrative, active_labels)
    if errors:
        raise AnnotationError(" ".join(errors))
    if any(
        old["start_char"] == entity["start_char"]
        and old["end_char"] == entity["end_char"]
        and old["label"] == entity["label"]
        for old in entities
    ):
        raise AnnotationError("This exact annotation already exists.")
    if any(spans_overlap(old, entity) for old in entities):
        raise AnnotationError("The selected span overlaps an existing gold annotation.")
    return sort_annotations([*entities, dict(entity)])


def delete_annotation(entities: list[dict], index: int) -> list[dict]:
    return [entity for i, entity in enumerate(entities) if i != index]


def change_label(entities: list[dict], index: int, label: str, active_labels: list[str]) -> list[dict]:
    if label not in active_labels:
        raise AnnotationError(f"Unknown label: {label}")
    changed = [dict(entity) for entity in entities]
    changed[index]["label"] = label
    return sort_annotations(changed)


def sort_annotations(entities: list[dict]) -> list[dict]:
    return sorted(entities, key=lambda e: (e["start_char"], e["end_char"]))


def serialize_annotations(entities: list[dict]) -> str:
    return json.dumps(sort_annotations(entities), ensure_ascii=False, separators=(",", ":"))

