import argparse
import concurrent.futures
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

from . import budget, consolidate, rpc, schema, store, util, wiki, worker


def _load_cfg(project: Path) -> schema.Config:
    text = (project / "experiment.yaml").read_text()
    return schema.load_config_yaml(text)


class Daemon:
    def __init__(self, project: Path):
        self.project = Path(project)
        self.cfg = _load_cfg(self.project)
        self.store = store.open_store(self.project / ".cairn" / "state.db")
        self.stop = threading.Event()
        self.in_flight = 0
        self.in_flight_lock = threading.Lock()
        self.pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, self.cfg.workers)
        )
        budget.init(
            self.store,
            experiments=self.cfg.budget.max_experiments,
            wallclock_h=self.cfg.budget.max_wallclock_hours,
            cost_usd=self.cfg.budget.max_cost_usd,
        )
        self.store.unclaim_stale(older_than_s=3600)
        self._check_baseline_vs_threshold()
        self.started_at = time.time()
        wiki.init(self.project / "wiki")

    def _check_baseline_vs_threshold(self) -> None:
        b = self.store.get_baseline()
        if not b:
            return
        if b["stddev"] > self.cfg.improvement_threshold * 0.5:
            msg = (
                f"baseline stddev {b['stddev']:.4f} exceeds half of "
                f"improvement_threshold {self.cfg.improvement_threshold:.4f}. "
                f"fix rng seed or raise threshold or run `cairn baseline --n 10`."
            )
            self.store.kv_set("halted_baseline", msg)
        else:
            self.store.conn.execute("DELETE FROM kv WHERE k='halted_baseline'")

    def handle(self, req: schema.Req) -> schema.Resp:
        try:
            data = json.loads(req.payload or b"{}")
        except Exception:
            data = {}
        if req.type == "status":
            return schema.Resp(ok=True, payload=self._status())
        if req.type == "run":
            return self._enqueue(data)
        if req.type == "consolidate":
            return self._consolidate(data)
        if req.type == "lint":
            wiki.rebuild_index(self.project / "wiki")
            return schema.Resp(ok=True, payload=b"{}")
        if req.type == "health":
            return schema.Resp(ok=True, payload=b"{}")
        if req.type == "down":
            self.stop.set()
            return schema.Resp(ok=True, payload=b"{}")
        if req.type == "baseline_save":
            return self._baseline_save(data)
        return schema.Resp(ok=False, error=f"unknown rpc type: {req.type}")

    def _status(self) -> bytes:
        st = budget.state(self.store)
        last_rows = self.store.last_runs(5)
        last_records = [
            schema.RunRecord(
                exp_num=r["exp_num"], commit_sha=r["commit_sha"],
                metric=r["metric"], metric_holdout=r["metric_holdout"],
                status=r["status"], duration_s=r["duration_s"],
                started_at=r["started_at"], ended_at=r["ended_at"],
                hypothesis=r["hypothesis"] or "", verdict=r["verdict"] or "",
                description=r["description"] or "", log_path=r["log_path"] or "",
                wiki_refs=r["wiki_refs"],
            ) for r in last_rows
        ]
        halt = budget.halt_reason(self.store)
        baseline_halt = self.store.kv_get("halted_baseline")
        if baseline_halt and not halt:
            halt = baseline_halt
        report = schema.StatusReport(
            daemon_up=True,
            queue_size=self.store.queue_size(),
            in_flight=self.in_flight,
            budget_used=st["used"],
            budget_cap=st["caps"],
            last_runs=last_records,
            halted_reason=halt,
            uptime_s=time.time() - self.started_at,
        )
        return schema.encode(report)

    def _enqueue(self, data: dict) -> schema.Resp:
        hyp = data.get("hypothesis", "")
        desc = data.get("description", "")
        pri = int(data.get("priority", 0))
        qid = self.store.enqueue(json.dumps(
            {"hypothesis": hyp, "description": desc}
        ), priority=pri)
        return schema.Resp(ok=True, payload=json.dumps({"queue_id": qid}).encode())

    def _consolidate(self, data: dict) -> schema.Resp:
        if data.get("done"):
            self.store.record_consolidation_end(
                pages_touched=int(data.get("pages_touched", 0)),
                notes=data.get("notes", ""),
            )
            self.store.kv_set("consolidating", "0")
            wiki.append_log(self.project / "wiki", "consolidate",
                            f"done: {data.get('notes', '')[:80]}")
            return schema.Resp(ok=True, payload=b"{}")
        reason = data.get("reason", "manual")
        self.store.record_consolidation_start(reason)
        self.store.kv_set("consolidating", "1")
        prompt = consolidate.build_prompt(
            self.store, wiki_root=self.project / "wiki", reason=reason,
        )
        return schema.Resp(ok=True, payload=prompt.encode())

    def _baseline_save(self, data: dict) -> schema.Resp:
        n = int(data.get("n", 0))
        mean = float(data.get("mean", 0.0))
        sd = float(data.get("stddev", 0.0))
        samples = data.get("samples", [])
        self.store.save_baseline(n=n, mean=mean, stddev=sd, samples=samples)
        self._check_baseline_vs_threshold()
        return schema.Resp(ok=True, payload=b"{}")

    def loop(self) -> None:
        tick_thread = threading.Thread(target=self._wallclock_tick, daemon=True)
        tick_thread.start()

        futures = []
        while not self.stop.is_set():
            if budget.halt_reason(self.store):
                time.sleep(0.5)
                continue
            if self.store.kv_get("halted_baseline"):
                time.sleep(0.5)
                continue
            if self.store.kv_get("consolidating") == "1":
                time.sleep(0.25)
                continue
            item = self.store.claim_one(worker=f"pool-{os.getpid()}")
            if item is None:
                self._maybe_trigger_consolidation()
                time.sleep(0.25)
                continue
            if not budget.try_consume(self.store, "experiments", 1):
                self.store.dequeue(item["id"])
                continue
            futures = [f for f in futures if not f.done()]
            fut = self.pool.submit(self._run_worker, item)
            futures.append(fut)

        for f in futures:
            try:
                f.result(timeout=15)
            except Exception:
                pass

    def _run_worker(self, item: dict) -> None:
        with self.in_flight_lock:
            self.in_flight += 1
        try:
            exp_num = self.store.next_exp_num()
            spec = json.loads(item["spec"])
            started = time.time()
            r = worker.run_one(
                project=self.project,
                exp_num=exp_num,
                run_command=self.cfg.run_command,
                grep_pattern=self.cfg.grep_pattern,
                timeout_s=self.cfg.timeout_seconds,
            )
            ended = time.time()
            if r["status"] == "ok" and r["metric"] is not None:
                status = "keep"
            elif r["status"] in ("crash", "timeout"):
                status = "crash"
            else:
                status = "skip"
            verdict = ""
            m_holdout = None
            if status == "keep" and self.cfg.holdout is not None:
                if exp_num % self.cfg.holdout.every == 0:
                    hr = worker.run_one(
                        project=self.project,
                        exp_num=exp_num,
                        run_command=self.cfg.holdout.run_command,
                        grep_pattern=self.cfg.holdout.grep_pattern,
                        timeout_s=self.cfg.timeout_seconds,
                    )
                    m_holdout = hr["metric"]
                    if m_holdout is not None and r["metric"] is not None:
                        prev = self._prev_primary_metric(exp_num)
                        if prev is not None:
                            primary_moved_right = _moved_right(
                                prev, r["metric"], self.cfg.metric.direction
                            )
                            prev_h = self._prev_holdout_metric(exp_num)
                            if prev_h is not None and primary_moved_right:
                                holdout_moved_right = _moved_right(
                                    prev_h, m_holdout, self.cfg.metric.direction
                                )
                                if not holdout_moved_right:
                                    status = "discard"
                                    verdict = (
                                        f"holdout divergence: primary={r['metric']:.4f}, "
                                        f"holdout={m_holdout:.4f}"
                                    )
            self.store.insert_run(
                exp_num=exp_num, commit_sha=r["sha"],
                metric=r["metric"], metric_holdout=m_holdout,
                status=status, duration_s=r["duration_s"],
                started_at=started, ended_at=ended,
                hypothesis=spec.get("hypothesis", ""),
                verdict=verdict,
                description=spec.get("description", ""),
                log_path=r["log_path"], wiki_refs=[],
            )
            self.store.dequeue(item["id"])
        finally:
            with self.in_flight_lock:
                self.in_flight -= 1

    def _prev_primary_metric(self, exp_num: int) -> float | None:
        r = self.store.conn.execute(
            "SELECT metric FROM runs WHERE status='keep' AND exp_num<? "
            "ORDER BY exp_num DESC LIMIT 1", (exp_num,),
        ).fetchone()
        return r[0] if r and r[0] is not None else None

    def _prev_holdout_metric(self, exp_num: int) -> float | None:
        r = self.store.conn.execute(
            "SELECT metric_holdout FROM runs "
            "WHERE metric_holdout IS NOT NULL AND exp_num<? "
            "ORDER BY exp_num DESC LIMIT 1", (exp_num,),
        ).fetchone()
        return r[0] if r else None

    def _maybe_trigger_consolidation(self) -> None:
        fire = consolidate.should_fire(
            self.store,
            every=self.cfg.consolidate_every,
            thresh=self.cfg.improvement_threshold,
        )
        if fire and self.store.kv_get("consolidating") != "1":
            kind, why = fire
            self.store.kv_set("consolidating", "1")
            self.store.record_consolidation_start(kind)
            wiki.append_log(self.project / "wiki", "consolidate",
                            f"pending: {kind} ({why})")

    def _wallclock_tick(self) -> None:
        last = time.time()
        while not self.stop.is_set():
            time.sleep(1.0)
            now = time.time()
            budget.try_consume(self.store, "wallclock", now - last)
            last = now

    def close(self) -> None:
        self.pool.shutdown(wait=False)
        self.store.close()


def _moved_right(prev: float, cur: float, direction: str) -> bool:
    if direction == "minimize":
        return cur < prev
    return cur > prev


def main():
    ap = argparse.ArgumentParser(prog="cairnd")
    ap.add_argument("--project", default=".", help="project dir (default: cwd)")
    ap.add_argument("--foreground", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    os.environ["CAIRN_PROJECT_ROOT"] = str(project)
    pf = project / ".cairn" / "cairnd.pid"
    pf.parent.mkdir(parents=True, exist_ok=True)

    old = util.read_pidfile(pf)
    if util.pid_alive(old):
        print(f"cairnd already running (pid {old})", file=sys.stderr)
        sys.exit(1)
    util.write_pidfile(pf, os.getpid())

    d = Daemon(project)

    def _sig(_s, _f):
        d.stop.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    server_stop = threading.Event()
    server_thread = threading.Thread(
        target=rpc.serve,
        args=(project / ".cairn" / "sock", d.handle, server_stop),
        daemon=True,
    )
    server_thread.start()

    try:
        d.loop()
    finally:
        server_stop.set()
        try:
            rpc.call(project / ".cairn" / "sock", schema.Req(type="__quit__"),
                     timeout=1.0)
        except Exception:
            pass
        server_thread.join(timeout=2.0)
        d.close()
        try:
            pf.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
