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


class Req(msgspec.Struct):
    type: str
    payload: bytes = b""


class Resp(msgspec.Struct):
    ok: bool
    payload: bytes = b""
    error: str = ""


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
    uptime_s: float = 0.0


_mp = msgspec.msgpack


def encode(obj) -> bytes:
    return _mp.encode(obj)


def decode(data: bytes, typ):
    return _mp.decode(data, type=typ)
