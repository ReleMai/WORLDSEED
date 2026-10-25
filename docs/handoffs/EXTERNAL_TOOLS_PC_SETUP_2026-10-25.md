# External tools: Windows local readiness

Date: 2026-10-25. Baseline: freshly fetched canonical main
`5940c26f17c52e2733e13d77e64000be789ac5a6` (also the foundation reference).
This is a dated local setup record, not a promise about future account state.

## Checkout and environment

The original `D:/Codex Project/wsLIVING` had 1,160 changed/untracked paths and
was preserved. Setup uses a complete managed detached checkout at
`C:/Users/relem/.codex/worktrees/external-tools-setup/wsLIVING`. Workspace preflight
passed against the fetched SHA before edits and again with dependency checks.
Keep this checkout: its registered docs vault, virtualenv and ignored pilots are
in use. Relocate them deliberately before archiving it.

Installed development environment: Python 3.14.2, Git 2.45.1.windows.1,
pygame-ce 2.5.8, ModernGL 5.11.0, glcontext 2.5.0, Pillow 11.3.0.
A dedicated `.venv` avoids changing global packages. The GPU extra resolved to
versions satisfying the repository bounds; native wheels built successfully.

```powershell
Set-Location 'C:/Users/relem/.codex/worktrees/external-tools-setup/wsLIVING'
# Recreate only if the environment is missing:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[gpu]" "Pillow>=10,<12"
# Normal use needs no activation or execution-policy change:
.\.venv\Scripts\python.exe tools/external_assets.py doctor
```

## Workflow status

| Workflow | Status | Evidence / remaining action |
| --- | --- | --- |
| Obsidian + Smart Connections | Operational and verified | Obsidian 1.14.5 and Smart Connections Core 4.7.2 enabled through Community Plugins. Local indexing completed; a ranked result opened the original WORLDSEED source. START_HERE is open in reading mode. |
| Scenario | Waiting on a paid API plan | User signed in and confirmed that API access requires a plan. Pilot/offline plan ready; account model access remains unverified. |
| Meshy + Blender | Waiting on Meshy API subscription; Blender operational and verified | User confirmed a separate API subscription is required to expose a Meshy key. Blender 5.2.3 LTS background bake passed. |
| ElevenLabs Sound Effects | Operational and verified for account access and offline planning | Replacement key encrypted with current-user Windows DPAPI, reload succeeded, authenticated read-only GET passed. No sound generation or quality trial performed. |
| Context7 | Operational and verified | Codex OAuth login succeeded; authenticated tool discovery succeeded; both target libraries resolved and returned docs. Reload the client/new chat to expose newly added tools. |

### Project memory

Use this checkout's `docs/` directly. Open `development/memory/START_HERE.md`
with Ctrl+O and bookmark it using the note's menu. An ignored convenience launcher
is `scratch/readiness/Open-WORLDSEED-Memory.ps1`; it opens that note through the
registered Obsidian URI. A Start Menu shortcut named WORLDSEED Project Memory
opens the same note. No documents are copied into a second knowledge store.

Smart Connections Core 4.7.2 was installed and enabled through Obsidian's
Community Plugins browser on the follow-up setup. Smart Environment 3.1.1 uses
the default local transformers model `TaylorAI/bge-micro-v2` (384 dimensions,
512-token input limit). Initial import and embedding completed: 130 source
records plus 751 selected blocks, 881 embedded items. Small/template blocks
below configured eligibility thresholds are intentionally not all embedded.

The first plugin startup left the renderer windows blank. Restarting the
Obsidian instance restored the vault; the cause is unconfirmed. No GPU flags,
plugin binaries, cloud embeddings or separate model service were changed.

Retrieval test passed in the actual Obsidian Connections view: with
`handoffs/EXTERNAL_TOOLS_FOUNDATION_2026-10-25.md` open, the highest related result
was `development/EXTERNAL_TOOLS.md`, displayed score 0.87. Opening that result
showed the original source, its 2026-10-25 decision date, offline-authoring scope
and five-tool table. The result was inspected rather than treated as authority
on similarity alone. Evidence remains ignored at
`scratch/readiness/smart-connections-index-evidence.json`. START_HERE was left in
reading mode to reduce accidental editing. Accepted decisions remain in Git.

### Context7 and version coverage

Detected coding client: Codex CLI 0.164.0-alpha.11.1 and the Codex desktop app.
Merged only this section into existing user config; pre-existing settings were
preserved, with a timestamped local backup:

```toml
[mcp_servers.context7]
url = "https://mcp.context7.com/mcp/oauth"
```

`codex mcp login context7` completed. Authenticated Codex app-server discovery
reported OAuth, Context7 4.4.3, `resolve-library-id` and `query-docs`, no tool error.
Read-only queries succeeded for `/pygame-community/pygame-ce` and
`/moderngl/moderngl`. Neither advertised exact installed-version IDs and the
returned citations target GitHub main. Exact version coverage remains unverified.
Use official [pygame-ce docs](https://pyga.me/docs/) and
[ModernGL docs](https://moderngl.readthedocs.io/), checking tagged
[pygame-ce 2.5.8 source](https://github.com/pygame-community/pygame-ce/blob/2.5.8/buildconfig/stubs/pygame/display.pyi)
and [ModernGL 5.11.0 source](https://github.com/moderngl/moderngl/blob/5.11.0/docs/reference/moderngl.rst)
when matching installed APIs matters. Raw files at both tagged sources returned HTTP 200.

Local evidence: `scratch/readiness/CONTEXT7_LOCAL_SETUP.md`,
`context7-codex-status.json` and `context7-query-evidence.json` in that directory.
No API key was placed in configuration. OAuth credentials stay in client storage.

### Blender pipeline

Installed executable:
`C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`.
A locally authored asymmetric column GLB produced eight 256px RGBA CPU Cycles
views at 64 samples. Alpha corners/edges, unclipped bounds, source/output SHA256
and ground anchors passed; anchors differed from `(0.5, 0.25)` by under 0.000001.
The installed executable separately passed a bounded four-view 128px/16-sample
bake in 7.5 seconds; its `system-verification.json` passed the same checks.
Rendered views from both bakes were visually inspected. The manifest retains normalization,
camera transforms, Blender version, recipe and fixture license; status remains
`unreviewed`. This verifies the pipeline, not production art quality.

The installed directory was added to user PATH and a Start Menu shortcut;
new terminals inherit that PATH. A redundant temporary portable build and this
task's downloads were removed after installed-system verification.

Fixture, bakes and verification live under ignored
`scratch/blender-pipeline-20261025/`. Use a new empty output for each bake:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python-exit-code 1 --python tools/blender_bake_sprites.py -- --source scratch/blender-pipeline-20261025/disposable-column.glb --output scratch/bakes/next-fixture --views 8 --size 256 --license-note 'Locally authored disposable fixture; pipeline test only'
```

### Asset accounts and first trial

Doctor and environment checks found no Scenario key/secret, Meshy key or ElevenLabs
key at process, user or machine scope. Provider sign-ins were subsequently completed by the user. Scenario requires a
plan and Meshy a separate API subscription, according to the user; neither paid
activation was performed. ElevenLabs subsequently passed an authenticated read-only account GET after
a replacement credential was saved locally. Its source/output generation remains
untested because no paid generation was authorized.
All three checked-in example plans and three editable local pilot plans succeeded.
No paid generation, training, subscription or generation POST occurred.

Ignored `scratch/external-tools-readiness/` contains editable `pilot-*.json`,
request plans, provider instructions and two local helpers. Its
`provider-secrets.ps1` prompts for masked local entry and stores SecureStrings
using current-user Windows DPAPI. No keys were present at the start of the follow-up; account setup remains
pending until credentials are supplied and the access checks pass. Do not put
secrets in chat, command arguments or Git.

For an easier local setup, the ignored
`scratch/readiness/Connect-WORLDSEED-Asset-Accounts.ps1` opens a masked desktop
form with official account-page buttons, current-user DPAPI storage and bounded
read-only verification. It is available from Start Menu as **WORLDSEED Asset
Connections**. The form was constructed/tested without real credentials, and
opened for the user to complete provider sign-ins and key entry. It cannot
create accounts, buy subscriptions or generate assets. Existing saved keys stay
unchanged when fields are blank. The first real save attempt returned a generic
helper error before writing a credential. The helper was hardened to retain form
state explicitly, isolate credential loading, separate storage from verification
and report sanitized failure phases. The precise real failure was `ConvertTo-SecureString` missing from the WinForms
callback. The launcher and credential loader now explicitly import the bundled
PowerShell Security and Utility modules. A cold callback test passed; the running
window was repaired through its existing Check action without exposing or
re-pasting the masked entry. Actual replacement-key DPAPI storage, reload and
ElevenLabs read-only access then passed. The actual destination also passed a
benign temporary DPAPI fixture test; only that fixture was removed.

The user may close the credential window. In a future session, use the Start Menu
launcher or load credentials through the shell helper before authoring. Sanitized
verification results are in `scratch/external-tools-readiness/last-access-check.json`.
Scenario and Meshy were skipped without requests; ElevenLabs made one GET.

```powershell
# After signing into the provider in your own browser and obtaining its key:
. .\scratch\external-tools-readiness\provider-secrets.ps1 -Configure -Provider scenario
# Repeat with -Provider meshy and -Provider elevenlabs as needed.
# In subsequent shells:
. .\scratch\external-tools-readiness\provider-secrets.ps1 -Load
.\.venv\Scripts\python.exe tools/external_assets.py doctor
.\.venv\Scripts\python.exe scratch/external-tools-readiness/check_access.py
.\.venv\Scripts\python.exe tools/external_assets.py plan --brief scratch/external-tools-readiness/pilot-scenario-icon.json
```

The account helper performs at most one bounded GET per configured provider and
prints sanitized status/schema booleans. Missing keys skip requests. Restricted
keys can fail an account-read check despite having generation scope.
Scenario's pilot replaces the placeholder with documented compatible candidate
`model_google-gemini-3-1-flash`; its prompt/aspectRatio schema and availability
must still be checked against the actual account. It is not a trained WORLDSEED
style model. See [Scenario's model guide](https://docs.scenario.com/get-started/generation/third-party-model-generation).

Before the first separately authorized asset trial: finish account access checks,
confirm Scenario model inputs, review reference/source rights and account budget,
edit one pilot brief and choose a unique ID, inspect its offline plan, then obtain
separate authorization for `submit --execute`. Review native-size output before
import; a Meshy trial also needs a downloaded/reviewed GLB and a new Blender bake.
Sound playback/event mapping remains a separate game feature.

## Validation and contracts

- Compileall passed for `worldseed`, `tools`, `tests`; pip check found no broken requirements.
- Bounded external_assets, blender_bake_sprites and development_workflow suite:
  21 tests completed, 19 passed and two Windows symlink-privilege skips.
- Doctor and all example/pilot offline plans passed without network generation.
- Real Blender pipeline, authenticated Context7 discovery and live Obsidian semantic retrieval/source inspection passed as above.
- Ignored PowerShell helpers parse; local benign DPAPI round-trip and empty-key
  loading/checks passed. No secrets printed and no requests with missing keys.
- Fast Gate run `40232967474` passed all seven jobs at `43f84a9`. This follow-up
  changes only the dated setup documentation; unchanged runtime code was not
  rerun through the full gate for bookkeeping.
- Development validation only; full release suite and long soaks were not run.

Tracked scope across the setup: this handoff, documentation index, OAuth setup
guidance and Obsidian's normalization of the shared app/core-plugin JSON settings.
The original six configured core plugins remain enabled. The normalized format
matches installed Obsidian 1.14.5, avoiding its already-observed startup rewrites.
Device layouts, community-plugin binaries/settings, indexes, executables,
virtualenv, fixtures, outputs, credential helpers, credentials and MCP state
remain outside publication. No gameplay APIs, persistent fields, migration,
RNG namespaces, world generation, simulation, asset IDs or runtime UI change.
No tests were added because repository behavior did not change. No runtime
performance impact. Next dependencies are Scenario/Meshy paid API plans and account/model access,
followed by a separately authorized real asset trial. All available local setup
and ElevenLabs account readiness checks are complete.
