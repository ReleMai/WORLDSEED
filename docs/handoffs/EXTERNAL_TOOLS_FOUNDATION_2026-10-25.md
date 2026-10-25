# External development tools foundation

Date: 2026-10-25. Baseline: canonical `ReleMai/WORLDSEED` main at
`7a90b7dae397f1512aff792dfd895dfb539d7c4c`. Full shallow Git checkout and
workspace preflight passed before editing. This is one developer-tooling work
unit; package/runtime version stays RC14 Dev65.

## Scope / modules changed

- [Five-tool decision and operating guide](../development/EXTERNAL_TOOLS.md):
  Obsidian + Smart Connections, Scenario, Meshy + Blender, ElevenLabs SFX, Context7.
- `docs/.obsidian/`, memory navigation/templates and Context7 client examples.
- `tools/external_assets.py`: offline request planner, credential-status doctor,
  explicit authenticated submission/status commands and ignored staging.
- `tools/blender_bake_sprites.py`: local static GLB to grounded transparent
  orthographic PNG views, with a source/render/output provenance manifest.
- Example briefs, environment-variable reference, local-data ignores, agent
  guidance and bounded pure contract tests in the existing Fast Gate.

## Public APIs / contracts

`external_assets.py doctor` and `plan --brief FILE` are offline. `submit` and
`status` require `--execute`; credentials come only from environment variables.
Endpoints are fixed per provider. Submission POSTs do not retry or follow
redirects; an exclusive submission record prevents accidental reuse of an ID.
Errors do not echo provider exception bodies or credential values. Output is
unreviewed staging under `scratch/external-tools/<id>`.

Scenario supports the `prompt`/`aspectRatio` input subset and requires a real
compatible account model ID. Meshy submits text-to-3D geometry-only preview;
refinement and artifact downloads are not implemented. ElevenLabs writes
unreviewed audio plus a hash record. No provider is imported by gameplay.

Blender takes a reviewed local `.glb`, normalizes/grounds its geometry and bakes
1/4/8/16 views. Output must be a new/empty staging folder under checkout scratch
or outside the checkout. Runtime asset directories cannot be targets.

## Persistent fields / migration and RNG namespaces

No game-state fields, save migrations, gameplay RNG namespaces, content IDs,
world-generation versions, sprites or runtime dependencies change. Vault search
does not become simulation/NPC memory. CPU Cycles uses a fixed authoring seed;
exact pixels across Blender versions/material revisions are not guaranteed.

## Validation

- Python compileall passed for `worldseed`, `tools` and `tests`.
- 21 focused tests passed: external request contracts/secret handling/staging,
  Blender normalization/output protection and existing development workflow.
- All three checked-in provider examples produced valid offline request plans;
  doctor confirmed no provider credentials were configured.
- Vault JSON and MCP JSON/TOML examples parse; local documentation links and
  whitespace were checked.
- Real Blender 4.3.2 CPU Cycles smoke: a disposable cube GLB produced four
  128px RGBA views in 3.8 seconds with 64 samples. Transparency, framing,
  fixed foot anchors and hashes were inspected. The fixture/output live outside
  Git under `/workspace/scratch/`; this validates the bake path, not AI art quality.
- Independent implementation review found no blockers. Symlink tests skip on
  hosts without symlink privileges. Automatic Fast Gate follows publication;
  its exact run/result is reported in the session, not presumed here.

## Performance / UI exposure

Developer CLI and documentation only. No game UI routes, render-frame work,
simulation work or network dependency is added. Live requests have bounded
timeouts/response sizes; status is one GET rather than an endless poll loop.

## Known limitations / next dependency

No paid generation, asset acceptance, custom training, desktop community-plugin
installation or authenticated Context7 connection was performed. The account
credentials are absent. Activate the desktop vault/plugin and coding-client
connection, configure provider credentials, replace Scenario's model placeholder,
then run the documented small quality trials. Obtain source assets through each
provider and use the existing reviewed import pipeline. Runtime sound playback
and event mapping remain a separate feature after sound assets are accepted.
