# WORLDSEED CI diagnostics handoff

Scope: `.github/workflows/{fast-gate,test-build}.yml`, `tools/run_ci_check.py`, visual/image audits, and coast audit progress. These are tooling changes; there are no gameplay, persistence, RNG, or UI changes.

- Each check logs its name, exact command, elapsed time, child PID, and final exit code. A running check emits a heartbeat every 30 seconds. A per-check deadline stops its process tree and returns exit code 124. GitHub step summaries collect the results; a failure also emits a GitHub error annotation.
- Unit tests run verbose so the last test name and failing assertion are visible. Content and visual audits, and the two hydrology audits, run as separate steps so an earlier failure cannot be hidden by a later success.
- `audit_visuals.py` decodes each unique referenced image fully and reports one actionable path for damaged files, invalid modes, and dimensions. No image is modified by the audit.
- Coast and river-mouth audits print the current seed before work and sample counts afterward. Their existing coverage thresholds remain intact.
- The install step performs one dependency resolution and has a three-minute timeout. The automatic gate retains its ten-minute job limit; the manual full gate retains its 45-minute limit.

Validation: `python -m unittest -v tests.test_ci_diagnostics`; `python -m compileall -q tools tests`; YAML parse and step consistency checks. The Windows workflow run is the integration check after publication.

Limitation: a job waiting for a GitHub-hosted runner cannot emit process heartbeats until a runner starts. The queued/running status in Actions remains the source of truth for that wait.
