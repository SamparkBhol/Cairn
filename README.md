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
