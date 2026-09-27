from __future__ import annotations

import html

import streamlit as st

from .validation import parse_json_list


def scalar(value, fallback="—") -> str:
    text = str(value) if value is not None else ""
    return text if text else fallback


def render_weak_entities(value) -> tuple[list, str | None]:
    entities, error = parse_json_list(value, "weak_pii_entities_json")
    st.subheader("Weak PII Reference")
    st.caption("Reference information only — weak entities are never automatically accepted or copied into Gold.")
    if error:
        st.warning(error)
    elif not entities:
        st.info("No weak PII reference available. The narrative still requires independent human review.")
    else:
        with st.container(border=True):
            for entity in entities:
                if isinstance(entity, dict):
                    text = html.escape(str(entity.get("text", "")))
                    start = html.escape(str(entity.get("start", "")))
                    end = html.escape(str(entity.get("end", "")))
                    st.markdown(f"- **{text}** `({start}, {end})`")
    return entities, error


def render_redacted_narrative(value) -> None:
    st.subheader("Cleaned Redacted Narrative")
    text = "" if value is None else str(value)
    st.caption("Comparison reference only. Gold offsets always use the Clean Narrative.")
    st.code(
        text or "No cleaned redacted narrative available for this record.",
        language=None,
        wrap_lines=True,
        height=258,
    )


def display_selection(selection: dict | None):
    if selection:
        st.caption(
            f'Selected [{selection["start_char"]}, {selection["end_char"]}): '
            f'“{html.escape(selection["text"])}”'
        )
