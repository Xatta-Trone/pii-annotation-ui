from src.label_manager import add_custom_label, normalize_label, recover_custom_labels


def test_normalize_and_duplicate():
    assert normalize_label(" Police Officer ID ") == "POLICE_OFFICER_ID"
    assert add_custom_label([], "Police Officer ID") == ["POLICE_OFFICER_ID"]


def test_recover_custom_labels():
    value = '[{"text":"unit","label":"POLICE_UNIT","start_char":0,"end_char":4}]'
    assert recover_custom_labels([value], ["unit arrived"]) == ["POLICE_UNIT"]
    assert recover_custom_labels([value], ["wrong narrative"]) == []
