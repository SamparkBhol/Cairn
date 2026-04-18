# Cairn

An autonomous experiment runner that remembers what it tried.

## Plug and play in sixty seconds

```
# install
uv tool install .

# drop Cairn into your project
cd your-project/
cairn init

# start the daemon, profile the baseline
cairn up
cairn baseline

# open your LLM agent (Claude Code, Codex, etc.) and paste:
#   read program.md and let us start
```

That is the whole setup. From here the agent drives. Come back in a few hours; you will have better code, a commit log of every attempt, and a wiki that explains what worked and why.

## What this is

Cairn sits in a project directory. You write a script that prints a number (a loss, an accuracy, a runtime, whatever counts as "better" for your problem). You tell Cairn how much compute you are willing to spend. You point an LLM coding agent at the project.

From that point the agent works on its own. It reads your code, forms a hypothesis, edits a file, commits, and asks Cairn to run the experiment. Cairn runs the script in a throwaway git worktree, extracts the metric, and records the outcome. If the number went the right way the change sticks. If not, it gets reverted and the agent moves on.

Every twenty experiments or so, Cairn pauses the explore loop and asks the agent to sit down and write. Not a status report; an actual wiki. What do we now believe about this problem? Which changes moved the metric? Which did nothing? Which theses are holding up, and which got contradicted? The agent writes markdown, commits, and then goes back to exploring.

When the budget runs out you come back to three things:

1. Code that is better than where you started, in small reviewable commits.
2. A wiki that tells you WHY it is better, with citations back to specific experiments.
3. A full log of every run, including the ones that did not work, so you can reconstruct the agent's thinking.

## Where the name comes from

A cairn is a stack of stones that hikers leave along a trail to mark the way. On featureless terrain (a fogged ridgeline, a glacier, open tundra) cairns are how you find your way back, and how the next person who comes through finds the trail at all.

This tool does the same thing for an agent working through a problem. Every kept experiment is a stone. The wiki is what you see when you look back along the trail. The agent never gets lost in "did I already try this?" because the trail is right there.

## Why this exists

I have been using karpathy's [autoresearch](https://github.com/karpathy/autoresearch) for a few weeks. It works. It hit the same wall after about forty experiments: the agent started re-proposing things it had already tried, the metric had drifted from what I actually cared about, and the log got too long to read. The mechanical parts also had real bugs. Shell injection if your yaml had the wrong character in it. TSV corruption when the agent wrote a tab in a description. No budget cap. No worktree isolation. This is the rewrite I kept meaning to do.

## Features

A complete list of what ships in v0.1.

### Runtime and architecture

* Daemon (`cairnd`) plus thin client (`cairn`) talking over a Unix domain socket. No port collisions, no TCP surface.
* msgpack-framed RPC with a 4-byte big-endian length prefix; single-file schema in `schema.py`.
* SQLite state store in WAL mode; machine-readable source of truth for queue, runs, budget, baseline, and consolidations.
* Supervisor pattern with a pidfile and stale-pid detection via `/proc`.
* Clean graceful shutdown: SIGTERM, ten-second drain, SIGKILL fallback.
* Signal handlers for SIGTERM and SIGINT in the daemon; all in-flight workers get fifteen seconds to finish before the pool is torn down.
* Thread-pool worker execution; pool size from `workers` in your config.
* Automatic unclaim of stale queue entries (over one hour) on daemon startup.
* Live wallclock budget ticker as a separate thread; consumes budget every second so caps apply to uptime, not just experiment count.

### The two-gear loop

* Explore gear: enqueues, runs, and records experiments as fast as your script can run.
* Consolidate gear: pauses the queue and emits a synthesis prompt so the agent can update the wiki.
* Three consolidation triggers: every N experiments (default 20), five consecutive discards, or metric stddev flat over the last ten runs (below `improvement_threshold * 0.1`).
* Manual trigger via `cairn consolidate --force`.
* Sub-budget for consolidation (default ten minutes) so a stuck agent cannot burn the whole session in gear 2.
* Consolidation pass recorded in its own SQLite table with trigger kind, duration, pages touched, and notes.

### Wiki palace (borrowed from MemPalace)

* Three directories on disk: `theses/`, `topics/`, `experiments/`.
* `theses/` pages carry status metadata: `forming`, `supported`, `contradicted`, `abandoned`.
* `topics/` pages synthesize across experiment clusters and cite by experiment filename.
* `experiments/` pages are verbatim per-run records with hypothesis, diff summary, metric, holdout metric, verdict, and backlinks.
* `index.md` is regenerated on demand by `cairn lint` by scanning the three subdirectories.
* `log.md` is an append-only plaintext event log, one line per ingest / query / consolidate / lint, parseable by awk.
* `schema.md` documents the layout once so new agents can orient themselves.
* Path-safety validator rejects wiki writes that escape the palace via `..`, absolute paths, or any traversal; enforced on every call into `wiki.safe_page_path`.
* The wiki is a plain git-tracked directory; `git log wiki/` shows you the agent's thinking over time.

### Metric handling

* Regex-based extraction with `re.MULTILINE` and last-match-wins semantics (so end-of-run prints dominate).
* Statistics helper for mean and sample standard deviation (n-1 denominator).
* Metric `direction` is either `minimize` or `maximize`; enforced by a schema literal type.
* Held-out eval hook (optional): if `holdout` is configured, every Nth kept experiment runs the holdout command in a fresh worktree from the same sha, and the result is parsed with a separate regex.
* Divergence detection: if the primary metric moved in the right direction but the holdout did not move in the same direction, the run is auto-demoted to `discard` with a verdict explaining the divergence.

### Safety and validation

* Shell injection prevention: `run_command` and `holdout.run_command` are split via `shlex.split` at config load and stored as argv lists. Workers spawn with `subprocess.run(args=..., shell=False)`. Shell metacharacters in the yaml become literal argv entries, never a shell string.
* Regex fields (`grep_pattern`, `holdout.grep_pattern`) are `re.compile`'d at config load; invalid regex causes the config to be rejected before the daemon ever starts.
* `forbid_unknown_fields=True` on every msgspec struct; typos in `experiment.yaml` are refused instead of silently ignored.
* Unix domain socket permissioned `0o600`; only the owning uid can connect.
* Baseline noise profile enforced before the explore loop starts: if `stddev > improvement_threshold * 0.5`, the daemon refuses to claim queue items and writes a halt reason explaining what to fix.
* Dirty-tree check in `cairn run`: if `git diff --quiet HEAD` shows uncommitted changes, the command refuses and tells you to commit first. Prevents running experiments against stale commit shas.

### Budget

* Three caps, each a hard stop: `max_experiments`, `max_wallclock_hours`, `max_cost_usd`.
* Per-cap atomic decrement inside a `BEGIN IMMEDIATE` transaction before a worker spawns. Two parallel workers cannot both slip past the final slot.
* `cap <= 0` disables a cap entirely.
* `cairn status` reports used versus cap for every cap, plus any halt reason.

### Worktree isolation

* Every experiment runs in its own `git worktree` under `.cairn/worktrees/<exp_num>-<sha>/`.
* Worktrees are removed automatically on run completion, including on timeout or crash.
* If `git worktree remove` fails for any reason, the directory is force-deleted and `git worktree prune` cleans up the metadata.
* Workers use `start_new_session=True` so they get their own process group; timeout kills the whole group, no orphan children.

### Concurrency

* Configurable `workers` parallelism. Each worker gets its own worktree and its own log file.
* Atomic exp_num allocation through a counter row in `kv` bumped inside the same transaction that claims a queue item.
* Thread-safe SQLite access: `RLock` on the Store plus `check_same_thread=False`; safe to share a connection across daemon, pool, server, and ticker.
* File locks via `fcntl.flock` for any cross-process critical section.

### Project and daemon lifecycle

* `cairn init` scaffolds `experiment.yaml`, `wiki/`, and `.cairn/` in one call. Seeds a git repo only if you are not already inside one.
* `cairn up` starts the daemon detached in the background, with stdout and stderr going to `.cairn/logs/cairnd.log`. Idempotent: if the daemon is already up, it is a no-op.
* `cairn down` sends SIGTERM; waits ten seconds; SIGKILL fallback.
* `cairn status` reads live state from the running daemon.
* State is durable. Kill the daemon mid-experiment, bring it back up, it resumes from SQLite.
* Auto-detect project root: `CAIRN_PROJECT_ROOT` env var is checked first, then the cwd is walked upward for the first directory containing `experiment.yaml`.

### CLI verbs

`init`, `up`, `down`, `status`, `baseline`, `run`, `consolidate`, `lint`, `logs`.

* `run` takes `--hypothesis` / `-H`, `--description` / `-d`, `--priority` / `-p`.
* `consolidate` has `--force` (trigger now) and `--done --notes "..." --pages-touched N` (for the agent to call when the pass is finished).
* `logs` accepts `--exp N` for a specific experiment and `--follow` / `-f` for live tail.

### Persistence

* SQLite WAL mode for simultaneous readers.
* Atomic file writes everywhere: write to a sibling `.tmp` file, fsync, `os.replace`.
* Pidfiles and state files survive restarts; cross-session resume is a no-op.

### Observability

* Per-experiment log at `.cairn/logs/<exp_num>_<sha>.log` containing full stdout and stderr of that run.
* Daemon log at `.cairn/logs/cairnd.log` for everything the daemon itself prints.
* `cairn logs --exp 7` shows the log for experiment seven. `cairn logs --follow` tails the daemon log live.
* `cairn status` prints a terminal-friendly snapshot with uptime, queue size, in-flight count, budget usage, and the last five runs.

### Testing

* Sixty-seven tests across fourteen test files: unit, integration, end-to-end, and security-regression.
* Zero mocking of subprocess, filesystem, or SQLite. Tests run against the real thing.
* End-to-end test spawns a real `cairnd` subprocess against a temporary project, runs real experiments, and verifies SQLite state, wiki artifacts, and budget enforcement.
* Shell-safety regression test parametrizes over five classic shell-injection payloads and asserts they never reach a shell.

### Dependencies

* `msgspec` for schema and IPC framing.
* `PyYAML` for config loading.
* `pytest` and `pytest-timeout` for the test suite.
* Everything else is Python standard library: `sqlite3`, `socket`, `subprocess`, `threading`, `fcntl`, `signal`.

## How it works

Each experiment cycle, step by step:

1. The agent reads the relevant parts of the wiki (`index.md`, a couple of topic pages) to see what has already been tried.
2. The agent picks an idea and writes a one-line hypothesis.
3. The agent edits your code and commits on the experiment branch.
4. The agent calls `cairn run`.
5. `cairnd` creates a fresh `git worktree` at the current HEAD and spawns the `run_command` there with the worktree as its cwd.
6. `cairnd` captures stdout and stderr, extracts the metric via your regex, enforces the timeout, and cleans up the worktree.
7. `cairnd` appends a row to `runs` in SQLite and updates the budget ledger.
8. The agent reads the result, writes a short page under `wiki/experiments/`, and updates any topic or thesis pages this result strengthened or contradicted.
9. Loop.

Every twenty runs (or when five experiments in a row get discarded, or when the metric goes flat), the daemon pauses the queue and emits a consolidation prompt: "here are the last N runs, go refactor the wiki." The agent does one synthesis pass, commits, and the explore loop resumes.

The loop stops when any budget cap is hit: `max_experiments`, `max_wallclock_hours`, or `max_cost_usd`.

## Setup

### Step 1: Install

```
uv tool install .
```

Installs two console scripts on PATH: `cairn` (the client) and `cairnd` (the daemon). You will normally only type `cairn`.

### Step 2: Drop Cairn into your project

```
cd your-project/
cairn init
```

This writes three things into the current directory:

* `experiment.yaml` with a starter config you can edit.
* `wiki/` with an empty palace (`theses/`, `topics/`, `experiments/`, plus `index.md`, `log.md`, `schema.md`).
* `.cairn/` for daemon state. Already in the generated `.gitignore`.

If you are not already in a git repo, Cairn also runs `git init` for you so commits have somewhere to go.

### Step 3: Edit `experiment.yaml`

The minimum fields:

```yaml
run_command: python train.py
grep_pattern: "^val_loss:"
metric:
  name: val_loss
  direction: minimize
budget:
  max_experiments: 100
  max_wallclock_hours: 2
```

The full set of fields (with defaults):

```yaml
run_command: python train.py
grep_pattern: "^val_loss:"

metric:
  name: val_loss
  direction: minimize          # or maximize

workers: 1                     # parallel experiment slots
timeout_seconds: 600           # kill a run that takes longer
consolidate_every: 20          # fire gear 2 after N explore runs
consolidate_budget_minutes: 10 # cap on one consolidation pass
improvement_threshold: 0.005   # minimum metric delta to call it real
session_tag: ""                # optional git branch tag

budget:
  max_experiments: 500
  max_wallclock_hours: 8
  max_cost_usd: 0              # 0 = disabled

holdout:                       # optional anti-Goodhart
  run_command: python eval.py
  grep_pattern: "^holdout:"
  every: 5
```

### Step 4: Verify your script works on its own

```
python train.py
```

If that does not finish and print the metric line on your own machine, Cairn cannot help.

### Step 5: Start the daemon

```
cairn up
```

Cairn forks `cairnd` into the background with logs going to `.cairn/logs/cairnd.log`. The command returns as soon as the daemon's socket is up (usually under a second). If something is wrong, check the log.

### Step 6: Profile the noise

```
cairn baseline
```

Runs the unmodified script three times and records mean and standard deviation. Prints a warning (and refuses the explore loop) if the noise exceeds half your `improvement_threshold`. The fix is usually one line: set a fixed RNG seed in your script.

### Step 7: Launch your agent

Open any coding agent that can read files, edit code, and run shell commands. Paste:

```
Read program.md and let us start.
```

That is the entire prompt. `program.md` is a short contract written for the agent; Cairn already dropped it in step 2.

### Step 8: Watch or walk away

Any time you want a snapshot:

```
cairn status
```

Live tail of the current experiment:

```
cairn logs --follow
```

Full output of a specific experiment:

```
cairn logs --exp 7
```

### Step 9: Stop or resume

```
cairn down         # stop the daemon gracefully
cairn up           # resume any time; state is in SQLite
```

## Plug-and-play: what you do NOT have to do

* No config servers. No accounts. No cloud deployment. No Docker.
* No network egress unless your agent uses one.
* No port configuration. Unix socket only.
* No schema migrations; SQLite is created on first `cairn up`.
* No cleanup required when you stop; worktrees and locks are removed automatically on daemon shutdown.
* No special directory structure for your project. Drop Cairn in anywhere that contains a git repo and a script that prints a number.

## Example configs

### Minimize validation loss

```yaml
run_command: python train.py
grep_pattern: "^val_loss:"
metric:
  name: val_loss
  direction: minimize
workers: 1
timeout_seconds: 600
budget:
  max_experiments: 200
  max_wallclock_hours: 10
```

### Minimize average runtime

```yaml
run_command: python bench.py
grep_pattern: "^avg_time_ms:"
metric:
  name: avg_time_ms
  direction: minimize
timeout_seconds: 60
budget:
  max_experiments: 50
  max_wallclock_hours: 1
```

### Maximize win rate

```yaml
run_command: python play_tournament.py
grep_pattern: "^win_rate:"
metric:
  name: win_rate
  direction: maximize
timeout_seconds: 300
budget:
  max_experiments: 100
  max_wallclock_hours: 8
```

### With a held-out check

```yaml
run_command: python simulate.py --regime train
grep_pattern: "^error:"
metric:
  name: error
  direction: minimize
holdout:
  run_command: python simulate.py --regime eval
  grep_pattern: "^error:"
  every: 5
budget:
  max_experiments: 100
```

The holdout runs every fifth kept experiment. If the train error drops but the eval error does not, the run is discarded with a divergence verdict.

### A non-Python project

`run_command` can be anything that prints the metric line to stdout:

```yaml
run_command: cargo run --release
grep_pattern: "^throughput_ops:"
metric:
  name: throughput_ops
  direction: maximize
```

## Reading the results

Four places to look, in rough order of usefulness.

### The wiki (`wiki/`)

The one you actually want to read. `index.md` catalogs every page. `theses/` shows what the agent currently believes. `topics/` synthesizes across related experiments. `experiments/` has one page per run with hypothesis, metric, and verdict. Because the wiki is git-tracked, `git log wiki/` shows you the agent's thinking over time.

### `cairn status`

Terminal snapshot: uptime, queue size, in-flight runs, budget used for each cap, last five runs with status and metric.

### The SQLite store (`.cairn/state.db`)

The source of truth for machine-readable state. Plot the metric over time:

```
sqlite3 .cairn/state.db \
  "SELECT exp_num, status, metric, description FROM runs ORDER BY exp_num"
```

### Per-run logs (`.cairn/logs/NNNN_<sha>.log`)

Full stdout and stderr of each experiment. Look at these when a run crashed.

## Key concepts

**Metric.** Any number your script prints, in a line your regex can match. Lower-is-better or higher-is-better, set via `metric.direction`.

**Improvement threshold.** The smallest change that counts as "real" progress. If your metric is noisy, raise this. Used both for consolidation triggers (metric gone flat) and for the baseline noise check.

**Budget.** A hard cap. Three kinds: `max_experiments`, `max_wallclock_hours`, `max_cost_usd`. The daemon stops claiming queue items once any cap is hit.

**Worktree.** A fresh checkout of your repo at a specific commit, under `.cairn/worktrees/`. Each experiment gets its own. Torn down automatically.

**The two gears.** Explore runs experiments. Consolidate updates the wiki. Consolidate fires every twenty experiments, on stall, or on demand.

**The palace.** The wiki layout of `theses/`, `topics/`, `experiments/`. Borrowed from MemPalace.

## FAQ

### How do I stop the agent?

Ctrl+C in the agent's terminal, then `cairn down` in yours. Nothing is corrupted. All state is in SQLite and all code changes are in git.

### Can I resume?

Yes. `cairn up` again. The queue, budget ledger, and run history are all in SQLite. Open your agent in the same directory and prompt it to read `program.md`.

### How many experiments per hour?

Depends on your `run_command`. If a run takes five minutes, you get twelve per hour per worker. Set `workers: 2` in `experiment.yaml` for two at a time. Each gets its own worktree.

### The agent keeps re-proposing the same idea

Check that the wiki is being maintained. If `wiki/topics/` is empty, consolidation is not happening. `cairn consolidate --force` triggers a pass manually.

### The metric is not being found

Common causes: the script prints to stderr (check with `cairn logs --exp <N>`); `grep_pattern` does not match the exact line (patterns are Python regex with `re.MULTILINE`); the script crashed before printing. Watch `cairn logs --follow` during a run to see exactly what the script emits.

### A run exceeded the timeout

Cairn sends SIGTERM to the worker's process group, waits five seconds, then SIGKILL. The run is marked `crash`. No orphan processes: `start_new_session=True` gives every worker its own process group.

### Can I use this without an LLM?

Technically yes. `cairn run --hypothesis "..." --description "..."` is a normal CLI call. You can write a shell script that iterates ideas, calls `cairn run`, and inspects `cairn status`. It just is not very useful without an agent, because the point of the loop is to offload ideation.

### Does it work with `uv`, `pip`, `poetry`, raw scripts?

`uv tool install .` is what I use. Anything that can install a Python package with a console script should work. Your experiment's own dependencies are whatever your `run_command` needs.

### Is any of this sent anywhere?

No. Cairn is a local tool. It does not talk to the internet. Your agent (Claude Code, Codex, whatever) may of course talk to its own API; that is on the agent, not on Cairn.

### Can I run multiple Cairn projects on the same machine?

Yes. Each project has its own `.cairn/sock`. Two projects, two sockets, zero collisions.

## What it is not

* Not a cloud orchestrator. Single machine.
* Not a hyperparameter search. The agent does the thinking.
* Not a metrics dashboard. `cairn status` in a second terminal.
* Not tied to any LLM. Works with Claude Code, Codex, plain bash.
* Not for Windows. Uses Unix sockets, flock, process groups.

## Requirements

* Python 3.11 or newer
* `git` on PATH
* A Unix-ish OS (Linux or macOS)
* An LLM coding agent you trust to edit files and run commands in your project directory

## Credit

karpathy's [autoresearch](https://github.com/karpathy/autoresearch), for the original loop shape and the fixed-time-budget discipline.

karpathy's [llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), for the idea that LLMs should incrementally build and maintain a wiki instead of re-deriving knowledge on every query.

[MemPalace](https://github.com/MemPalace/mempalace), for the wings/rooms/drawers layout that shaped `theses/`, `topics/`, `experiments/`.

## License
MIT License

Copyright (c) 2026 Sampark Bhol

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

