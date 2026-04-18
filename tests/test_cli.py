import os
import subprocess
import sys
from pathlib import Path


def _new(project, *argv, timeout=20):
    env = os.environ.copy()
    env["CAIRN_PROJECT_ROOT"] = str(project)
    return subprocess.run(
        [sys.executable, "-m", "cairn", *argv],
        cwd=project, capture_output=True, text=True, env=env, timeout=timeout,
    )


def test_init_scaffolds(tmp_project):
    p = _new(tmp_project, "init")
    assert p.returncode == 0, p.stderr
    assert (tmp_project / "experiment.yaml").exists()
    assert (tmp_project / "wiki" / "index.md").exists()


def test_status_when_no_daemon(tmp_project):
    p = _new(tmp_project, "status")
    assert p.returncode == 0
    assert "down" in p.stdout.lower() or "not running" in p.stdout.lower()
