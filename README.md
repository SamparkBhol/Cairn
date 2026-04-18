  # cairn

  An autonomous experiment runner that remembers what it tried.

  ## What this is

  cairn sits in a project directory. You write a script that prints a number (a loss, an accuracy, a runtime, whatever counts as "better" for your problem).
   You tell cairn how much compute you are willing to spend. You point an LLM coding agent at the project.

  From that point the agent works on its own. It reads your code, forms a hypothesis, edits a file, commits, and asks cairn to run the experiment. cairn
  runs the script in a throwaway git worktree, extracts the metric, and records the outcome. If the number went the right way the change sticks. If not, it
  gets reverted and the agent moves on.

  Every twenty experiments or so, cairn pauses the explore loop and asks the agent to sit down and write. Not a status report; an actual wiki. What do we
  now believe about this problem? Which changes moved the metric? Which did nothing? Which theses are holding up, and which got contradicted? The agent
  writes markdown, commits, and then goes back to exploring.

  When the budget runs out you come back to three things:

  1. Code that is better than where you started, in small reviewable commits.
  2. A wiki that tells you WHY it is better, with citations back to specific experiments.
  3. A full log of every run, including the ones that did not work, so you can reconstruct the agent's thinking.

  ## Where the name comes from

  A cairn is a stack of stones that hikers leave along a trail to mark the way. On featureless terrain (a fogged ridgeline, a glacier, open tundra) cairns
  are how you find your way back, and how the next person who comes through finds the trail at all.

  This tool does the same thing for an agent working through a problem. Every kept experiment is a stone. The wiki is what you see when you look back along
  the trail. The agent never gets lost in "did I already try this?" because the trail is right there.

  ## Why this exists

  I have been using karpathy's [autoresearch](https://github.com/karpathy/autoresearch) for a few weeks. It works. It hit the same wall after about forty
  experiments: the agent started re-proposing things it had already tried, the metric had drifted from what I actually cared about, and the log got too long
   to read. The mechanical parts also had real bugs. Shell injection if your yaml had the wrong character in it. TSV corruption when the agent wrote a tab
  in a description. No budget cap. No worktree isolation. This is the rewrite I kept meaning to do.

  ## How it is different

  ### Two gears

  A fast explore loop runs experiments. A slow consolidate pass updates a wiki. The wiki is the agent's memory, and it compounds. Inspired by karpathy's
  [llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

  ### Palace layout

  The wiki is three directories. `theses/` holds high-level beliefs the agent is converging on. `topics/` holds thematic clusters of experiments (learning
  rate, architecture width, regularization). `experiments/` holds verbatim per-run pages. Borrowed from [MemPalace](https://github.com/MemPalace/mempalace).

  ### Held-out eval

  An optional sidecar command the agent cannot see. Every few kept experiments, cairn runs the holdout and compares. If the primary metric improved but the
  holdout did not, the run is discarded with a divergence verdict. Cheap defense against metric gaming.

  ### Daemon plus client

  A long-lived `cairnd` owns everything that can go wrong: queue, budget, worktrees, metric parsing, sqlite state. A thin `cairn` CLI is what you type. They
   talk over a Unix domain socket, so there is no port to conflict with.

  ### Worktree per run

  Every experiment runs in its own `git worktree`. A run that crashes, loops, or fills the disk can be torn down without touching your main checkout.

  ### Budget caps that actually cap

  The daemon does an atomic decrement in sqlite before spawning a worker. Two parallel experiments cannot both slip past the final budget slot.

  ### Baseline noise check

  Before the loop starts, cairn runs the unmodified script three times and measures the metric's standard deviation. If the noise is more than half your
  improvement threshold, it refuses to start and tells you why. This prevents the failure mode where the agent "improves" the score by riding random
  variance for a dozen cycles.

  ## How it works

  Each experiment cycle, step by step:

  1. The agent reads the relevant parts of the wiki (`index.md`, a couple of topic pages) to see what has already been tried.
  2. The agent picks an idea and writes a one-line hypothesis.
  3. The agent edits your code and commits on the experiment branch.
  4. The agent calls `cairn run`.
  5. `cairnd` creates a fresh `git worktree` at the current HEAD and spawns the `run_command` there with the worktree as its cwd.
  6. `cairnd` captures stdout and stderr, extracts the metric via your regex, enforces the timeout, and cleans up the worktree.
  7. `cairnd` appends a row to `runs` in sqlite and updates the budget ledger.
  8. The agent reads the result, writes a short page under `wiki/experiments/`, and updates any topic or thesis pages this result strengthened or
  contradicted.
  9. Loop.

  Every twenty runs (or when five experiments in a row get discarded, or when the metric goes flat), the daemon pauses the queue and emits a consolidation
  prompt: "here are the last N runs, go refactor the wiki." The agent does one synthesis pass, commits, and the explore loop resumes.

  The loop stops when any budget cap is hit: `max_experiments`, `max_wallclock_hours`, or (if you wire it up) `max_cost_usd`.

  ## Quick start

  ### Step 1: Install

  ```
  uv tool install .
  ```

  ### Step 2: Set up your project

  ```
  cd your-project/
  cairn init
  ```

  This writes three things into the project:

  * `experiment.yaml` for your config
  * `wiki/` with an empty palace layout
  * `.cairn/` for daemon state (gitignored)

  ### Step 3: Fill in `experiment.yaml`

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

  Make sure `run_command` prints a line matching `grep_pattern` on a successful run. If your script prints `val_loss: 0.1234` somewhere near the end, the
  pattern `^val_loss:` will find it.

  ### Step 4: Verify your script runs manually

  ```
  python train.py
  ```

  If that does not finish and print the metric on your own machine, cairn cannot help you.

  ### Step 5: Start the daemon

  ```
  cairn up
  ```

  ### Step 6: Run a baseline

  ```
  cairn baseline
  ```

  This runs the unmodified script three times and prints the mean and standard deviation. If the stddev is more than half your improvement threshold, the
  daemon will refuse to start the explore loop until you fix the noise (usually by setting a fixed RNG seed in your script).

  ### Step 7: Launch your agent

  Open a coding agent (Claude Code, Codex, anything that can read files, edit code, and run shell commands). Prompt:

  ```
  Read program.md and let us start.
  ```

  The agent takes over. Leave it.

  ### Step 8: Watch or walk away

  In another terminal:

  ```
  cairn status                     # queue, budget, last 5 runs
  cairn logs --exp 7 --follow      # live stdout of experiment 7
  ```

  ### Step 9: Stop when you want

  ```
  cairn down
  ```

  Resume any time with `cairn up`. Queue and state persist in sqlite.

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

  There are four places to look, in rough order of usefulness.

  ### The wiki (`wiki/`)

  This is the one you actually want to read. `index.md` catalogs every page. `theses/` shows what the agent currently believes. `topics/` synthesizes across
   related experiments. `experiments/` has one page per run with hypothesis, metric, and verdict. The wiki is git-tracked, so `git log wiki/` shows you the
  agent's thinking over time.

  ### `cairn status`

  Terminal snapshot: queue size, in-flight runs, budget used, last five runs with status and metric.

  ### The sqlite store (`.cairn/state.db`)

  The source of truth for machine-readable state. If you like SQL:

  ```
  sqlite3 .cairn/state.db \
    "SELECT exp_num, status, metric, description FROM runs ORDER BY exp_num"
  ```

  Useful for plotting the metric over time.

  ### Per-run logs (`.cairn/logs/NNNN_<sha>.log`)

  Full stdout and stderr of each experiment. Not committed. Look at these when a run crashes.

  ## Key concepts

  **Metric.** Any number your script prints, in a line your regex can match. Lower-is-better or higher-is-better, set via `metric.direction`.

  **Improvement threshold.** The smallest change that counts as "real" progress. If your metric is noisy, raise this. Used both for consolidation triggers
  (metric gone flat) and for the baseline noise check.

  **Budget.** A hard cap. Three kinds: `max_experiments`, `max_wallclock_hours`, `max_cost_usd`. The daemon stops claiming queue items once any cap is hit.

  **Worktree.** A fresh checkout of your repo at a specific commit, living under `.cairn/worktrees/`. Each experiment gets its own. Torn down automatically.

  **The two gears.** Explore runs experiments. Consolidate updates the wiki. Consolidate fires every twenty experiments, on stall, or on demand.

  **The palace.** The wiki layout of `theses/`, `topics/`, `experiments/`. Borrowed from MemPalace.

  ## FAQ

  ### How do I stop the agent?

  Ctrl+C in the agent's terminal, then `cairn down` in yours. Nothing is corrupted. All state is in sqlite and all code changes are in git.

  ### Can I resume?

  Yes. `cairn up` again. The queue, budget ledger, and run history are all in sqlite. Open your agent in the same directory and prompt it to read
  `program.md`.

  ### How many experiments per hour?

  Depends on your `run_command`. If a run takes five minutes, you get twelve per hour per worker. Set `workers: 2` in `experiment.yaml` for two at a time.
  Each gets its own worktree.

  ### The agent keeps re-proposing the same idea

  Check that the wiki is being maintained. If `wiki/topics/` is empty, consolidation is not happening. `cairn consolidate --force` triggers a pass manually.

  ### The metric is not being found

  Common causes: the script prints to stderr (check with `cairn logs --exp <N>`); `grep_pattern` does not match the exact line (patterns are Python regex
  with `re.MULTILINE`); the script crashed before printing.

  ### A run exceeded the timeout

  cairn sends SIGTERM to the worker's process group, waits five seconds, then SIGKILL. The run is marked `crash`. No orphan processes:
  `start_new_session=True` gives every worker its own process group.

  ### Can I use this without an LLM?

  Technically yes. `cairn run --hypothesis "..." --description "..."` is a normal CLI call. You can write a shell script that iterates ideas, calls `cairn
  run`, and inspects `cairn status`. It just is not very useful without an agent, because the point of the loop is to offload ideation.

  ### Does it work with `uv`, `pip`, `poetry`, raw scripts?

  `uv tool install .` is what I use. Anything that can install a Python package with a console script should work. Your experiment's own dependencies are
  whatever your `run_command` needs.

  ### Is any of this sent anywhere?

  No. cairn is a local tool. It does not talk to the internet. Your agent (Claude Code, Codex, whatever) may of course talk to its own API; that is on the
  agent, not on cairn.

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

  karpathy's [llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), for the idea that LLMs should incrementally build and
  maintain a wiki instead of re-deriving knowledge on every query.

  [MemPalace](https://github.com/MemPalace/mempalace), for the wings/rooms/drawers layout that shaped `theses/`, `topics/`, `experiments/`.

  ## License

  MIT.
