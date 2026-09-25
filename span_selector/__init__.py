from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component(
    "gold_pii_span_selector",
    path=str(Path(__file__).parent / "frontend" / "dist"),
)


def span_selector(text: str, annotations: list[dict], key: str):
    """Render selectable text and return exact browser selection offsets."""
    return _component(mode="span_selector", text=text, annotations=annotations, key=key, default=None)


def session_router(current_session: str | None, reset: bool, ttl_seconds: int, key: str):
    """Synchronize the URL session key with browser sessionStorage."""
    return _component(
        mode="session_router",
        current_session=current_session or "",
        reset=reset,
        ttl_seconds=ttl_seconds,
        key=key,
        default=None,
    )
