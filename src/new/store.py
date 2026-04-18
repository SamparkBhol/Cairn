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


def open_store(path: Path) -> Store:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return Store(conn)
