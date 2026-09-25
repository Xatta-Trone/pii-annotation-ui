from src.validation import parse_json_list, validate_entities, validate_span


def test_exact_offsets_unicode_and_multiline():
    text = "First line\nJosé called."
    start = text.index("José")
    item = {"text": "José", "label": "PERSON", "start_char": start, "end_char": start + 4}
    assert validate_span(item, text, ["PERSON"]) == []
    assert text[item["start_char"]:item["end_char"]] == "José"


def test_malformed_json_is_nonfatal():
    assert parse_json_list("{bad", "weak")[0] == []
    assert "Malformed" in parse_json_list("{bad", "weak")[1]
    assert parse_json_list("{bad", "gold")[0] == []


def test_completed_empty_entity_list_is_valid():
    assert validate_entities([], "No private data.", ["PERSON"]) == []

