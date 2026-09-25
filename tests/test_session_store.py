from src.session_store import create_session_id, prune_expired_sessions, restore_session, save_session


def test_session_id_uses_stable_hash_and_timestamp():
    first = create_session_id("file.csv:abc", now=100.0)
    second = create_session_id("file.csv:abc", now=101.0)
    assert first.split("-")[0] == second.split("-")[0]
    assert first.endswith("100000")
    assert second.endswith("101000")


def test_session_restore_and_expiry_are_isolated_copies():
    store = {}
    snapshot = {"custom_labels": ["UNIT_ID"]}
    save_session(store, "key", snapshot, now=10.0)
    snapshot["custom_labels"].append("CHANGED")
    restored = restore_session(store, "key", ttl_seconds=900, now=20.0)
    assert restored == {"custom_labels": ["UNIT_ID"]}
    restored["custom_labels"].append("LOCAL")
    assert store["key"]["snapshot"] == {"custom_labels": ["UNIT_ID"]}
    assert restore_session(store, "key", ttl_seconds=900, now=921.0) is None


def test_prune_expired_sessions():
    store = {
        "fresh": {"last_activity": 950.0, "snapshot": {}},
        "old": {"last_activity": 0.0, "snapshot": {}},
    }
    assert prune_expired_sessions(store, ttl_seconds=100, now=1000.0) == ["old"]
    assert list(store) == ["fresh"]
