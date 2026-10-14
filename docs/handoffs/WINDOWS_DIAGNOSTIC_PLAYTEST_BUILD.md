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
