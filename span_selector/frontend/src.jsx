import React, {useEffect, useMemo, useRef} from "react";
import {createRoot} from "react-dom/client";
import {Streamlit, withStreamlitConnection} from "streamlit-component-lib";
import "./style.css";

function segments(text, annotations) {
  const chars = Array.from(text);
  const sorted = [...annotations].sort((a, b) => a.start_char - b.start_char);
  const result = [];
  let cursor = 0;
  sorted.forEach((item, index) => {
    if (item.start_char > cursor) result.push({text: chars.slice(cursor, item.start_char).join("")});
    result.push({text: chars.slice(item.start_char, item.end_char).join(""), label: item.label, index});
    cursor = item.end_char;
  });
  if (cursor < chars.length) result.push({text: chars.slice(cursor).join("")});
  return result;
}

function highlightedRedactions(text) {
  return String(text || "").split(/(xxx)/gi).map((part, index) =>
    part.toLowerCase() === "xxx"
      ? <mark className="redaction-token" key={index}>{part}</mark>
      : part
  );
}

function Selector({args}) {
  const rootRef = useRef(null);
  const redactedRef = useRef(null);
  const synchronizingScroll = useRef(false);
  const parts = useMemo(() => segments(args.text || "", args.annotations || []), [args.text, args.annotations]);
  useEffect(() => {
    Streamlit.setFrameHeight((rootRef.current?.parentElement?.scrollHeight || 280) + 4);
  }, [parts]);
  useEffect(() => {
    function navigate(event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      Streamlit.setComponentValue({
        event_type: "navigation",
        direction: event.key === "ArrowRight" ? "next" : "previous",
        event_id: `${Date.now()}-${Math.random()}`,
      });
    }
    document.addEventListener("keydown", navigate);
    return () => document.removeEventListener("keydown", navigate);
  }, []);

  function offsetWithin(root, node, offset) {
    const range = document.createRange();
    range.selectNodeContents(root);
    range.setEnd(node, offset);
    return Array.from(range.toString()).length;
  }

  function selected() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
    const range = selection.getRangeAt(0);
    const root = rootRef.current;
    if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return;
    const start = offsetWithin(root, range.startContainer, range.startOffset);
    const end = offsetWithin(root, range.endContainer, range.endOffset);
    const lo = Math.min(start, end), hi = Math.max(start, end);
    if (lo === hi) return;
    Streamlit.setComponentValue({
      event_type: "selection",
      text: Array.from(args.text || "").slice(lo, hi).join(""), start_char: lo, end_char: hi,
      selection_id: `${Date.now()}-${Math.random()}`
    });
  }

  function synchronizeScroll(source, target) {
    if (!source || !target || synchronizingScroll.current) return;
    synchronizingScroll.current = true;
    const sourceRange = Math.max(0, source.scrollHeight - source.clientHeight);
    const targetRange = Math.max(0, target.scrollHeight - target.clientHeight);
    const progress = sourceRange ? source.scrollTop / sourceRange : 0;
    target.scrollTop = progress * targetRange;
    requestAnimationFrame(() => { synchronizingScroll.current = false; });
  }

  return <div className="narrative-grid">
    <div>
      <div className="hint">Drag across the exact text to select it. Existing gold spans are highlighted.</div>
      <div className="narrative" ref={rootRef} onMouseUp={selected}
        onScroll={() => synchronizeScroll(rootRef.current, redactedRef.current)}>
        {parts.map((part, i) => part.label
          ? <mark key={i} title={`${part.label} [${part.index}]`}>{part.text}</mark>
          : <React.Fragment key={i}>{part.text}</React.Fragment>)}
      </div>
    </div>
    <div>
      <div className="hint">Comparison reference only. Gold offsets always use the Clean Narrative above.</div>
      <div className="redacted" ref={redactedRef}
        onScroll={() => synchronizeScroll(redactedRef.current, rootRef.current)}>
        {highlightedRedactions(
          args.redacted_text || "No cleaned redacted narrative available for this record."
        )}
      </div>
    </div>
  </div>;
}

function SessionRouter({args}) {
  useEffect(() => {
    Streamlit.setFrameHeight(0);
    const sessionKey = "gold_pii_annotation_session";
    const activityKey = "gold_pii_annotation_last_activity";
    const now = Date.now();
    const ttlMs = Number(args.ttl_seconds || 900) * 1000;
    const eventId = `${now}-${Math.random()}`;

    if (args.reset) {
      sessionStorage.removeItem(sessionKey);
      sessionStorage.removeItem(activityKey);
      Streamlit.setComponentValue({action: "cleared", event_id: eventId});
      return;
    }

    const storedSession = sessionStorage.getItem(sessionKey) || "";
    const lastActivity = Number(sessionStorage.getItem(activityKey) || 0);
    if (lastActivity && now - lastActivity > ttlMs) {
      sessionStorage.removeItem(sessionKey);
      sessionStorage.removeItem(activityKey);
      Streamlit.setComponentValue({action: "expired", session_id: storedSession, event_id: eventId});
      return;
    }

    if (args.current_session) {
      sessionStorage.setItem(sessionKey, args.current_session);
      sessionStorage.setItem(activityKey, String(now));
      Streamlit.setComponentValue({action: "active", session_id: args.current_session, event_id: eventId});
    } else if (storedSession) {
      Streamlit.setComponentValue({action: "resume", session_id: storedSession, event_id: eventId});
    }
  }, [args.current_session, args.reset, args.ttl_seconds]);
  return null;
}

function KeyboardNavigation() {
  useEffect(() => {
    Streamlit.setFrameHeight(0);
    function navigate(event) {
      const target = event.target;
      const tag = (target?.tagName || "").toLowerCase();
      const isEditing = target?.isContentEditable || ["input", "textarea", "select"].includes(tag);
      if (isEditing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      Streamlit.setComponentValue({
        direction: event.key === "ArrowRight" ? "next" : "previous",
        event_id: `${Date.now()}-${Math.random()}`,
      });
    }
    let targetDocument = document;
    try { targetDocument = window.parent.document; } catch (_) {}
    targetDocument.addEventListener("keydown", navigate);
    return () => targetDocument.removeEventListener("keydown", navigate);
  }, []);
  return null;
}

function Component({args}) {
  if (args.mode === "session_router") return <SessionRouter args={args} />;
  if (args.mode === "keyboard_navigation") return <KeyboardNavigation />;
  return <Selector args={args} />;
}

const Connected = withStreamlitConnection(Component);
createRoot(document.getElementById("root")).render(<Connected />);
