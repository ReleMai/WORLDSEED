# Dev66: roofs and canopies intercept GPU precipitation

## Scope and baseline

Canonical baseline: `9d8b3de21fb32893e3231238fc2e160397248a99`.
This implements the admitted-cover precipitation step proposed in the
[W4 landscape handoff](WORLDSEED_W4_LANDSCAPE_QUALITY_2026-10-16.md) and left open
by the [Dev65 recovery](DEV65_GPU_RECOVERY_2026-10-22.md). October 25 external-tool
setup remains an offline authoring workflow; no external generator is used here.

## Delivered behavior and contracts

- Rain and snow in the full GPU game are attenuated by currently admitted public
  building roofs, independent roof objects and mature tree crowns. Source-art
  alpha and exact sight clips preserve courtyard holes and gaps between leaves.
- Cosmetic transparency around the player remains a readability effect. The
  precipitation pass uses original cover alpha, so revealing the player does
  not open a hole in the displayed weather protection.
- Remembered art, trunks, doors, ordinary props and departing harvest ghosts do
  not become current cover. The atmosphere shader still rejects memory/unknown
  scene pixels before sampling cover. Rendering cannot disclose a hidden room.
- Wet idle frames reuse the detached scene. Static roof coverage is reused;
  swaying crowns redraw coverage with exactly the same visual clock/vertex sway
  as their color pass. View capture and resize invalidate the cover cache.

`SpriteCommand.precipitation_cover` is an explicit boolean visual classification.
`presentation/precipitation_cover.py` selects at most 2,112 current cover commands
from the existing bounded 4,096-command frame. Classification belongs to the
tree/building/object producers; asset filenames do not establish physical cover.

`GLWorldspaceRenderer.draw(..., coverage_only=True)` shares detached materials,
source textures, exact clips and vertex motion with the normal renderer. A small
dedicated `worldspace_cover.frag` program avoids adding a cover branch to the
large terrain shader. `GLAtmospherePass` owns an R8 cover target and applies it
only when `present(..., cover_enabled=True)` is requested. Defaults preserve the
existing renderer/QA APIs. Packaging and startup self-checks require the shader.

## Authority, persistence and versioning

Engine/package versions advance to Dev66. No persistent fields, migrations,
RNG namespaces, weather algorithm, geography, collision, sight/discovery, NPC
admission, gameplay shelter or time-control rules change. Cover metadata,
buffers and cache state are ephemeral presentation data. Render/idle paths do
not query generators, resource placement, private rooms or distant populations.

## Performance and lifecycle

The RGBA8 scene and R8 cover consume five bytes per viewport pixel, within the
existing 48 MiB active atmosphere-buffer budget through 3840x2160. Resize releases
old resources only after replacement allocation succeeds, and failed allocations
leave the previous targets usable. Close releases both targets and shaders.

No CPU world bitmap, per-frame image readback or new runtime dependency is used.
Wet swaying cover adds a bounded GPU pass; dry scenes skip it and static covers
reuse it. `gpu.precipitation_cover` timing and separate cover draw reports expose
its cost without misreporting it as part of the old color-only frame count.
Stationary roof clips use cropped UV meshes in batches of up to 64; moving
canopies retain exact scissors. A 130-clip regression requires three static
draws instead of 130, while preserving the moving-canopy path.

## Verification and evidence

Focused checks cover semantic producer tags, source-alpha gaps/courtyards,
partial cover and overlapping alpha, cosmetic reveal independence, exact clips,
unknown/memory stability, rain and snow, resize/clear/allocation rollback,
idle cache ownership and unchanged main-game authority fingerprints.

- The producer/admission and existing scene, building, object, visibility,
  Dev65 feedback and packaging checks passed: 63 tests in 29 seconds.
- The final backend and real EGL pixel checks passed: 19 tests, including the
  static-clip batching regression. Nine new real OpenGL pixel/native-window
  cases also passed from an empty Mesa shader cache, with no skips, in 76 seconds.
- Existing main-game, Dev65 native, interior and package compatibility passed:
  40 tests, no skips, in 58 seconds under the standard 180-second check budget.
- Python compilation, workflow YAML parsing and whitespace checks passed.

The [before image](../evidence/dev66-precipitation/before.png),
[after image](../evidence/dev66-precipitation/after.png) and
[cover mask](../evidence/dev66-precipitation/cover.png) capture the actual prepared
main-game reference village at the same visual clock with controlled detached
rain. The [capture record](../evidence/dev66-precipitation/capture.json) confirms
unchanged authority, eight admitted covers/eight cover draws and 3,456,000 bytes
of atmosphere buffers at 960x720. Twelve warmed frames per mode on llvmpipe
measured median 85.800 ms without interception and 85.745 ms with it; this short
software trace is evidence of bounded submission, not a hardware speed claim.

Two earlier combined 90-second local runs hit cold compilation costs in the
unchanged terrain/color shader; no assertion failure preceded either timeout.
The narrower compatibility run and capture used local `GALLIVM_PERF=nopt` to
bound software-driver optimization cost. Production and CI settings/deadlines
are unchanged. Development graphics checks use SDL offscreen/Mesa EGL; they do
not establish native Windows hardware acceptance. The full release suite and
long soaks were not run. Exact-commit Fast Gate and Windows GPU candidate
workflows run after publication.

## Known limits and next dependency

This is a screen-space precipitation interception model using admitted 2.5D
cover art. It does not simulate elevated drop trajectories, runoff, splashes,
ground accumulation or new shelter/wetness mechanics. Unknown and remembered
space cannot contribute current cover. The separate legacy software/QA weather
path retains its previous default rendering behavior.

Next W4 work can add admitted exposed-ground splashes and then fuller directional
shadows/occluded light. W5 device recovery, representative Windows playtests,
performance/long-world acceptance and the existing bootstrap-audit helper defect
remain separate work units.
