from __future__ import annotations

import pandas as pd


def filtered_indices(
    dataframe: pd.DataFrame,
    statuses: list[str] | None = None,
    source_classes: list[str] | None = None,
    years: list[str] | None = None,
) -> list[int]:
    mask = pd.Series(True, index=dataframe.index)
    if statuses:
        mask &= dataframe["annotation_status"].astype(str).isin(statuses)
    if source_classes and "source_class" in dataframe:
        mask &= dataframe["source_class"].astype(str).isin(source_classes)
    if years and "year" in dataframe:
        mask &= dataframe["year"].astype(str).isin(years)
    return dataframe.index[mask].tolist()


def move(current: int, indices: list[int], step: int) -> int:
    if not indices:
        return current
    if current not in indices:
        return indices[0]
    position = indices.index(current)
    return indices[max(0, min(len(indices) - 1, position + step))]


def jump_to_row(row_number: int, row_count: int) -> int:
    if not 1 <= row_number <= row_count:
        raise ValueError(f"Row must be between 1 and {row_count}.")
    return row_number - 1


def find_crash_id(dataframe: pd.DataFrame, crash_id: str) -> int:
    matches = dataframe.index[dataframe["crash_id"].astype(str) == str(crash_id)].tolist()
    if not matches:
        raise ValueError(f"Crash ID {crash_id!r} was not found.")
    return matches[0]

