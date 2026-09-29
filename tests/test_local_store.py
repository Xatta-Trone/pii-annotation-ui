import pandas as pd

from src.local_store import (
    create_local_dataset,
    list_local_datasets,
    load_local_dataset,
    load_local_session,
    update_local_session,
)


def sample_frame():
    return pd.DataFrame(
        [
            {
                "crash_id": "99999999999999999999",
                "clean_narrative": "First line\nJosé Smith",
                "weak_pii_entities_json": "[]",
                "annotation_status": "NOT_ANNOTATED",
                "gold_entities_json": "",
                "annotator_notes": "",
                "extra": "preserve",
            },
            {
                "crash_id": "002",
                "clean_narrative": "No PII",
                "weak_pii_entities_json": "[]",
                "annotation_status": "COMPLETED",
                "gold_entities_json": "[]",
                "annotator_notes": "reviewed",
                "extra": "also",
            },
        ],
        dtype=str,
    )


def test_local_database_round_trip_and_incremental_update(tmp_path):
    database = tmp_path / "annotations.db"
    frame = sample_frame()
    drafts = {
        0: {"entities": [], "status": "NOT_ANNOTATED", "notes": ""},
        1: {"entities": [], "status": "COMPLETED", "notes": "reviewed"},
    }
    create_local_dataset(
        database,
        "file.csv:hash",
        "session-1",
        "file.csv",
        frame,
        drafts,
        current_row_index=0,
        custom_labels=["UNIT_ID"],
        filter_state={},
        load_warnings=[],
        revision=1,
    )

    drafts[0] = {
        "entities": [
            {"text": "José Smith", "label": "PERSON", "start_char": 11, "end_char": 21}
        ],
        "status": "COMPLETED",
        "notes": "saved",
    }
    update_local_session(
        database,
        "file.csv:hash",
        current_row_index=0,
        current_draft=drafts[0],
        custom_labels=["UNIT_ID"],
        filter_state={"statuses": ["COMPLETED"]},
        load_warnings=[],
        revision=2,
    )

    restored = load_local_session(database, "session-1")
    assert restored is not None
    assert list(restored["dataframe"].columns) == list(frame.columns)
    assert restored["dataframe"]["crash_id"].tolist() == ["99999999999999999999", "002"]
    assert restored["dataframe"]["extra"].tolist() == ["preserve", "also"]
    assert restored["dataframe"].loc[0, "clean_narrative"] == "First line\nJosé Smith"
    assert restored["drafts"][0] == drafts[0]
    assert restored["dataframe"].loc[0, "annotation_status"] == "COMPLETED"
    assert restored["dataframe"].loc[1, "gold_entities_json"] == "[]"
    assert load_local_dataset(database, "file.csv:hash")["web_session_id"] == "session-1"

    recent = list_local_datasets(database)
    assert recent[0]["filename"] == "file.csv"
    assert recent[0]["row_count"] == 2
    assert recent[0]["completed_count"] == 2
