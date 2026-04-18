from new import consolidate, store


def _insert_runs(s, metrics, status="keep"):
    for i, m in enumerate(metrics, start=1):
        s.insert_run(
            exp_num=i, commit_sha="x", metric=m, metric_holdout=None,
            status=status, duration_s=0.0, started_at=float(i),
            ended_at=float(i), hypothesis="", verdict="",
            description="", log_path="", wiki_refs=[],
        )


def test_trigger_by_count(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    _insert_runs(s, [0.1] * 20)
    assert consolidate.should_fire(s, every=20, thresh=0.01)[0] == "count"


def test_trigger_by_stall_discards(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    _insert_runs(s, [0.1] * 5, status="discard")
    assert consolidate.should_fire(s, every=50, thresh=0.01)[0] == "stall"


def test_trigger_by_flat_metric(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    _insert_runs(s, [0.5] * 10)
    assert consolidate.should_fire(s, every=50, thresh=0.01)[0] == "stall"


def test_no_trigger_when_healthy(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    _insert_runs(s, [0.5, 0.4, 0.3, 0.25, 0.2])
    assert consolidate.should_fire(s, every=50, thresh=0.01) is None


def test_prompt_includes_recent(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    _insert_runs(s, [0.9, 0.8, 0.7])
    prompt = consolidate.build_prompt(s, wiki_root=tmp_project / "wiki",
                                       reason="manual")
    assert "recent runs" in prompt.lower()
    assert "0.9" in prompt or "0.8" in prompt or "0.7" in prompt
