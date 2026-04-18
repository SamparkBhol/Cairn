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


def test_enqueue_and_size(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    assert s.queue_size() == 0
    qid = s.enqueue('{"h":"x"}', priority=0)
    assert qid == 1
    assert s.queue_size() == 1
    s.close()


def test_claim_respects_fifo_and_priority(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.enqueue('{"h":"a"}', priority=0)
    s.enqueue('{"h":"b"}', priority=5)
    s.enqueue('{"h":"c"}', priority=0)
    first = s.claim_one("w1")
    assert '"b"' in first["spec"]
    second = s.claim_one("w1")
    assert '"a"' in second["spec"]
    s.close()


def test_claim_empty_returns_none(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    assert s.claim_one("w1") is None
    s.close()


def test_unclaim_stale(tmp_project):
    import time
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.enqueue('{"h":"x"}', priority=0)
    item = s.claim_one("w1")
    s.conn.execute("UPDATE queue SET claimed_at = ? WHERE id=?",
                   (time.time() - 3600, item["id"]))
    n = s.unclaim_stale(older_than_s=60)
    assert n == 1
    again = s.claim_one("w1")
    assert again is not None
    s.close()
