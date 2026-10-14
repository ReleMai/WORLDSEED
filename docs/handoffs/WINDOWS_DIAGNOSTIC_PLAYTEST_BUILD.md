# Windows playable diagnostic build — October 2026

A self-contained **Windows x64 PyInstaller one-directory bundle** is built by
`.github/workflows/windows-playtest.yml` on changes to the packaging/instrumentation,
or manual dispatch. The *real bundled exe* is smoke-tested for content, pygame
availability and offline report export before publication. This is a playtest,
not the full release candidate or long-session GPU acceptance certification.

## What testers do

Download the Actions artifact `WORLDSEED-Windows-Playtest-<commit>`, extract the
whole folder, and double-click `PLAY_WORLDSEED_TEST.bat`. The wrapper starts
`WORLDSEED.exe --window --profile-runtime` from the extracted directory,
capturing console output only in `logs/`. On normal exit or crash it runs
`WORLDSEED.exe --playtest-export` to create a local ZIP. Manual export uses
`EXPORT_WORLDSEED_REPORT.bat`. Both launchers are included in the artifact.

The existing `SessionDebugLog` records commands, UI navigation, saves,
preparation stages, and exceptions. Pygame frame stages and other runtime
stages are already measured by the bounded `RuntimeProfiler`. `run_game`
now flushes a final `profile_summary` event and latest turn/game minute
in a `finally` block. Python crashes still write a separate local traceback;
native process aborts can leave less evidence.

The reporter summarizes only the **most recently created log**. It includes
type names, timing percentiles, event-category counts, gameplay turn and
minute, coarse environment and build metadata, and namespaced stage identifiers.
It does not copy raw user keys, messages, save data, local paths, full tracebacks
or exception text. Report generation has no network code or upload action.
Only the tester can attach the generated ZIP to their conversation. No screenshots,
microphone data or gameplay recordings are collected.

## Development and QA boundaries

The Windows packaging job is triggered only for the changed paths listed in
its workflow, not on every development commit. Ordinary Fast Gate smoke and
targeted `tests.test_playtest_report` remain independent. The one-directory
EXE is checked on a GitHub-hosted Windows x64 runner; actual interactive
playtesting and image parity still require player Windows hardware.

A complete test session should include: start/load, exploration/zoom/resizing,
NPC and building interaction, inventory and crafting menus, a save/reload,
and a clean quit. Share the ZIP here and a short human explanation of any
visible clipping, responsiveness, crashes, or graphical oddities.

No save-schema, worldgen, RNG, content or simulation-authority change is part
of this instrumentation package.


## October 14 — Source ZIP versus Windows executable artifact fix

Observed issue: `PLAY_WORLDSEED_TEST.bat` was committed at the repository
root. GitHub's source archive therefore displayed a launcher but had **no**
`WORLDSEED.exe`. GitHub Actions *did* build, smoke-test and upload the
Windows PyInstaller executable successfully (artifact 11906091211, run
38585957463, 443733208 bytes). The user's extracted layout matches the
source ZIP, not the Windows binary artifact; a local extraction cannot be
verified remotely.

Correction: move the Windows launcher, exporter and player README into
`packaging/windows/` so they only become *root files* of the compiled
distribution through the Windows builder. Remove the misleading source-root
launchers, add upfront README download guidance and make launcher errors
identify source-vs-binary confusion explicitly.

The Windows release workflow now checks the actual `WORLDSEED.exe`, the
PyInstaller `_internal` directory, readable launchers and build identity
**after** frozen-executable smoke tests and **before** artifact upload. It
writes a small verifiable `BUNDLE_VERIFY.json` manifest with the EXE size
and SHA256, and uses a clearly named `WORLDSEED-Windows-x64-EXECUTABLE`
artifact. The game and save format remain unchanged.

## October 14 — Real Windows report triage (follow-up)

A player-supplied sanitized Windows x64 report (dev64, approximately 18.5 minutes
elapsed) recorded 735 realtime advances, 19 save events, no Python exceptions,
and a one-time active-region initialization with region planning 1962.84 ms and
settlement physicalization 3928.13 ms. These are single startup/activation samples,
**not evidence of continuous movement stuttering**. The recent-event tail included
saves at 192–217 ms and a final 450.63 ms checkpoint; the pre-fix report omitted
all-session save percentiles and backend phase attribution. No FPS/input sample
was present: `runtime_profile` was empty and no `profile_summary` event was logged.

Remediation: enable bounded RuntimeProfiler automatically only for frozen Windows
playtest executables with a valid `PLAYTEST_BUILD.json` identity, including when
players open WORLDSEED.exe directly. The default source/release runtime stays
opt-in. The privacy-safe exporter now explicitly distinguishes absent profiling
from sampled timing and aggregates all bounded save events into autosave versus
full-checkpoint percentiles and counts above 100 ms. This is instrumentation
and triage, **not** a claimed reduction to save or settlement generation time.

Next Windows pass: repeat normal gameplay and inspect `render.frame`,
`save.capture`, `save.database`, `save.commit` and region-preparation stages.
Do not change autosave durability or pre-generation contracts until timings
identify the responsible phase. No game/save/schema/worldgen changes.

## October 14 — Windows NPC portrait crash and engine M2 activation follow-up

A player-submitted second sanitized report from Windows build `a264757`
reported a `ValueError` after an NPC portrait interaction. Source audit
confirmed the popup requested 520 pixels at desktop resolutions even though
`PortraitComposer.render` accepts at most 512. Centralize the portrait size
limit at 520 pixels to match the existing popup; add an actual 1920x1080 pygame popup regression.
The sanitized report does not include the raw traceback, so retain that
qualification in incident summaries.

Native observations (one short session, no hardware certification):
- `render.frame` 848 samples: p50 20.81 ms, p95 40.50 ms, p99 94.94 ms;
  6 lifetime frames >100ms, worst 396.81 ms.
- Region activation: `region_plans` 2096.14 ms,
  `settlement_physicalization` 5077.91 ms; both are single samples.
- Autosave: 155.24 ms total, of which `save.commit` 141.22 ms;
  `save.capture` 10.87 ms; preserve SQLite transaction durability.

Next M2 engine slice instruments settlement materialization separately into
plan, access-repair, cell-index and route stages. Region-road border post
projection also reuses one exact route-cell membership set rather than
rebuilding it for every post. This is a bounded complexity improvement, not
proof of a particular speedup. No saved geography, RNG, persistence contract,
procedural art identity or world-authority changes.

Next priority after validation is GPU-backed alpha/light/weather composition
and moving-camera cache misses at 1080p+, with software fallback and approved
pixel parity, then a Windows repeat using the same seed and world.
