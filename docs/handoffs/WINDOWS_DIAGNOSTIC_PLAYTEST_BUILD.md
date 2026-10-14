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
