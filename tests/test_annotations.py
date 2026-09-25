import pytest

from src.annotations import AnnotationError, add_annotation


def entity(text, label, start, end):
    return {"text": text, "label": label, "start_char": start, "end_char": end}


def test_duplicate_text_at_different_offsets():
    text = "John Smith spoke. Later John Smith left."
    labels = ["PERSON"]
    items = add_annotation([], entity("John Smith", "PERSON", 0, 10), text, labels)
    items = add_annotation(items, entity("John Smith", "PERSON", 24, 34), text, labels)
    assert len(items) == 2


def test_adjacent_allowed_overlap_and_duplicate_rejected():
    text = "John Smith801"
    labels = ["PERSON", "NUMERIC_VALUE"]
    items = add_annotation([], entity("John Smith", "PERSON", 0, 10), text, labels)
    assert len(add_annotation(items, entity("801", "NUMERIC_VALUE", 10, 13), text, labels)) == 2
    with pytest.raises(AnnotationError, match="overlaps"):
        add_annotation(items, entity("Smith8", "PERSON", 5, 11), text, labels)
    with pytest.raises(AnnotationError, match="already exists"):
        add_annotation(items, entity("John Smith", "PERSON", 0, 10), text, labels)

