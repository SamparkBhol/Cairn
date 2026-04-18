from pathlib import Path

from . import metric


def should_fire(s, *, every: int, thresh: float) -> tuple[str, str] | None:
    n = s.runs_since_last_consolidation()
    if n >= every:
        return ("count", f"{n} runs since last consolidation")
    last = s.last_runs(10)
    if not last:
        return None
    discards = 0
    for r in last:
        if r["status"] == "discard":
            discards += 1
        else:
            break
    if discards >= 5:
        return ("stall", f"{discards} consecutive discards")
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
