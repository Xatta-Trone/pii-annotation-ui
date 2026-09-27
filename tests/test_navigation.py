import pandas as pd
from src.navigation import filtered_indices, find_crash_id, move


def test_filter_uses_original_indices_and_navigation():
    frame = pd.DataFrame({"crash_id": ["9", "8", "7"], "annotation_status": ["COMPLETED", "NOT_ANNOTATED", "NOT_ANNOTATED"]})
    indices = filtered_indices(frame, statuses=["NOT_ANNOTATED"])
    assert indices == [1, 2]
    assert move(1, indices, 1) == 2
    assert find_crash_id(frame, "8") == 1


def test_navigation_clamps_at_first_and_last_filtered_record():
    indices = [2, 5, 9]
    assert move(2, indices, -1) == 2
    assert move(9, indices, 1) == 9

