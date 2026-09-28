# Development reliability handoff — 2026-09-28

## Scope

Reconciled the interrupted workflow fixes onto main `4f00caa`, preserving its workshop expansion and custom-item rules. No simulation authority, save schema, world-generation version, or RNG contract changed.

- `run_ci_check.py` now enforces the deadline through both process completion and output-pipe closure; it no longer waits forever after early EOF or an exited parent with a live child. Output buffering is bounded and chunked, including newline-free output. Non-finite limits are rejected.
- `process_tree.py` cleans up POSIX process groups and Windows Job objects. A gated Windows launcher joins the Job before the command can spawn descendants. Startup containment errors fail clearly.
- Diagnostic self-tests cover both reproduced hangs, descendant cleanup, output draining, invalid limits and startup failure. Expected failures are captured so they do not emit misleading GitHub error annotations.
- Soaks default to one seed-year, require explicit opt-in for longer runs, report initialization/simulation/serialization liveness on stderr, and close the database on failure. Simulation advancement itself is unchanged.
- Preflight detects incomplete/stale snapshots, wrong repository/branch, dirty checkouts and missing rendering-test dependencies. It is a before-edit check, not a reason to discard current work.
- AGENTS/DEVELOPMENT now specify one main-based work unit/writer, targeted bounded tests, explicit release validation and an approximately 25-minute session budget. No new development branch was created.
- Full validation now discovers the entire suite once instead of a selected subset; packaging uses the Git commit rather than miscellaneous workspace files. The fast gate retains workshop regressions and adds Linux process cleanup checks alongside Windows coverage.
- Fixed stale sprite-canvas assertions against the documented mixed character roster and supported 32/64px craftable formats; assertions still check transparency, rendering and uniqueness. Isolated two pure tests from unnecessary world-generation fixtures, closed image handles, fixed a discovery-only test import, and stopped a UI test from overwriting a tracked screenshot.

## Validation performed locally

- Compileall and workflow YAML parsing passed.
- 20 focused workflow/render/asset tests passed in 23.1 seconds.
- 82 storage, interaction, economy, activity, profession, workshop and logistics tests passed in 2.7 seconds.
- All five workshop expansion tests passed after reconciling the newer main.
- Final diagnostic regression rerun covers the expected-error annotation cleanup.
- Content audit passed: 150 items, 82 recipes, 35 structures. Visual audit passed: 669 unique assets.
- One-year/full-policy/one-seed soak passed with no invariant errors, including initialization heartbeat output (15.7 seconds end-to-end).
- A broader discovery run reported no assertion failure before its 180-second budget expired during Dev31 exploration setup/execution. The runner terminated the process tree and returned 124. This was a bounded scan, **not a full release-suite pass**.

## Branch disposition and remaining work

`BRANCH_AUDIT.md` records all 64 non-main tips at the baseline. One is ancestry-contained; 63 diverge. Divergence is not proof that a feature is missing. Workshop PR #67 is now closed and its implementation is on main. No open PRs remained at the audit.

Remote branch deletion is unavailable through the configured repository tools. No branch was deleted or bulk-merged; divergent work is preserved. Only `dev38-natural-container-art-variants` is ancestry-proven eligible for later cleanup after a fresh check. The main-first rule is a development contract, not a server-side branch-creation restriction.

Next release hardening should run the manual complete suite and profile remaining repeated Simulation fixture construction. Do not increase timeouts blindly, treat a timeout as a pass, or claim that repository fixes diagnose ChatGPT service/UI freezes. Windows Job-object behavior is covered by the automatic Windows gate; Linux behavior was exercised locally.
