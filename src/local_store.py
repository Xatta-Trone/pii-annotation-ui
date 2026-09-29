from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .annotations import serialize_annotations


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(database_path: Path) -> None:
    with _connect(database_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                columns_json TEXT NOT NULL,
                current_row_index INTEGER NOT NULL DEFAULT 0,
                custom_labels_json TEXT NOT NULL DEFAULT '[]',
                filter_state_json TEXT NOT NULL DEFAULT '{}',
                load_warnings_json TEXT NOT NULL DEFAULT '[]',
                revision INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                dataset_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                draft_entities_json TEXT NOT NULL DEFAULT '[]',
                draft_status TEXT NOT NULL,
                draft_notes TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (dataset_id, row_index),
                FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_datasets_updated_at
                ON datasets(updated_at DESC);
            """
        )


def create_local_dataset(
    database_path: Path,
    dataset_id: str,
    session_id: str,
    filename: str,
    dataframe: pd.DataFrame,
    drafts: dict[int, dict[str, Any]],
    *,
    current_row_index: int,
    custom_labels: list[str],
    filter_state: dict[str, Any],
    load_warnings: list[str],
    revision: int,
) -> None:
    initialize_database(database_path)
    now = _timestamp()
    columns = [str(column) for column in dataframe.columns]
    rows: list[tuple[Any, ...]] = []
    for row_index, row in dataframe.iterrows():
        original = {column: str(row[column]) for column in columns}
        draft = drafts[int(row_index)]
        rows.append(
            (
                dataset_id,
                int(row_index),
                json.dumps(original, ensure_ascii=False, separators=(",", ":")),
                serialize_annotations(draft["entities"]),
                str(draft["status"]),
                str(draft["notes"]),
            )
        )
    with _connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO datasets (
                dataset_id, session_id, filename, columns_json, current_row_index,
                custom_labels_json, filter_state_json, load_warnings_json, revision,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dataset_id) DO UPDATE SET
                session_id=excluded.session_id,
                filename=excluded.filename,
                current_row_index=excluded.current_row_index,
                custom_labels_json=excluded.custom_labels_json,
                filter_state_json=excluded.filter_state_json,
                load_warnings_json=excluded.load_warnings_json,
                revision=excluded.revision,
                updated_at=excluded.updated_at
            """,
            (
                dataset_id,
                session_id,
                filename,
                json.dumps(columns, ensure_ascii=False),
                current_row_index,
                json.dumps(custom_labels, ensure_ascii=False),
                json.dumps(filter_state, ensure_ascii=False),
                json.dumps(load_warnings, ensure_ascii=False),
                revision,
                now,
                now,
            ),
        )
        connection.executemany(
            """
            INSERT INTO records (
                dataset_id, row_index, row_json, draft_entities_json,
                draft_status, draft_notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(dataset_id, row_index) DO UPDATE SET
                draft_entities_json=excluded.draft_entities_json,
                draft_status=excluded.draft_status,
                draft_notes=excluded.draft_notes
            """,
            rows,
        )


def update_local_session(
    database_path: Path,
    dataset_id: str,
    *,
    current_row_index: int,
    current_draft: dict[str, Any],
    custom_labels: list[str],
    filter_state: dict[str, Any],
    load_warnings: list[str],
    revision: int,
) -> None:
    now = _timestamp()
    with _connect(database_path) as connection:
        existing = connection.execute(
            "SELECT revision FROM datasets WHERE dataset_id = ?", (dataset_id,)
        ).fetchone()
        if existing is None:
            raise KeyError(f"Unknown local dataset: {dataset_id}")
        if int(existing["revision"]) == revision:
            return
        connection.execute(
            """
            UPDATE datasets SET
                current_row_index=?, custom_labels_json=?, filter_state_json=?,
                load_warnings_json=?, revision=?, updated_at=?
            WHERE dataset_id=?
            """,
            (
                current_row_index,
                json.dumps(custom_labels, ensure_ascii=False),
                json.dumps(filter_state, ensure_ascii=False),
                json.dumps(load_warnings, ensure_ascii=False),
                revision,
                now,
                dataset_id,
            ),
        )
        connection.execute(
            """
            UPDATE records SET
                draft_entities_json=?, draft_status=?, draft_notes=?
            WHERE dataset_id=? AND row_index=?
            """,
            (
                serialize_annotations(current_draft["entities"]),
                str(current_draft["status"]),
                str(current_draft["notes"]),
                dataset_id,
                current_row_index,
            ),
        )


def _load_dataset_row(connection: sqlite3.Connection, dataset: sqlite3.Row) -> dict[str, Any]:
    columns = json.loads(dataset["columns_json"])
    record_rows = connection.execute(
        """
        SELECT row_index, row_json, draft_entities_json, draft_status, draft_notes
        FROM records WHERE dataset_id=? ORDER BY row_index
        """,
        (dataset["dataset_id"],),
    ).fetchall()
    dataframe_rows: list[dict[str, str]] = []
    drafts: dict[int, dict[str, Any]] = {}
    for record in record_rows:
        row_index = int(record["row_index"])
        values = json.loads(record["row_json"])
        entities = json.loads(record["draft_entities_json"])
        status = str(record["draft_status"])
        notes = str(record["draft_notes"])
        values["gold_entities_json"] = serialize_annotations(entities)
        values["annotation_status"] = status
        values["annotator_notes"] = notes
        dataframe_rows.append(values)
        drafts[row_index] = {"entities": entities, "status": status, "notes": notes}
    dataframe = pd.DataFrame(dataframe_rows, columns=columns).fillna("")
    return {
        "dataframe": dataframe,
        "current_row_index": int(dataset["current_row_index"]),
        "uploaded_file_identity": str(dataset["dataset_id"]),
        "uploaded_filename": str(dataset["filename"]),
        "custom_labels": json.loads(dataset["custom_labels_json"]),
        "filter_state": json.loads(dataset["filter_state_json"]),
        "drafts": drafts,
        "load_warnings": json.loads(dataset["load_warnings_json"]),
        "state_revision": int(dataset["revision"]),
        "export_revision": int(dataset["revision"]),
        "local_dataset_id": str(dataset["dataset_id"]),
        "web_session_id": str(dataset["session_id"]),
    }


def load_local_session(database_path: Path, session_id: str) -> dict[str, Any] | None:
    initialize_database(database_path)
    with _connect(database_path) as connection:
        dataset = connection.execute(
            "SELECT * FROM datasets WHERE session_id=?", (session_id,)
        ).fetchone()
        return _load_dataset_row(connection, dataset) if dataset is not None else None


def load_local_dataset(database_path: Path, dataset_id: str) -> dict[str, Any] | None:
    initialize_database(database_path)
    with _connect(database_path) as connection:
        dataset = connection.execute(
            "SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)
        ).fetchone()
        return _load_dataset_row(connection, dataset) if dataset is not None else None


def list_local_datasets(database_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    initialize_database(database_path)
    with _connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT dataset_id, session_id, filename, updated_at,
                   (SELECT COUNT(*) FROM records
                    WHERE records.dataset_id=datasets.dataset_id) AS row_count,
                   (SELECT COUNT(*) FROM records
                    WHERE records.dataset_id=datasets.dataset_id
                      AND records.draft_status='COMPLETED') AS completed_count
            FROM datasets ORDER BY updated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
