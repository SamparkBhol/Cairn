from cairn import budget, store


def test_init_and_state(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    budget.init(s, experiments=100, wallclock_h=1.0, cost_usd=0.0)
    st = budget.state(s)
    assert st["caps"]["experiments"] == 100
    assert st["used"]["experiments"] == 0


def test_consume_experiments(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    budget.init(s, experiments=2, wallclock_h=1.0, cost_usd=0.0)
    assert budget.try_consume(s, "experiments", 1) is True
    assert budget.try_consume(s, "experiments", 1) is True
    assert budget.try_consume(s, "experiments", 1) is False


def test_halt_reason(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    budget.init(s, experiments=1, wallclock_h=1.0, cost_usd=0.0)
    budget.try_consume(s, "experiments", 1)
    assert budget.try_consume(s, "experiments", 1) is False
    assert "experiments cap" in budget.halt_reason(s)


def test_disabled_cap_is_unbounded(tmp_project):
    s = store.open_store(tmp_project / ".cairn" / "state.db")
    budget.init(s, experiments=5, wallclock_h=1.0, cost_usd=0.0)
    for _ in range(10):
        assert budget.try_consume(s, "cost", 1000.0) is True
