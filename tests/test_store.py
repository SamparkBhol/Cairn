from pathlib import Path

from new import store


def test_open_creates_tables(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    cur = s.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {r[0] for r in cur}
    assert {"queue", "runs", "budget", "kv", "consolidations", "baseline"} <= names
    s.close()


def test_kv_set_get(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.kv_set("foo", "1")
    assert s.kv_get("foo") == "1"
    assert s.kv_get("missing") is None
    s.close()


def test_counter_increment(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    assert s.next_exp_num() == 1
    assert s.next_exp_num() == 2
    assert s.next_exp_num() == 3
    s.close()


def test_wal_mode(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    mode = s.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    s.close()
