from __future__ import annotations

import html

import streamlit as st

from .validation import parse_json_list


def scalar(value, fallback="—") -> str:
    text = str(value) if value is not None else ""
    return text if text else fallback


def render_weak_entities(value) -> tuple[list, str | None]:
    entities, error = parse_json_list(value, "weak_pii_entities_json")
    st.subheader("Weak PII Entities — Reference Only")
    st.caption("These candidates are not gold annotations and are never accepted automatically.")
    if error:
        st.warning(error)
    elif not entities:
        st.info("No weak PII entities detected.")
    else:
        rows = []
        for entity in entities:
            if isinstance(entity, dict):
                rows.append({"Text": entity.get("text", ""), "Start": entity.get("start", ""), "End": entity.get("end", "")})
        st.dataframe(rows, width="stretch", hide_index=True)
    return entities, error


def display_selection(selection: dict | None):
    if selection:
        st.caption(
            f'Selected [{selection["start_char"]}, {selection["end_char"]}): '
            f'“{html.escape(selection["text"])}”'
        )
