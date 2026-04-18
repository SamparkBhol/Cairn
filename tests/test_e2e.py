import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture
def toy_project(tmp_path):
    src = Path(__file__).parent.parent / "examples" / "toy-sort"
    dst = tmp_path / "proj"
    shutil.copytree(src, dst)
    subprocess.check_call(["git", "init", "-q", "-b", "master"], cwd=dst)
    subprocess.check_call(["git", "config", "user.email", "x@y"], cwd=dst)
    subprocess.check_call(["git", "config", "user.name", "x"], cwd=dst)
    subprocess.check_call(["git", "add", "."], cwd=dst)
    subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=dst)
    return dst


def _new(project, *argv, timeout=20) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["CAIRN_PROJECT_ROOT"] = str(project)
    return subprocess.run(
        [sys.executable, "-m", "cairn", *argv],
        cwd=project, capture_output=True, text=True, env=env, timeout=timeout,
    )


@pytest.mark.timeout(90)
def test_init_up_run_down(toy_project):
    assert _new(toy_project, "init").returncode == 0
    up = _new(toy_project, "up")
    assert up.returncode == 0
    try:
        st = _new(toy_project, "status")
        assert "up" in st.stdout

        r = _new(toy_project, "run", "-H", "baseline", "-d", "first run")
        assert r.returncode == 0
        for _ in range(60):
            st = _new(toy_project, "status")
            if "last runs" in st.stdout and "0001" in st.stdout:
                break
            time.sleep(0.5)
        assert "0001" in st.stdout
    finally:
        _new(toy_project, "down")


@pytest.mark.timeout(120)
def test_multiple_runs_halt_on_budget(toy_project):
    y = toy_project / "experiment.yaml"
    y.write_text(y.read_text().replace("max_experiments: 20",
                                        "max_experiments: 2"))
    subprocess.check_call(["git", "add", "experiment.yaml"], cwd=toy_project)
    subprocess.check_call(["git", "commit", "-q", "-m", "cap 2"], cwd=toy_project)
    _new(toy_project, "init")
    _new(toy_project, "up")
    try:
        for _ in range(5):
            _new(toy_project, "run", "-d", "x")
        for _ in range(60):
            st = _new(toy_project, "status")
            if "halted" in st.stdout or "experiments cap reached" in st.stdout:
                break
            time.sleep(0.5)
        assert "halted" in st.stdout or "cap reached" in st.stdout
    finally:
        _new(toy_project, "down")
