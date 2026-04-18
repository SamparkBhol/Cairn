import subprocess

from new import daemon, schema, store


def test_holdout_divergence_demotes_to_discard(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    # primary: reads a count from file, divides metric by count
    (proj / "primary.py").write_text(
        "from pathlib import Path\n"
        "p = Path('count.txt')\n"
        "n = int(p.read_text()) if p.exists() else 1\n"
        "print(f'primary: {1.0/n:.4f}')\n"
    )
    # holdout: always prints 0.5 regardless of the change
    (proj / "holdout.py").write_text(
        "print('holdout: 0.5000')\n"
    )
    (proj / "count.txt").write_text("1")
    (proj / "experiment.yaml").write_text(
        "run_command: python primary.py\n"
        "grep_pattern: \"^primary:\"\n"
        "metric:\n"
        "  name: primary\n"
        "  direction: minimize\n"
        "workers: 1\n"
        "improvement_threshold: 0.01\n"
        "timeout_seconds: 30\n"
        "budget:\n"
        "  max_experiments: 20\n"
        "  max_wallclock_hours: 1\n"
        "  max_cost_usd: 0\n"
        "holdout:\n"
        "  run_command: python holdout.py\n"
        "  grep_pattern: \"^holdout:\"\n"
        "  every: 1\n"
    )
    subprocess.check_call(["git", "init", "-q", "-b", "master"], cwd=proj)
    subprocess.check_call(["git", "config", "user.email", "x@y"], cwd=proj)
    subprocess.check_call(["git", "config", "user.name", "x"], cwd=proj)
    subprocess.check_call(["git", "add", "."], cwd=proj)
    subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=proj)
    monkeypatch.setenv("NEW_PROJECT_ROOT", str(proj))

    d = daemon.Daemon(proj)
    try:
        # first run: n=1 primary=1.0, holdout=0.5. keep.
        qid1 = d.store.enqueue(
            '{"hypothesis":"h","description":"run1"}', priority=0
        )
        item1 = d.store.claim_one("w")
        d._run_worker(item1)

        # bump n in project: primary now 0.5, improvement. holdout still 0.5.
        (proj / "count.txt").write_text("2")
        subprocess.check_call(["git", "add", "."], cwd=proj)
        subprocess.check_call(["git", "commit", "-q", "-m", "n=2"], cwd=proj)
        qid2 = d.store.enqueue(
            '{"hypothesis":"h","description":"run2"}', priority=0
        )
        item2 = d.store.claim_one("w")
        d._run_worker(item2)

        runs = d.store.last_runs(5)
        latest = runs[0]
        assert latest["exp_num"] == 2
        assert latest["status"] == "discard"
        assert "holdout divergence" in latest["verdict"]
    finally:
        d.close()
