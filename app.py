from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from span_selector import session_router, span_selector
from src.annotations import AnnotationError, add_annotation, change_label, delete_annotation, serialize_annotations
from src.config import DEFAULT_LABELS, VALID_STATUSES
from src.data_io import export_dataset, file_identity, load_dataset
from src.label_manager import add_custom_label, label_schema_json, recover_custom_labels
from src.navigation import filtered_indices, find_crash_id, jump_to_row, move
from src.session_store import (
    SESSION_TTL_SECONDS,
    create_session_id,
    prune_expired_sessions,
    restore_session,
    save_session,
)
from src.ui_helpers import display_selection, render_weak_entities, scalar
from src.validation import parse_json_list, validate_entities, validate_span


st.set_page_config(page_title="Gold PII Annotation Tool", page_icon="🔒", layout="wide")


@st.cache_resource
def get_web_session_store() -> dict:
    """Process-local transient storage shared across Streamlit page refreshes."""
    return {}


def init_state() -> None:
    defaults = {
        "dataframe": None,
        "current_row_index": 0,
        "uploaded_file_identity": None,
        "custom_labels": [],
        "filter_state": {},
        "drafts": {},
        "load_warnings": [],
        "flash": None,
        "web_session_id": None,
        "clear_browser_route": False,
        "processed_router_event": None,
        "landing_warning": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def active_labels() -> list[str]:
    return [*DEFAULT_LABELS, *st.session_state.custom_labels]


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


def save_row(row_index: int, status: str | None = None) -> bool:
    frame = st.session_state.dataframe
    draft = st.session_state.drafts[row_index]
    if status is not None:
        draft["status"] = status
    errors = validate_entities(draft["entities"], str(frame.at[row_index, "clean_narrative"]), active_labels())
    if errors:
        st.error("Cannot save: " + " ".join(errors))
        return False
    frame.at[row_index, "gold_entities_json"] = serialize_annotations(draft["entities"])
    frame.at[row_index, "annotation_status"] = draft["status"]
    frame.at[row_index, "annotator_notes"] = draft["notes"]
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
            "custom_labels": st.session_state.custom_labels,
            "filter_state": st.session_state.filter_state,
            "drafts": st.session_state.drafts,
            "load_warnings": st.session_state.load_warnings,
        },
    )


def restore_web_session(snapshot: dict, session_id: str) -> None:
    for key in (
        "dataframe", "current_row_index", "uploaded_file_identity", "custom_labels",
        "filter_state", "drafts", "load_warnings",
    ):
        st.session_state[key] = snapshot[key]
    st.session_state.web_session_id = session_id
    filters = snapshot.get("filter_state", {})
    st.session_state["status_filter"] = filters.get("statuses", [])
    st.session_state["source_filter"] = filters.get("source_classes", [])
    st.session_state["year_filter"] = filters.get("years", [])
    st.session_state["only_not_annotated"] = False
    st.session_state.flash = "Recovered the recent annotation session."


def start_new_dataset() -> None:
    """Return to upload without destroying the still-live server snapshot."""
    for key, value in {
        "dataframe": None,
        "current_row_index": 0,
        "uploaded_file_identity": None,
        "custom_labels": [],
        "filter_state": {},
        "drafts": {},
        "load_warnings": [],
        "flash": None,
        "web_session_id": None,
    }.items():
        st.session_state[key] = value
    st.session_state.clear_browser_route = True
    st.query_params.clear()


def navigate(step: int, indices: list[int]) -> None:
    st.session_state.current_row_index = move(st.session_state.current_row_index, indices, step)
    persist_web_session()
    st.rerun()


init_state()
WEB_SESSION_STORE = get_web_session_store()
prune_expired_sessions(WEB_SESSION_STORE)
st.title("Gold PII Annotation Tool")

url_session_id = str(st.query_params.get("session", "")) or None
router_event = session_router(
    current_session=url_session_id,
    reset=st.session_state.clear_browser_route,
    ttl_seconds=SESSION_TTL_SECONDS,
    key="browser_session_router",
)
st.session_state.clear_browser_route = False

if router_event and router_event.get("event_id") != st.session_state.processed_router_event:
    st.session_state.processed_router_event = router_event.get("event_id")
    action = router_event.get("action")
    routed_session_id = router_event.get("session_id")
    if action == "resume" and not url_session_id and routed_session_id:
        if restore_session(WEB_SESSION_STORE, routed_session_id) is not None:
            st.query_params["session"] = routed_session_id
            st.rerun()
        st.session_state.clear_browser_route = True
        st.session_state.landing_warning = "The previous browser session has expired. Upload a dataset to begin again."
    elif action == "expired":
        if routed_session_id:
            WEB_SESSION_STORE.pop(routed_session_id, None)
        if url_session_id:
            start_new_dataset()
            st.session_state.landing_warning = "The annotation session expired after 15 minutes of inactivity."
            st.rerun()

if st.session_state.dataframe is None and url_session_id:
    snapshot = restore_session(WEB_SESSION_STORE, url_session_id)
    if snapshot is not None:
        restore_web_session(snapshot, url_session_id)
    else:
        start_new_dataset()
        st.session_state.landing_warning = "This annotation URL has expired or is no longer available."
        st.rerun()

uploaded = st.file_uploader("Upload crash-narrative dataset", type=["csv", "tsv"])
if uploaded is not None:
    content = uploaded.getvalue()
    identity = file_identity(uploaded.name, content)
    if identity != st.session_state.uploaded_file_identity:
        try:
            loaded = load_dataset(content, uploaded.name)
        except Exception as exc:
            st.error(f"Could not load dataset: {exc}")
            st.stop()
        st.session_state.dataframe = loaded
        st.session_state.uploaded_file_identity = identity
        st.session_state.custom_labels = recover_custom_labels(
            loaded["gold_entities_json"], loaded["clean_narrative"]
        )
        st.session_state.drafts, st.session_state.load_warnings = initialize_drafts(loaded)
        remaining = loaded.index[loaded["annotation_status"] == "NOT_ANNOTATED"].tolist()
        st.session_state.current_row_index = remaining[0] if remaining else 0
        session_id = create_session_id(identity)
        st.session_state.web_session_id = session_id
        st.query_params["session"] = session_id
        persist_web_session()
        st.session_state.flash = f"Loaded {len(loaded):,} records."
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
    st.caption(f"Temporary session: `{st.session_state.web_session_id}`")
    st.caption("Automatically recoverable for 15 minutes after the last activity.")
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
    st.session_state.filter_state = {
        "statuses": selected_statuses, "source_classes": selected_sources, "years": selected_years
    }

indices = filtered_indices(df, **st.session_state.filter_state)
if not indices:
    st.warning("No records match the current filters. Clear or change the sidebar filters.")
    st.stop()
if st.session_state.current_row_index not in indices:
    st.session_state.current_row_index = indices[0]

with st.sidebar:
    st.header("Navigation")
    row_number = st.number_input("Jump to row", min_value=1, max_value=len(df), value=st.session_state.current_row_index + 1)
    if st.button("Go to row", width="stretch"):
        st.session_state.current_row_index = jump_to_row(int(row_number), len(df))
        persist_web_session()
        st.rerun()
    crash_target = st.text_input("Jump to crash ID")
    if st.button("Go to crash ID", width="stretch"):
        try:
            st.session_state.current_row_index = find_crash_id(df, crash_target)
            persist_web_session()
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    st.header("Manage custom labels")
    if st.session_state.custom_labels:
        st.caption(", ".join(st.session_state.custom_labels))
    custom_value = st.text_input("New label")
    if st.button("Add label", width="stretch"):
        try:
            st.session_state.custom_labels = add_custom_label(st.session_state.custom_labels, custom_value)
            st.success(f"Added {st.session_state.custom_labels[-1]}")
            persist_web_session()
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    st.header("Downloads")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        "Download Annotated Dataset", export_dataset(export_with_drafts()),
        file_name=f"gold_pii_annotations_{timestamp}.csv", mime="text/csv", width="stretch",
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

st.subheader("Narrative annotation interface")
selection = span_selector(narrative, draft["entities"], key=f"selector_{row_index}")
processed_selection = st.session_state.get(f"processed_selection_{row_index}")
if selection and selection.get("selection_id") != processed_selection:
    st.session_state[f"selection_{row_index}"] = selection
current_selection = st.session_state.get(f"selection_{row_index}")
display_selection(current_selection)
add_columns = st.columns([3, 1])
selected_label = add_columns[0].selectbox("PII label", active_labels(), key=f"add_label_{row_index}")
if add_columns[1].button("Add annotation", type="primary", width="stretch", disabled=not current_selection):
    try:
        entity = {
            "text": current_selection["text"], "label": selected_label,
            "start_char": int(current_selection["start_char"]), "end_char": int(current_selection["end_char"]),
        }
        draft["entities"] = add_annotation(draft["entities"], entity, narrative, active_labels())
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
    cols = st.columns([3, 2, 1, 1, 1])
    cols[0].write(entity["text"])
    new_label = cols[1].selectbox(
        "Label", active_labels(), index=active_labels().index(entity["label"]),
        key=f"entity_label_{row_index}_{annotation_index}", label_visibility="collapsed",
    )
    cols[2].write(str(entity["start_char"]))
    cols[3].write(str(entity["end_char"]))
    if new_label != entity["label"]:
        draft["entities"] = change_label(draft["entities"], annotation_index, new_label, active_labels())
    if cols[4].button("Delete", key=f"delete_{row_index}_{annotation_index}"):
        draft["entities"] = delete_annotation(draft["entities"], annotation_index)
        persist_web_session()
        st.rerun()

render_weak_entities(row["weak_pii_entities_json"])

st.subheader("Annotator Notes")
draft["notes"] = st.text_area("Notes", value=draft["notes"], key=f"notes_{row_index}", label_visibility="collapsed")
draft["status"] = st.selectbox(
    "Annotation status", VALID_STATUSES, index=VALID_STATUSES.index(draft["status"]), key=f"status_{row_index}"
)
persist_web_session()

buttons = st.columns(6)
if buttons[0].button("Previous", width="stretch"):
    navigate(-1, indices)
if buttons[1].button("Save", width="stretch"):
    if save_row(row_index):
        st.rerun()
if buttons[2].button("Save & Next", width="stretch"):
    if save_row(row_index):
        navigate(1, indices)
if buttons[3].button("Mark Completed & Next", type="primary", width="stretch"):
    if save_row(row_index, "COMPLETED"):
        navigate(1, indices)
if buttons[4].button("Mark Needs Review", width="stretch"):
    if save_row(row_index, "NEEDS_REVIEW"):
        st.rerun()
if buttons[5].button("Next", width="stretch"):
    navigate(1, indices)

st.caption("Offsets use Python slicing semantics (start inclusive, end exclusive). Character offsets are the canonical gold positions.")
