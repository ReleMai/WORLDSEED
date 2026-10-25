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
| Obsidian + Smart Connections | Waiting on a specific user action | Obsidian 1.14.5 installed; the existing clean-checkout docs folder is registered and open as the vault. Desktop control was stopped with Escape before community-plugin setup. Install/enable Smart Connections Core, finish local indexing and test source retrieval. |
| Scenario | Waiting on account and credentials | Example and editable pilot plans validate offline. Key/secret absent; account/model access unverified. |
| Meshy + Blender | Waiting on Meshy credentials; Blender operational and verified | Meshy key absent. Blender 5.2.3 LTS installed and background GLB-to-PNG bake verified. |
| ElevenLabs Sound Effects | Waiting on account and credential | API key absent; example/pilot plans validate offline. |
| Context7 | Operational and verified | Codex OAuth login succeeded; authenticated tool discovery succeeded; both target libraries resolved and returned docs. Reload the client/new chat to expose newly added tools. |

### Project memory

Use this checkout's `docs/` directly. Open `development/memory/START_HERE.md`
with Ctrl+O and bookmark it using the note's menu. An ignored convenience launcher
is `scratch/readiness/Open-WORLDSEED-Memory.ps1`; it opens that note through the
registered Obsidian URI. A Start Menu shortcut named WORLDSEED Project Memory
opens the same note. No documents are copied into a second knowledge store.

In Obsidian Settings -> Community plugins, install **Smart Connections** Core
and enable it. Keep local embeddings; do not configure cloud providers for this
initial check. Inspect included sources/exclusions and wait for ready/completed
index status in Smart Environment. Installation and indexing were not verified.

For the retrieval test, open the external-tools foundation handoff and inspect its
related notes. A second useful known decision is in
[the smooth visibility handoff](2026-10-17-smooth-sight-memory-player.md): the full
player renders last while hidden NPCs/rooms remain filtered. Follow a retrieved
match to the original file, confirm the source/date and compare current code.
Record completion only after the plugin returns a relevant passage and the
original is inspected. Reading a file directly is not a semantic-retrieval test.
Accepted decisions remain in versioned docs; similarity does not grant authority.

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
key at process, user or machine scope. No account access can be claimed.
All three checked-in example plans and three editable local pilot plans succeeded.
No paid generation, training, subscription or generation POST occurred.

Ignored `scratch/external-tools-readiness/` contains editable `pilot-*.json`,
request plans, provider instructions and two local helpers. Its
`provider-secrets.ps1` prompts for masked local entry and stores SecureStrings
using current-user Windows DPAPI. No actual keys have been entered/stored.
Do not put secrets in chat, command arguments or Git.

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
- Real Blender pipeline and authenticated Context7 discovery passed as above.
- Ignored PowerShell helpers parse; local benign DPAPI round-trip and empty-key
  loading/checks passed. No secrets printed and no requests with missing keys.
- Development validation only; full release suite and long soaks were not run.

Tracked scope: this handoff, documentation index and OAuth setup guidance. Local
settings, executables, virtualenv, fixtures, outputs, credential helpers and MCP
state remain outside publication. No gameplay APIs, persistent fields, migration,
RNG namespaces, world generation, simulation, asset IDs or runtime UI change.
No tests were added because repository behavior did not change. No runtime
performance impact. Next dependencies are Smart Connections desktop completion
and provider credentials, followed by a separately authorized real asset trial.
