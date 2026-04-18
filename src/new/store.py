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
            self.conn.execute("BEGIN IMMEDIATE")
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

    def update_run(self, exp_num: int, **fields) -> None:
        if not fields:
            return
        import json
        cols = []
        vals = []
        for k, v in fields.items():
            if k == "wiki_refs":
                v = json.dumps(v)
            cols.append(f"{k}=?")
            vals.append(v)
        vals.append(exp_num)
        with self.conn:
            self.conn.execute(
                f"UPDATE runs SET {', '.join(cols)} WHERE exp_num=?",
                vals,
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


def open_store(path: Path) -> Store:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return Store(conn)
