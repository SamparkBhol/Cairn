# agent contract

you drive the loop. the daemon runs experiments, tracks budget, and
maintains a wiki with you.

## setup

1. `cairn status` — is the daemon up?
2. if not: `cairn up`.
3. if first session in this repo: `cairn baseline` — runs the unmodified
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
5. `cairn run -H "<hypothesis>" -d "<short description>"`.
6. watch: `cairn status`, or `cairn logs --exp <N> --follow`.
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
- you ran `cairn consolidate --force`.

when fired:
1. `cairn consolidate` — emits a prompt on stdout with the recent runs.
2. read the wiki in full. it should not take long if you've been
   maintaining it.
3. for each recent run, make sure an `experiments/<N>-<slug>.md` exists.
4. refactor topic pages as needed — remove duplication, strengthen or
   weaken claims based on new evidence, flag contradictions.
5. if a new thesis has emerged, create `theses/<slug>.md`.
6. `git commit -m "wiki: consolidate after exp <N>"`.
7. `cairn consolidate --done --notes "..." --pages-touched <k>`.

## stopping

the daemon stops itself when any budget cap is hit. check with
`cairn status`. if you want to pause manually, `cairn down`.

## rules

- never write to `.cairn/`. the daemon owns it.
- never edit another experiment's page. history is append-only.
- never `git reset --hard` the experiment branch. if a run was bad,
  the next experiment reverts.
- if the daemon crashes, `cairn up` again. it resumes from sqlite.
- if you don't know what to do, re-read this file.
