# Reliable WORLDSEED development

`ReleMai/WORLDSEED` on `main` is the only integration baseline. Work on one coherent task at a time. Historical branches are parked references; do not resume them or create a fresh branch per chat. See `BRANCH_AUDIT.md` before attempting to recover old work.

## Start with a complete baseline

With normally configured Git credentials, clone into a new empty directory:

```sh
git clone https://github.com/ReleMai/WORLDSEED.git WORLDSEED
cd WORLDSEED
git fetch origin main
git rev-parse origin/main
python tools/workspace_preflight.py --expected-head <the-SHA-just-returned>
```

For an existing checkout, inspect `git status` first. Preserve uncommitted work; never reset or overwrite it. A clean `main` may use `git pull --ff-only origin main`. If branches have diverged, stop and reconcile the specific work. Detached CI checkouts are supported by the preflight check.

In connector-only environments, use a complete archive/snapshot pinned to the freshly read GitHub main commit. Verify it against the GitHub recursive tree (not a local file count). The manifest format is `{"commit":"<SHA>","tree":[{"path":"relative/path","sha":"Git-blob-SHA"}]}` and must contain every blob from that remote tree:

```sh
python tools/workspace_preflight.py --snapshot ../source-tree.json --expected-head <fresh-remote-main-SHA>
```

Preflight runs before edits, so expected modifications made during the current task should not be mistaken for a stale baseline afterward. Do not commit the temporary manifest. Missing files or hash mismatches must be resolved before testing; an old RC13 attachment must not silently replace current main.

Install validation dependencies with `python -m pip install -e . "Pillow>=10,<12"`, then add `--check-dependencies` to preflight. A test run that silently skips pygame checks is not graphical validation. Do not confuse missing dependencies with a game regression.

## Validation levels

1. Development: compile changed Python and run affected tests through `run_ci_check.py`, normally with a 180-second budget. Add regression tests for the reproduced fault. Run content/visual audits when changing assets or data.
2. Integration: publish one coherent commit and inspect the automatic fast gate. It includes Windows coverage and Linux process-runner regression checks.
3. Release: deliberately run the manual full-validation workflow. It discovers the entire suite once, with a hard deadline, then runs the physical-world audits. Long soaks require `--allow-long-run`; do not launch them during routine UI/art changes.

`soak_matrix.py --json` keeps result rows on stdout and progress on stderr. Its default is one seed and one simulated year. Wrap it with `run_ci_check.py` to enforce a wall-clock deadline; the runner combines output for human-readable logs.

## Publish and hand off

Re-read remote main, reconcile any concurrent change, and publish code, tests and documentation together. Include the commit, tests actually run, remaining limitations and the next dependency. Avoid a second commit just for generated documentation. Routine work requires no extra development branch.

Remote branch deletion is separate from feature integration. Only delete a branch after proving its tip is an ancestor of current main, checking open PRs, and recording the tip SHA for recovery. Divergence is not proof that its feature is missing: squash/copy integration can preserve content without preserving ancestry. Never bulk-merge old branches.
