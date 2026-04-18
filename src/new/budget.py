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
        if cap <= 0:
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
