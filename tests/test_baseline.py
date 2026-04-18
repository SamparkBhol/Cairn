import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from new import store


def _new(project, *argv, timeout=30):
    env = os.environ.copy()
    env["NEW_PROJECT_ROOT"] = str(project)
    return subprocess.run(
        [sys.executable, "-m", "new", *argv],
        cwd=project, capture_output=True, text=True, env=env, timeout=timeout,
    )


@pytest.fixture
def noisy_project(tmp_path):
    dst = tmp_path / "proj"
    dst.mkdir()
    (dst / "main.py").write_text(
        "import random, os\n"
        "random.seed(int(os.environ.get('PYTHONHASHSEED', '0') or '0')"
        " + int(1000 * random.random() + 1))\n"
        "print(f'metric: {random.random():.4f}')\n"
    )
    (dst / "experiment.yaml").write_text(
        "run_command: python main.py\n"
        "grep_pattern: \"^metric:\"\n"
        "metric:\n"
        "  name: metric\n"
        "  direction: minimize\n"
        "workers: 1\n"
        "improvement_threshold: 0.01\n"
        "timeout_seconds: 30\n"
        "budget:\n"
        "  max_experiments: 20\n"
        "  max_wallclock_hours: 1\n"
        "  max_cost_usd: 0\n"
    )
    subprocess.check_call(["git", "init", "-q", "-b", "master"], cwd=dst)
    subprocess.check_call(["git", "config", "user.email", "x@y"], cwd=dst)
    subprocess.check_call(["git", "config", "user.name", "x"], cwd=dst)
    subprocess.check_call(["git", "add", "."], cwd=dst)
    subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=dst)
    return dst


def test_baseline_saves_and_halts_on_noise(noisy_project):
    # run baseline 3x — each draws a random number in [0,1). stddev will be
    # large relative to 0.01.
    r = _new(noisy_project, "baseline", "--n", "3")
    assert r.returncode == 0, r.stderr
    # check baseline row exists
    s = store.open_store(noisy_project / ".new" / "state.db")
    try:
        b = s.get_baseline()
        assert b is not None
        assert b["n"] == 3
        # noisy: stddev should vastly exceed improvement_threshold * 0.5
        assert b["stddev"] > 0.005
    finally:
        s.close()

    # bring daemon up and observe halt
    up = _new(noisy_project, "up")
    assert up.returncode == 0
    try:
        for _ in range(30):
            st = _new(noisy_project, "status")
            if "baseline stddev" in st.stdout or "baseline stddev" in (st.stderr or ""):
                break
            time.sleep(0.2)
        assert "baseline stddev" in st.stdout
    finally:
        _new(noisy_project, "down")
