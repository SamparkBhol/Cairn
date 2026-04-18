import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import metric


def _run_git(args: list[str], cwd: Path) -> str:
    out = subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE)
    return out.strip()


def run_one(*, project: Path, exp_num: int,
            run_command: list[str], grep_pattern: str,
            timeout_s: int) -> dict:
    project = Path(project)
    logs_dir = project / ".new" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    sha = _run_git(["rev-parse", "HEAD"], project)[:7]
    wt = project / ".new" / "worktrees" / f"{exp_num:04d}-{sha}"
    wt.parent.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{exp_num:04d}_{sha}.log"

    started = time.time()
    _run_git(["worktree", "add", "-q", "--detach", str(wt), sha], project)

    try:
        with open(log_path, "wb") as lf:
            try:
                proc = subprocess.Popen(
                    run_command, cwd=wt, stdout=lf, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except FileNotFoundError as e:
                return {
                    "status": "crash", "metric": None, "log_path": str(log_path),
                    "sha": sha, "duration_s": time.time() - started, "err": str(e),
                }
            try:
                rc = proc.wait(timeout=timeout_s)
                status = "ok" if rc == 0 else "crash"
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        pass
                status = "timeout"
                rc = -1

        log_text = log_path.read_text(errors="replace")
        m = metric.parse(log_text, grep_pattern)
        if status == "ok" and m is None:
            status = "crash"

        return {
            "status": status, "metric": m, "log_path": str(log_path),
            "sha": sha, "duration_s": time.time() - started, "rc": rc,
        }
    finally:
        try:
            _run_git(["worktree", "remove", "--force", str(wt)], project)
        except Exception:
            shutil.rmtree(wt, ignore_errors=True)
            try:
                _run_git(["worktree", "prune"], project)
            except Exception:
                pass
