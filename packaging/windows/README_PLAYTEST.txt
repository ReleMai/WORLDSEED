WORLDSEED WINDOWS TEST BUILD (October 2026)
=======================================

Requirements: Windows 10/11 x64. No Python or pip installation required.

1. DO NOT use GitHub's green Code > Download ZIP button; that ZIP is only
   source code and contains NO WORLDSEED.exe.
   Instead open https://github.com/ReleMai/WORLDSEED/actions/workflows/windows-playtest.yml
   and download the WORLDSEED-Windows-x64-EXECUTABLE-... artifact under the
   latest successful Windows Playtest Executable workflow run.
   The artifact is a large download because it includes all game graphics.
2. Extract the entire Actions artifact ZIP into a NEW EMPTY folder (such as Documents/WORLDSEED_Test).
   IMPORTANT: Keep WORLDSEED.exe and the _internal directory together.
3. Double-click PLAY_WORLDSEED_TEST.bat to start recording a session.
4. Create or load a world, explore, interact, craft, save and try several
   menus. For performance issues, note where you saw delays.
5. When you exit (or after a crash), the launcher generates a local ZIP.
   You can also run EXPORT_WORLDSEED_REPORT.bat at any time after a session.
6. Open playtest_reports and attach the newest
   WORLDSEED_PLAYTEST_REPORT_YYYYMMDD_HHMMSS.zip to your WORLDSEED
   ChatGPT conversation. Ask for session/performance/crash analysis.

The report includes: game/build version, coarse Windows details, timing
percentiles for rendering and game systems, slow stage summaries, actions,
approximate progress and exception categories. The latest game session's
existing debug log is summarized into the ZIP.

Privacy:
 - No network transmission or automatic ChatGPT/GitHub upload.
 - No save files, player names, raw typed keys, raw debug JSONL, exception
   messages, tracebacks or local file paths in the default report.
 - Review the report.json inside the ZIP before sending it.
 - Reports remain on your computer unless YOU attach them in chat.
 - Original debug logs and saves are retained in the local folder for recovery.
 - If deeper investigation requires a saved game or raw error log, you can
   inspect and send it separately.

Folders in the extracted Windows build:
 saves/              your persistent worlds (never included in report)
 logs/               full local session logs (not included in report ZIP)
 playtest_reports/    sanitized ZIPs for sharing

Known limits:
 - A diagnostic report is not a recording or screen capture.
 - The game uses the current Pygame software display renderer.
 - 1080p high-load and higher-resolution GPU hardware acceptance remain open.
 - If the game never reaches a playable scene, send the sanitized ZIP and
   tell ChatGPT what you saw. Do not share private save files automatically.

Build identity is in PLAYTEST_BUILD.json.
