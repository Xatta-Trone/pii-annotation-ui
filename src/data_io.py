from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pandas as pd

from .config import ANNOTATION_COLUMNS, VALID_STATUSES
from .validation import validate_dataset_columns


def file_identity(name: str, content: bytes) -> str:
    return f"{name}:{hashlib.sha256(content).hexdigest()}"


def load_dataset(content: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".tsv"}:
        raise ValueError("Upload a .csv or .tsv file.")
    separator = "\t" if suffix == ".tsv" else ","
    dataframe = pd.read_csv(
        io.BytesIO(content), sep=separator, dtype=str, keep_default_na=False,
        encoding="utf-8-sig",
    )
    missing = validate_dataset_columns(dataframe.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    for column, default in ANNOTATION_COLUMNS.items():
        if column not in dataframe:
            dataframe[column] = default
    invalid_status = ~dataframe["annotation_status"].isin(VALID_STATUSES)
    dataframe.loc[invalid_status, "annotation_status"] = "NOT_ANNOTATED"
    return dataframe.reset_index(drop=True)


def export_dataset(dataframe: pd.DataFrame, separator: str = ",") -> bytes:
    return dataframe.to_csv(index=False, sep=separator, lineterminator="\n").encode("utf-8-sig")

