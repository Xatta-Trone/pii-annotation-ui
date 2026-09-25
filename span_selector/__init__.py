from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component(
    "gold_pii_span_selector",
    path=str(Path(__file__).parent / "frontend" / "dist"),
)


def span_selector(text: str, annotations: list[dict], key: str):
    """Render selectable text and return exact browser selection offsets."""
    return _component(text=text, annotations=annotations, key=key, default=None)

