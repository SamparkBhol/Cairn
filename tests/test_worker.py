import subprocess
from pathlib import Path

import pytest

from new import worker


@pytest.fixture
def mini_repo(tmp_path):
    subprocess.check_call(["git", "init", "-q", "-b", "master"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.email", "x@y"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "x"], cwd=tmp_path)
    (tmp_path / "run.py").write_text(
        "import sys; print('val_loss:', 0.42); sys.exit(0)\n"
    )
    subprocess.check_call(["git", "add", "."], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=tmp_path)
    return tmp_path


def test_run_extracts_metric(mini_repo):
    r = worker.run_one(
        project=mini_repo,
        exp_num=1,
        run_command=["python", "run.py"],
        grep_pattern=r"^val_loss:",
        timeout_s=15,
    )
    assert r["status"] == "ok"
    assert abs(r["metric"] - 0.42) < 1e-9
    assert Path(r["log_path"]).exists()


def test_run_crash_no_metric(mini_repo):
    (mini_repo / "crash.py").write_text("import sys; sys.exit(1)\n")
    subprocess.check_call(["git", "add", "."], cwd=mini_repo)
    subprocess.check_call(["git", "commit", "-q", "-m", "crash"], cwd=mini_repo)
    r = worker.run_one(
        project=mini_repo, exp_num=2,
        run_command=["python", "crash.py"],
        grep_pattern=r"^val_loss:", timeout_s=15,
    )
    assert r["status"] == "crash"
    assert r["metric"] is None


def test_timeout_kills(mini_repo):
    (mini_repo / "slow.py").write_text("import time; time.sleep(60)\n")
    subprocess.check_call(["git", "add", "."], cwd=mini_repo)
    subprocess.check_call(["git", "commit", "-q", "-m", "slow"], cwd=mini_repo)
    r = worker.run_one(
        project=mini_repo, exp_num=3,
        run_command=["python", "slow.py"],
        grep_pattern=r"^val_loss:", timeout_s=1,
    )
    assert r["status"] == "timeout"


def test_worktree_cleaned_up(mini_repo):
    worker.run_one(
        project=mini_repo, exp_num=4,
        run_command=["python", "run.py"],
        grep_pattern=r"^val_loss:", timeout_s=10,
    )
    out = subprocess.check_output(["git", "worktree", "list"], cwd=mini_repo).decode()
    assert str(mini_repo / ".new" / "worktrees") not in out
