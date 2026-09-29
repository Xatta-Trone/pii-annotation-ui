from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st

from span_selector import _component as span_selector_component
from src.annotations import AnnotationError, add_annotation, change_label, delete_annotation, serialize_annotations
from src.auth import ACCESS_CODE_ENV_VAR, access_code_matches, load_access_code
from src.config import (
    DEFAULT_LABELS,
    VALID_STATUSES,
    load_database_path,
    load_runtime_environment,
    load_session_ttl_minutes,
)
from src.data_io import export_dataset, file_identity, load_dataset
from src.label_manager import add_custom_label, label_schema_json, recover_custom_labels
from src.local_store import (
    create_local_dataset,
    initialize_database,
    list_local_datasets,
    load_local_dataset,
    load_local_session,
    update_local_session,
)
from src.navigation import filtered_indices, find_crash_id, jump_to_row, move
from src.session_store import (
    create_session_id,
    prune_expired_sessions,
    restore_session,
    save_session,
)
from src.ui_helpers import display_selection, render_weak_entities, scalar
from src.validation import parse_json_list, validate_entities, validate_span


st.set_page_config(page_title="Gold PII Annotation Tool", page_icon="🔒", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def session_router(current_session: str | None, reset: bool, ttl_seconds: int, key: str):
    """Call the browser-session mode without relying on a hot-reloaded wrapper import."""
    return span_selector_component(
        mode="session_router",
        current_session=current_session or "",
        reset=reset,
        ttl_seconds=ttl_seconds,
        key=key,
        default=None,
    )


def keyboard_navigation(key: str):
    """Call the keyboard-navigation mode through the stable component handle."""
    return span_selector_component(mode="keyboard_navigation", key=key, default=None)


@st.cache_resource
def get_web_session_store() -> dict:
    """Process-local transient storage shared across Streamlit page refreshes."""
    return {}


def init_state() -> None:
    defaults = {
        "dataframe": None,
        "current_row_index": 0,
        "uploaded_file_identity": None,
        "uploaded_filename": None,
        "local_dataset_id": None,
        "custom_labels": [],
        "filter_state": {},
        "drafts": {},
        "load_warnings": [],
        "flash": None,
        "web_session_id": None,
        "clear_browser_route": False,
        "processed_router_event": None,
        "landing_warning": None,
        "pending_keyboard_navigation": None,
        "processed_keyboard_event": None,
        "state_revision": 0,
        "export_revision": 0,
        "cached_export_revision": -1,
        "cached_export_bytes": None,
        "authenticated": False,
        "pending_auth_session_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def active_labels() -> list[str]:
    return [*DEFAULT_LABELS, *st.session_state.custom_labels]


def require_authentication() -> None:
    """Stop before any annotation data or URL session is accessed unless authenticated."""
    if st.session_state.authenticated:
        return

    st.title("Gold PII Annotation Tool")
    st.subheader("Restricted access")
    # Parse here through the original auth API name so Streamlit hot reloads can
    # coexist with an older src.auth module already cached by the process.
    raw_access_codes = load_access_code()
    expected_codes = tuple(
        code.strip() for code in (raw_access_codes or "").split(",") if code.strip()
    )
    if not expected_codes:
        st.error(
            f"Access is not configured. Set {ACCESS_CODE_ENV_VAR} in the app's .env file "
            "or hosting environment."
        )
        st.stop()

    with st.form("access_code_form", clear_on_submit=True):
        provided_code = st.text_input("Access code", type="password", autocomplete="off")
        submitted = st.form_submit_button("Continue", type="primary", width="stretch")
    if submitted:
        matched = False
        for expected_code in expected_codes:
            matched |= access_code_matches(provided_code, expected_code)
        if matched:
            pending_session_id = st.session_state.pending_auth_session_id
            if pending_session_id:
                st.query_params["session"] = pending_session_id
            st.session_state.authenticated = True
            st.rerun()
        st.error("Incorrect access code.")
    st.stop()


def mark_state_changed(*, affects_export: bool = False) -> None:
    """Version mutable state so expensive snapshots and CSV exports are rebuilt only when needed."""
    st.session_state.state_revision += 1
    if affects_export:
        st.session_state.export_revision += 1


def initialize_drafts(dataframe: pd.DataFrame) -> tuple[dict, list[str]]:
    drafts: dict[int, dict] = {}
    warnings: list[str] = []
    labels = active_labels()
    for row_index, row in dataframe.iterrows():
        parsed, parse_error = parse_json_list(row["gold_entities_json"], "gold_entities_json")
        accepted: list[dict] = []
        if parse_error:
            warnings.append(f"Row {row_index + 1} / crash_id {row['crash_id']}: {parse_error}")
        else:
            for entity_index, entity in enumerate(parsed):
                errors = validate_span(entity, str(row["clean_narrative"]), labels)
                if errors:
                    warnings.append(
                        f"Row {row_index + 1} / crash_id {row['crash_id']}, entity {entity_index + 1}: "
                        + " ".join(errors)
                    )
                    continue
                try:
                    accepted = add_annotation(accepted, entity, str(row["clean_narrative"]), labels)
                except AnnotationError as exc:
                    warnings.append(f"Row {row_index + 1} / crash_id {row['crash_id']}, entity {entity_index + 1}: {exc}")
        drafts[row_index] = {
            "entities": accepted,
            "status": str(row["annotation_status"]),
            "notes": str(row["annotator_notes"]),
        }
    return drafts, warnings


def sync_current_widgets(row_index: int) -> bool:
    """Copy rendered widget values into the row draft before any save/navigation."""
    draft = st.session_state.drafts[row_index]
    notes_key = f"notes_{row_index}"
    status_key = f"status_{row_index}"
    changed = False
    if notes_key in st.session_state and draft["notes"] != st.session_state[notes_key]:
        draft["notes"] = st.session_state[notes_key]
        changed = True
    if status_key in st.session_state and draft["status"] != st.session_state[status_key]:
        draft["status"] = st.session_state[status_key]
        changed = True
    labels = active_labels()
    for annotation_index, entity in enumerate(draft["entities"]):
        label_key = f"entity_label_{row_index}_{annotation_index}"
        selected_label = st.session_state.get(label_key)
        if selected_label in labels and selected_label != entity["label"]:
            draft["entities"] = change_label(
                draft["entities"], annotation_index, selected_label, labels
            )
            changed = True
    return changed


def save_row(row_index: int, status: str | None = None) -> bool:
    frame = st.session_state.dataframe
    draft = st.session_state.drafts[row_index]
    changed = sync_current_widgets(row_index)
    if status is not None:
        changed = changed or draft["status"] != status
        draft["status"] = status
    errors = validate_entities(draft["entities"], str(frame.at[row_index, "clean_narrative"]), active_labels())
    if errors:
        st.error("Cannot save: " + " ".join(errors))
        return False
    serialized = serialize_annotations(draft["entities"])
    changed = changed or frame.at[row_index, "gold_entities_json"] != serialized
    changed = changed or frame.at[row_index, "annotation_status"] != draft["status"]
    changed = changed or frame.at[row_index, "annotator_notes"] != draft["notes"]
    frame.at[row_index, "gold_entities_json"] = serialized
    frame.at[row_index, "annotation_status"] = draft["status"]
    frame.at[row_index, "annotator_notes"] = draft["notes"]
    if changed:
        mark_state_changed(affects_export=True)
    st.session_state.flash = f"Saved row {row_index + 1}."
    persist_web_session()
    return True


def export_with_drafts() -> pd.DataFrame:
    exported = st.session_state.dataframe.copy(deep=True)
    for row_index, draft in st.session_state.drafts.items():
        errors = validate_entities(draft["entities"], str(exported.at[row_index, "clean_narrative"]), active_labels())
        if not errors:
            exported.at[row_index, "gold_entities_json"] = serialize_annotations(draft["entities"])
            exported.at[row_index, "annotation_status"] = draft["status"]
            exported.at[row_index, "annotator_notes"] = draft["notes"]
    return exported


def annotated_export_bytes() -> bytes:
    """Return one cached complete export for both download buttons."""
    if (
        st.session_state.cached_export_bytes is None
        or st.session_state.cached_export_revision != st.session_state.export_revision
    ):
        st.session_state.cached_export_bytes = export_dataset(export_with_drafts())
        st.session_state.cached_export_revision = st.session_state.export_revision
    return st.session_state.cached_export_bytes


def persist_web_session() -> None:
    session_id = st.session_state.web_session_id
    if not session_id or st.session_state.dataframe is None:
        return
    save_session(
        WEB_SESSION_STORE,
        session_id,
        {
            "dataframe": st.session_state.dataframe,
            "current_row_index": st.session_state.current_row_index,
            "uploaded_file_identity": st.session_state.uploaded_file_identity,
            "uploaded_filename": st.session_state.uploaded_filename,
            "local_dataset_id": st.session_state.local_dataset_id,
            "custom_labels": st.session_state.custom_labels,
            "filter_state": st.session_state.filter_state,
            "drafts": st.session_state.drafts,
            "load_warnings": st.session_state.load_warnings,
            "state_revision": st.session_state.state_revision,
            "export_revision": st.session_state.export_revision,
        },
        revision=st.session_state.state_revision,
    )
    if st.session_state.local_dataset_id:
        row_index = st.session_state.current_row_index
        try:
            update_local_session(
                database_path,
                st.session_state.local_dataset_id,
                current_row_index=row_index,
                current_draft=st.session_state.drafts[row_index],
                custom_labels=st.session_state.custom_labels,
                filter_state=st.session_state.filter_state,
                load_warnings=st.session_state.load_warnings,
                revision=st.session_state.state_revision,
            )
        except (OSError, sqlite3.Error, KeyError) as exc:
            st.error(f"Local autosave failed. Navigation has been stopped: {exc}")
            st.stop()


def restore_web_session(snapshot: dict, session_id: str) -> None:
    for key in (
        "dataframe", "current_row_index", "uploaded_file_identity", "custom_labels",
        "filter_state", "drafts", "load_warnings",
    ):
        st.session_state[key] = snapshot[key]
    st.session_state.uploaded_filename = snapshot.get("uploaded_filename")
    st.session_state.local_dataset_id = snapshot.get("local_dataset_id")
    # Sessions created before revisioned caching remain recoverable during a hot reload.
    st.session_state.state_revision = int(snapshot.get("state_revision", 0))
    st.session_state.export_revision = int(snapshot.get("export_revision", 0))
    st.session_state.web_session_id = session_id
    filters = snapshot.get("filter_state", {})
    st.session_state["status_filter"] = filters.get("statuses", [])
    st.session_state["source_filter"] = filters.get("source_classes", [])
    st.session_state["year_filter"] = filters.get("years", [])
    st.session_state["only_not_annotated"] = False
    st.session_state.flash = "Recovered the recent annotation session."
    st.session_state.cached_export_revision = -1
    st.session_state.cached_export_bytes = None


def start_new_dataset() -> None:
    """Return to upload without destroying the still-live server snapshot."""
    for key, value in {
        "dataframe": None,
        "current_row_index": 0,
        "uploaded_file_identity": None,
        "uploaded_filename": None,
        "local_dataset_id": None,
        "custom_labels": [],
        "filter_state": {},
        "drafts": {},
        "load_warnings": [],
        "flash": None,
        "web_session_id": None,
        "state_revision": 0,
        "export_revision": 0,
        "cached_export_revision": -1,
        "cached_export_bytes": None,
    }.items():
        st.session_state[key] = value
    st.session_state.clear_browser_route = True
    st.query_params.clear()


def save_and_navigate(step: int, indices: list[int], status: str | None = None) -> None:
    """Single navigation path used by buttons and keyboard shortcuts."""
    current = st.session_state.current_row_index
    if not save_row(current, status=status):
        return
    st.session_state.current_row_index = move(current, indices, step)
    mark_state_changed()
    persist_web_session()
    st.rerun()


def save_and_jump(target_row_index: int) -> None:
    """Save the complete current draft before a direct row/crash-ID jump."""
    current = st.session_state.current_row_index
    if not save_row(current):
        return
    st.session_state.current_row_index = target_row_index
    mark_state_changed()
    persist_web_session()
    st.rerun()


init_state()
requested_session_id = str(st.query_params.get("session", "")) or None
if requested_session_id and not st.session_state.authenticated:
    st.session_state.pending_auth_session_id = requested_session_id
require_authentication()
try:
    runtime_environment = load_runtime_environment()
    session_ttl_minutes = load_session_ttl_minutes()
except ValueError as exc:
    st.error(f"Invalid application configuration: {exc}")
    st.stop()
session_ttl_seconds = session_ttl_minutes * 60
database_path = load_database_path(runtime_environment)
try:
    initialize_database(database_path)
except (OSError, sqlite3.Error) as exc:
    st.error(f"Could not initialize SQLite storage: {exc}")
    st.stop()
WEB_SESSION_STORE = get_web_session_store()
prune_expired_sessions(WEB_SESSION_STORE, ttl_seconds=session_ttl_seconds)
title_column, _, download_column = st.columns(
    [3, 2, 1.6],
    vertical_alignment="center",
)
with title_column:
    st.title("Gold PII Annotation Tool")
with download_column:
    top_download_slot = st.empty()

url_session_id = str(st.query_params.get("session", "")) or None
router_event = session_router(
    current_session=url_session_id,
    reset=st.session_state.clear_browser_route,
    ttl_seconds=session_ttl_seconds,
    key="browser_session_router",
)
st.session_state.clear_browser_route = False

if router_event and router_event.get("event_id") != st.session_state.processed_router_event:
    st.session_state.processed_router_event = router_event.get("event_id")
    action = router_event.get("action")
    routed_session_id = router_event.get("session_id")
    # The root URL is an intentional dataset chooser. A browser-stored session
    # must never auto-open a dataset; users resume explicitly from the list.
    # Session URLs still restore below when the URL contains ?session=...
    if action == "expired":
        if routed_session_id:
            WEB_SESSION_STORE.pop(routed_session_id, None)
        if url_session_id:
            start_new_dataset()
            st.session_state.landing_warning = (
                f"The annotation session expired after {session_ttl_minutes} minutes of inactivity."
            )
            st.rerun()

if st.session_state.dataframe is None and url_session_id:
    snapshot = restore_session(
        WEB_SESSION_STORE, url_session_id, ttl_seconds=session_ttl_seconds
    )
    if snapshot is None:
        snapshot = load_local_session(database_path, url_session_id)
    if snapshot is not None:
        restore_web_session(snapshot, url_session_id)
    else:
        start_new_dataset()
        st.session_state.landing_warning = "This annotation URL has expired or is no longer available."
        st.rerun()

if st.session_state.dataframe is not None:
    top_download_timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    with top_download_slot:
        st.download_button(
            "Download Annotated Dataset",
            annotated_export_bytes(),
            file_name=f"gold_pii_annotations_{top_download_timestamp}.csv",
            mime="text/csv",
            key="top_download_dataset",
            width="stretch",
        )

uploaded = None
if st.session_state.dataframe is None:
    uploaded = st.file_uploader("Upload crash-narrative dataset", type=["csv", "tsv"])
if uploaded is not None:
    content = uploaded.getvalue()
    identity = file_identity(uploaded.name, content)
    if identity != st.session_state.uploaded_file_identity:
        existing_local = load_local_dataset(database_path, identity)
        if existing_local is not None:
            existing_session_id = existing_local["web_session_id"]
            restore_web_session(existing_local, existing_session_id)
            st.query_params["session"] = existing_session_id
            st.session_state.flash = "Resumed the existing SQLite dataset."
            st.rerun()
        try:
            loaded = load_dataset(content, uploaded.name)
        except Exception as exc:
            st.error(f"Could not load dataset: {exc}")
            st.stop()
        st.session_state.dataframe = loaded
        st.session_state.uploaded_file_identity = identity
        st.session_state.uploaded_filename = uploaded.name
        st.session_state.custom_labels = recover_custom_labels(
            loaded["gold_entities_json"], loaded["clean_narrative"]
        )
        st.session_state.drafts, st.session_state.load_warnings = initialize_drafts(loaded)
        remaining = loaded.index[loaded["annotation_status"] == "NOT_ANNOTATED"].tolist()
        st.session_state.current_row_index = remaining[0] if remaining else 0
        mark_state_changed(affects_export=True)
        session_id = create_session_id(identity)
        st.session_state.web_session_id = session_id
        st.session_state.local_dataset_id = identity
        try:
            create_local_dataset(
                database_path,
                identity,
                session_id,
                uploaded.name,
                loaded,
                st.session_state.drafts,
                current_row_index=st.session_state.current_row_index,
                custom_labels=st.session_state.custom_labels,
                filter_state=st.session_state.filter_state,
                load_warnings=st.session_state.load_warnings,
                revision=st.session_state.state_revision,
            )
        except (OSError, sqlite3.Error) as exc:
            st.error(f"Could not persist the uploaded dataset to SQLite: {exc}")
            st.stop()
        st.query_params["session"] = session_id
        persist_web_session()
        st.session_state.flash = f"Loaded {len(loaded):,} records."
        st.rerun()

if st.session_state.dataframe is None:
    recent_datasets = list_local_datasets(database_path)
    if recent_datasets:
        st.subheader("Resume Saved Dataset")
        recent_by_id = {item["dataset_id"]: item for item in recent_datasets}
        selected_dataset_id = st.selectbox(
            "Saved dataset",
            list(recent_by_id),
            format_func=lambda dataset_id: (
                f'{recent_by_id[dataset_id]["filename"]} · '
                f'{recent_by_id[dataset_id]["completed_count"]:,} of '
                f'{recent_by_id[dataset_id]["row_count"]:,} completed · '
                f'updated {recent_by_id[dataset_id]["updated_at"]}'
            ),
        )
        if st.button("Resume Selected Dataset", type="primary"):
            local_snapshot = load_local_dataset(database_path, selected_dataset_id)
            if local_snapshot is not None:
                local_session_id = local_snapshot["web_session_id"]
                restore_web_session(local_snapshot, local_session_id)
                st.query_params["session"] = local_session_id
                st.rerun()

if st.session_state.dataframe is None:
    if st.session_state.landing_warning:
        st.warning(st.session_state.landing_warning)
        st.session_state.landing_warning = None
    st.info("Upload a UTF-8 CSV or TSV containing crash_id, clean_narrative, and weak_pii_entities_json.")
    st.stop()

df: pd.DataFrame = st.session_state.dataframe

# Sidebar filters and dashboard
with st.sidebar:
    if st.button("Log out", width="stretch"):
        st.session_state.authenticated = False
        st.rerun()
    st.divider()
    st.caption(f"Temporary session: `{st.session_state.web_session_id}`")
    if runtime_environment == "local":
        st.caption("Storage: Local SQLite (autosaved)")
    else:
        st.caption("Storage: Deployment-local SQLite (autosaved)")
    st.metric("Session timeout (TTL)", f"{session_ttl_minutes} min")
    st.caption("The timer resets after activity.")
    if st.button("Start / Upload New Dataset", width="stretch"):
        persist_web_session()
        start_new_dataset()
        st.rerun()

    st.header("Progress summary")
    status_counts = df["annotation_status"].value_counts()
    completed = int(status_counts.get("COMPLETED", 0))
    not_annotated = int(status_counts.get("NOT_ANNOTATED", 0))
    needs_review = int(status_counts.get("NEEDS_REVIEW", 0))
    entity_counts = [len(parse_json_list(value, "gold")[0]) for value in df["gold_entities_json"]]
    st.metric("Total records", f"{len(df):,}")
    c1, c2 = st.columns(2)
    c1.metric("Completed", f"{completed:,}")
    c2.metric("Not annotated", f"{not_annotated:,}")
    c1.metric("Needs review", f"{needs_review:,}")
    c2.metric("With gold PII", f"{sum(count > 0 for count in entity_counts):,}")
    st.metric("Total gold entities", f"{sum(entity_counts):,}")
    st.progress(completed / len(df) if len(df) else 0, text=f"{completed / len(df):.1%} completed" if len(df) else "0% completed")

    st.header("Filters")
    only_unannotated = st.checkbox("Show only NOT_ANNOTATED", key="only_not_annotated")
    selected_statuses = st.multiselect("Annotation status", VALID_STATUSES, key="status_filter")
    if only_unannotated:
        selected_statuses = ["NOT_ANNOTATED"]
    source_options = sorted(df["source_class"].astype(str).unique()) if "source_class" in df else []
    year_options = sorted(df["year"].astype(str).unique()) if "year" in df else []
    selected_sources = st.multiselect("Source class", source_options, key="source_filter")
    selected_years = st.multiselect("Year", year_options, key="year_filter")
    new_filter_state = {
        "statuses": selected_statuses, "source_classes": selected_sources, "years": selected_years
    }
    if new_filter_state != st.session_state.filter_state:
        st.session_state.filter_state = new_filter_state
        mark_state_changed()

indices = filtered_indices(df, **st.session_state.filter_state)
if not indices:
    st.warning("No records match the current filters. Clear or change the sidebar filters.")
    st.stop()
if st.session_state.current_row_index not in indices:
    st.session_state.current_row_index = indices[0]
    mark_state_changed()

with st.sidebar:
    st.header("Navigation")
    row_number = st.number_input("Jump to row", min_value=1, max_value=len(df), value=st.session_state.current_row_index + 1)
    if st.button("Go to row", width="stretch"):
        save_and_jump(jump_to_row(int(row_number), len(df)))
    crash_target = st.text_input("Jump to crash ID")
    if st.button("Go to crash ID", width="stretch"):
        try:
            save_and_jump(find_crash_id(df, crash_target))
        except ValueError as exc:
            st.error(str(exc))

    st.header("Manage custom labels")
    if st.session_state.custom_labels:
        st.caption(", ".join(st.session_state.custom_labels))
    custom_value = st.text_input("New label")
    if st.button("Add label", width="stretch"):
        try:
            st.session_state.custom_labels = add_custom_label(st.session_state.custom_labels, custom_value)
            mark_state_changed(affects_export=True)
            st.success(f"Added {st.session_state.custom_labels[-1]}")
            persist_web_session()
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    st.header("Downloads")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        "Download Annotated Dataset", annotated_export_bytes(),
        file_name=f"gold_pii_annotations_{timestamp}.csv", mime="text/csv", width="stretch",
        key="sidebar_download_dataset",
    )
    st.download_button(
        "Download Label Schema", label_schema_json(st.session_state.custom_labels),
        file_name=f"gold_pii_label_schema_{timestamp}.json", mime="application/json", width="stretch",
    )

row_index = st.session_state.current_row_index
row = df.loc[row_index]
draft = st.session_state.drafts[row_index]
position = indices.index(row_index) + 1

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None
if st.session_state.load_warnings:
    with st.expander(f"Upload validation warnings ({len(st.session_state.load_warnings)})"):
        for warning in st.session_state.load_warnings:
            st.warning(warning)

st.subheader(f"Record {position} of {len(indices)}")
if len(indices) != len(df):
    st.caption(f"Filtered view · original row {row_index + 1} of {len(df)}")
header = st.columns(6)
header[0].metric("Crash ID", scalar(row.get("crash_id")))
header[1].metric("Year", scalar(row.get("year")))
header[2].metric("Source Class", scalar(row.get("source_class")))
narrative = str(row["clean_narrative"])
header[3].metric("Word Count", scalar(row.get("word_count"), str(len(narrative.split()))))
header[4].metric("Character Count", scalar(row.get("char_count"), str(len(narrative))))
weak_items, _ = parse_json_list(row["weak_pii_entities_json"], "weak")
header[5].metric("Weak PII Count", len(weak_items))

clean_column, redacted_column = st.columns(2, gap="large")
with clean_column:
    st.subheader("Clean Narrative")
with redacted_column:
    st.subheader("Cleaned Redacted Narrative")
redacted_narrative = str(row.get("clean_redactedNarrative", "") or "")
selection = span_selector_component(
    mode="span_selector",
    text=narrative,
    annotations=draft["entities"],
    redacted_text=redacted_narrative,
    key=f"selector_{row_index}",
    default=None,
)
processed_selection = st.session_state.get(f"processed_selection_{row_index}")
if selection and selection.get("event_type") == "selection" and selection.get("selection_id") != processed_selection:
    st.session_state[f"selection_{row_index}"] = selection
current_selection = st.session_state.get(f"selection_{row_index}")
gold_column, weak_column = st.columns(2, gap="large")
with gold_column:
    st.subheader("Gold Annotation Controls")
    display_selection(current_selection)
    st.markdown("PII label")
    add_columns = st.columns([2, 1])
    selected_label = add_columns[0].selectbox(
        "PII label",
        active_labels(),
        key=f"add_label_{row_index}",
        label_visibility="collapsed",
    )
    if add_columns[1].button("Add annotation", type="primary", width="stretch", disabled=not current_selection):
        try:
            raw_selection_text = str(current_selection["text"])
            trimmed_selection_text = raw_selection_text.strip()
            if not trimmed_selection_text:
                raise AnnotationError("Select at least one non-whitespace character.")
            leading_whitespace_count = len(raw_selection_text) - len(raw_selection_text.lstrip())
            trimmed_start = int(current_selection["start_char"]) + leading_whitespace_count
            entity = {
                "text": trimmed_selection_text,
                "label": selected_label,
                "start_char": trimmed_start,
                "end_char": trimmed_start + len(trimmed_selection_text),
            }
            draft["entities"] = add_annotation(draft["entities"], entity, narrative, active_labels())
            mark_state_changed(affects_export=True)
            st.session_state[f"processed_selection_{row_index}"] = current_selection.get("selection_id")
            st.session_state.pop(f"selection_{row_index}", None)
            persist_web_session()
            st.rerun()
        except (AnnotationError, KeyError, TypeError, ValueError) as exc:
            st.error(str(exc))

    st.subheader("Gold Annotations")
    if not draft["entities"]:
        st.info("No gold annotations for this record.")
    for annotation_index, entity in enumerate(list(draft["entities"])):
        cols = st.columns([3, 2, 1])
        cols[0].write(
            f'{entity["text"]} ({entity["start_char"]}, {entity["end_char"]})'
        )
        new_label = cols[1].selectbox(
            "Label", active_labels(), index=active_labels().index(entity["label"]),
            key=f"entity_label_{row_index}_{annotation_index}", label_visibility="collapsed",
        )
        if new_label != entity["label"]:
            draft["entities"] = change_label(draft["entities"], annotation_index, new_label, active_labels())
            mark_state_changed(affects_export=True)
        if cols[2].button("Delete", key=f"delete_{row_index}_{annotation_index}", width="stretch"):
            draft["entities"] = delete_annotation(draft["entities"], annotation_index)
            mark_state_changed(affects_export=True)
            persist_web_session()
            st.rerun()

with weak_column:
    render_weak_entities(row["weak_pii_entities_json"])

st.subheader("Annotator Notes")
notes_value = st.text_area("Notes", value=draft["notes"], key=f"notes_{row_index}", label_visibility="collapsed")
status_value = st.selectbox(
    "Annotation status", VALID_STATUSES, index=VALID_STATUSES.index(draft["status"]), key=f"status_{row_index}"
)
if notes_value != draft["notes"] or status_value != draft["status"]:
    draft["notes"] = notes_value
    draft["status"] = status_value
    mark_state_changed(affects_export=True)
persist_web_session()

buttons = st.columns(6)
if buttons[0].button("Previous", width="stretch"):
    save_and_navigate(-1, indices)
if buttons[1].button("Save", width="stretch"):
    if save_row(row_index):
        st.rerun()
if buttons[2].button("Save & Next", width="stretch"):
    save_and_navigate(1, indices)
if buttons[3].button("Mark Completed & Next", type="primary", width="stretch"):
    save_and_navigate(1, indices, status="COMPLETED")
if buttons[4].button("Mark Needs Review", width="stretch"):
    if save_row(row_index, "NEEDS_REVIEW"):
        st.rerun()
if buttons[5].button("Next", width="stretch"):
    save_and_navigate(1, indices)

page_keyboard_event = keyboard_navigation(key="page_keyboard_navigation")
if (
    page_keyboard_event
    and page_keyboard_event.get("event_id") != st.session_state.processed_keyboard_event
):
    st.session_state.pending_keyboard_navigation = page_keyboard_event

pending_navigation = st.session_state.pending_keyboard_navigation
if (
    pending_navigation
    and pending_navigation.get("event_id") != st.session_state.processed_keyboard_event
):
    st.session_state.processed_keyboard_event = pending_navigation.get("event_id")
    st.session_state.pending_keyboard_navigation = None
    direction = pending_navigation.get("direction")
    current_status = st.session_state.get(
        f"status_{row_index}",
        draft["status"],
    )
    keyboard_status = "COMPLETED" if current_status == "NOT_ANNOTATED" else None
    save_and_navigate(
        1 if direction == "next" else -1,
        indices,
        status=keyboard_status,
    )

st.caption("Offsets use Python slicing semantics (start inclusive, end exclusive). Character offsets are the canonical gold positions.")
