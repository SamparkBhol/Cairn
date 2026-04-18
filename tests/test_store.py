from pathlib import Path

from cairn import store


def test_open_creates_tables(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    cur = s.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {r[0] for r in cur}
    assert {"queue", "runs", "budget", "kv", "consolidations", "baseline"} <= names
    s.close()


def test_kv_set_get(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    s.kv_set("foo", "1")
    assert s.kv_get("foo") == "1"
    assert s.kv_get("missing") is None
    s.close()


def test_counter_increment(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    assert s.next_exp_num() == 1
    assert s.next_exp_num() == 2
    assert s.next_exp_num() == 3
    s.close()


def test_wal_mode(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    mode = s.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    s.close()


def test_enqueue_and_size(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    assert s.queue_size() == 0
    qid = s.enqueue('{"h":"x"}', priority=0)
    assert qid == 1
    assert s.queue_size() == 1
    s.close()


def test_claim_respects_fifo_and_priority(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    s.enqueue('{"h":"a"}', priority=0)
    s.enqueue('{"h":"b"}', priority=5)
    s.enqueue('{"h":"c"}', priority=0)
    first = s.claim_one("w1")
    assert '"b"' in first["spec"]
    second = s.claim_one("w1")
    assert '"a"' in second["spec"]
    s.close()


def test_claim_empty_returns_none(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    assert s.claim_one("w1") is None
    s.close()


def test_unclaim_stale(tmp_project):
    import time
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    s.enqueue('{"h":"x"}', priority=0)
    item = s.claim_one("w1")
    s.conn.execute("UPDATE queue SET claimed_at = ? WHERE id=?",
                   (time.time() - 3600, item["id"]))
    n = s.unclaim_stale(older_than_s=60)
    assert n == 1
    again = s.claim_one("w1")
    assert again is not None
    s.close()


def test_insert_and_list_runs(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    s.insert_run(
        exp_num=1, commit_sha="abc", metric=0.5, metric_holdout=None,
        status="keep", duration_s=1.0, started_at=1.0, ended_at=2.0,
        hypothesis="h", verdict="v", description="d",
        log_path="logs/1.log", wiki_refs=[],
    )
    rows = s.last_runs(5)
    assert len(rows) == 1
    assert rows[0]["exp_num"] == 1
    s.close()


def test_runs_since_last_consolidation(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    for i in range(3):
        s.insert_run(
            exp_num=i + 1, commit_sha="x", metric=0.0, metric_holdout=None,
            status="keep", duration_s=0.0, started_at=float(i + 1), ended_at=float(i + 1),
            hypothesis="", verdict="", description="",
            log_path="", wiki_refs=[],
        )
    assert s.runs_since_last_consolidation() == 3
    s.record_consolidation_start("count")
    s.record_consolidation_end(pages_touched=2, notes="ok")
    assert s.runs_since_last_consolidation() == 0
    s.close()


def test_baseline_persist(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    s.save_baseline(n=3, mean=0.5, stddev=0.01, samples=[0.49, 0.50, 0.51])
    b = s.get_baseline()
    assert b["n"] == 3 and abs(b["mean"] - 0.5) < 1e-9
    s.close()
