import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import metric, rpc, schema, store, util, wiki, worker


_TEMPLATE_YAML = """\
run_command: python train.py
grep_pattern: "^val_loss:"
metric:
  name: val_loss
  direction: minimize
workers: 1
consolidate_every: 20
improvement_threshold: 0.005
timeout_seconds: 600
budget:
  max_experiments: 500
  max_wallclock_hours: 8
  max_cost_usd: 0
"""


def _project() -> Path:
    return util.find_project_root()


def _sock() -> Path:
    return _project() / ".new" / "sock"


def _pid() -> Path:
    return _project() / ".new" / "newd.pid"


def _daemon_up() -> bool:
    pid = util.read_pidfile(_pid())
    return util.pid_alive(pid) and _sock().exists()


def cmd_init(args):
    proj = _project()
    (proj / ".new").mkdir(exist_ok=True)
    yf = proj / "experiment.yaml"
    # a zero-byte file from conftest or stale touch should be replaced
    if not yf.exists() or yf.stat().st_size == 0:
        yf.write_text(_TEMPLATE_YAML)
    wiki.init(proj / "wiki")
    if not (proj / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "master"], cwd=proj, check=False)
    print(f"initialized {proj}")


def cmd_up(args):
    if _daemon_up():
        print("newd already up")
        return
    proj = _project()
    log = proj / ".new" / "logs" / "newd.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(
        [sys.executable, "-m", "new.daemon", "--project", str(proj)],
        stdout=open(log, "ab"), stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(60):
        if _sock().exists():
            print(f"newd up (pid {p.pid})")
            return
        time.sleep(0.05)
    print("newd did not come up — see .new/logs/newd.log", file=sys.stderr)
    sys.exit(1)


def cmd_down(args):
    pid = util.read_pidfile(_pid())
    if not util.pid_alive(pid):
        print("newd not running")
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"signal error: {e}", file=sys.stderr)
        sys.exit(1)
    for _ in range(100):
        if not util.pid_alive(pid):
            print("stopped")
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    print("killed")


def cmd_status(args):
    if not _daemon_up():
        print("newd: down")
        return
    resp = rpc.call(_sock(), schema.Req(type="status"))
    if not resp.ok:
        print(f"error: {resp.error}", file=sys.stderr)
        sys.exit(1)
    report = schema.decode(resp.payload, schema.StatusReport)
    print(f"newd: up (uptime {report.uptime_s:.0f}s)")
    print(f"queue: {report.queue_size}  in-flight: {report.in_flight}")
    print("budget:")
    for k, cap in report.budget_cap.items():
        used = report.budget_used.get(k, 0)
        cap_s = "disabled" if cap <= 0 else f"{cap:.2f}"
        print(f"  {k}: {used:.2f} / {cap_s}")
    if report.halted_reason:
        print(f"halted: {report.halted_reason}")
    print("last runs:")
    for r in report.last_runs:
        m = "-" if r.metric is None else f"{r.metric:.4f}"
        print(f"  {r.exp_num:04d} [{r.status:7}] {m}  {r.description}")


def cmd_run(args):
    if not _daemon_up():
        print("newd not running; run `new up`", file=sys.stderr)
        sys.exit(1)
    if (_project() / ".git").exists():
        r = subprocess.run(
            ["git", "diff", "--quiet", "HEAD"], cwd=_project()
        )
        if r.returncode != 0:
            print("tree is dirty; commit your change first", file=sys.stderr)
            sys.exit(1)
    payload = json.dumps({
        "hypothesis": args.hypothesis or "",
        "description": args.description or "",
        "priority": args.priority,
    }).encode()
    resp = rpc.call(_sock(), schema.Req(type="run", payload=payload))
    if not resp.ok:
        print(f"error: {resp.error}", file=sys.stderr)
        sys.exit(1)
    print(resp.payload.decode())


def cmd_consolidate(args):
    if not _daemon_up():
        print("newd not running", file=sys.stderr)
        sys.exit(1)
    if args.done:
        payload = json.dumps({
            "done": True, "notes": args.notes or "",
            "pages_touched": args.pages_touched,
        }).encode()
    else:
        payload = json.dumps({"reason": "manual" if args.force else "auto"}).encode()
    resp = rpc.call(_sock(), schema.Req(type="consolidate", payload=payload))
    if not resp.ok:
        print(f"error: {resp.error}", file=sys.stderr)
        sys.exit(1)
    print(resp.payload.decode())


def cmd_lint(args):
    if not _daemon_up():
        wiki.rebuild_index(_project() / "wiki")
        print("wiki/index.md rebuilt (offline)")
        return
    rpc.call(_sock(), schema.Req(type="lint"))
    print("wiki/index.md rebuilt")


def cmd_logs(args):
    logs = _project() / ".new" / "logs"
    if args.exp is not None:
        matches = sorted(logs.glob(f"{args.exp:04d}_*.log"))
        if not matches:
            print(f"no log for exp {args.exp}", file=sys.stderr)
            sys.exit(1)
        print(matches[-1].read_text())
        return
    newd = logs / "newd.log"
    if not newd.exists():
        print("no daemon log yet", file=sys.stderr)
        return
    if args.follow:
        subprocess.call(["tail", "-F", str(newd)])
    else:
        print(newd.read_text())


def cmd_baseline(args):
    proj = _project()
    # require a committed repo so worktree add works
    if not (proj / ".git").exists():
        print("no git repo; run `new init` first", file=sys.stderr)
        sys.exit(1)
    cfg_text = (proj / "experiment.yaml").read_text()
    cfg = schema.load_config_yaml(cfg_text)
    n = args.n
    samples = []
    for i in range(n):
        r = worker.run_one(
            project=proj,
            exp_num=10000 + i,
            run_command=cfg.run_command,
            grep_pattern=cfg.grep_pattern,
            timeout_s=cfg.timeout_seconds,
        )
        if r["metric"] is None:
            print(f"baseline run {i+1}/{n} failed: {r.get('status')}", file=sys.stderr)
            sys.exit(1)
        samples.append(r["metric"])
        print(f"baseline {i+1}/{n}: {r['metric']:.6f}")
    mean, sd = metric.stats(samples)
    # persist via daemon RPC if up, else directly to store
    if _daemon_up():
        payload = json.dumps(
            {"n": n, "mean": mean, "stddev": sd, "samples": samples}
        ).encode()
        rpc.call(_sock(), schema.Req(type="baseline_save", payload=payload))
    else:
        s = store.open_store(proj / ".new" / "state.db")
        try:
            s.save_baseline(n=n, mean=mean, stddev=sd, samples=samples)
        finally:
            s.close()
    print(f"mean={mean:.6f} stddev={sd:.6f}")
    if sd > cfg.improvement_threshold * 0.5:
        print(
            f"warning: stddev {sd:.4f} > improvement_threshold "
            f"{cfg.improvement_threshold:.4f} * 0.5. "
            f"fix rng seed, raise threshold, or run with --n 10.",
            file=sys.stderr,
        )


def main():
    ap = argparse.ArgumentParser(prog="new")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("up").set_defaults(fn=cmd_up)
    sub.add_parser("down").set_defaults(fn=cmd_down)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    r = sub.add_parser("run")
    r.add_argument("--hypothesis", "-H", default="")
    r.add_argument("--description", "-d", default="")
    r.add_argument("--priority", "-p", type=int, default=0)
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("consolidate")
    c.add_argument("--force", action="store_true")
    c.add_argument("--done", action="store_true")
    c.add_argument("--notes", default="")
    c.add_argument("--pages-touched", type=int, default=0)
    c.set_defaults(fn=cmd_consolidate)

    sub.add_parser("lint").set_defaults(fn=cmd_lint)

    l = sub.add_parser("logs")
    l.add_argument("--exp", type=int)
    l.add_argument("--follow", "-f", action="store_true")
    l.set_defaults(fn=cmd_logs)

    b = sub.add_parser("baseline")
    b.add_argument("--n", type=int, default=3)
    b.set_defaults(fn=cmd_baseline)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
