# WORLDSEED G4/G8-candidate — layered oak/pine art and OpenGL sprite renderer

**Status:** Opt-in art and standalone shader-capable OpenGL candidate; **not a production GPU default/cutover**. Starting baseline `761396abdf9d010ebfa66b9e838bcd89fd04e7b1`, Fast Gate `38678812338` successful (7/7). Builds on the [G0–G9 roadmap](WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md), G0/G1a and G1b world-space contracts, and G2 software canopy preview.

## Added tree artwork and provenance

- Authored **original deterministic source art** in `tools/build_worldspace_tree_art.py`, with 384×384 straight-alpha RGBA trunk, shadow and spring/summer/autumn/winter canopy PNGs for *oak* and *pine* (12 distinct layers). These are 2D sprites with a common foot anchor; not 3D meshes. Distinct evergreen whorls, spreading oak broadleaf foliage and season palettes.
- The packed delivery is `worldseed/assets/sprites/worldspace/trees/tree_layers.b85`: text-safe Base85 archive of the 12 original PNGs. The source manifest lists every filename, SHA-256, dimensions, channel, anchoring, species, season, collision boundary and provenance. This is intentionally included in the Python package data; no runtime Pillow requirement.
- `tree_art.py` decodes and SHA-checks individual PNGs on demand, then scales pygame surfaces in a **48 MiB / 64-entry LRU**, without mutating cached source alpha during local fades. Rebuild loose PNGs using `python -m tools.build_worldspace_tree_art --output-dir worldseed/assets/sprites/worldspace/trees` for art editing/approval.
- The G2 opt-in software viewer now allows at most four already-prepared oak/pine trees and uses authored trunk/crown/shadow layers. Footprint/harvest positions stay tied to existing resource cells. Exclude buildings, shells, player homesteads, unknown and remembered-only cells; keep current actor/roof/stealth gating. Normal software output remains identical while `WORLDSEED_G2_CANOPY_PREVIEW` is not `1`.
- **Art approval remains a separate player-visible review gate**. Source graphics are ready for testing, not an assertion of approved final art direction; the asset pack does not change worldgen v8 or resourcegen v5.

## OpenGL candidate: architecture and constraints

`worldseed/presentation/gl_worldspace.py`, vertex/fragment shader assets and `tools/worldspace_opengl_probe.py` form an isolated, shader-capable ModernGL/OpenGL 3.3 renderer:

1. **One window/context owner:** the native probe creates one pygame SDL OPENGL window, handles its own events and presents via that same window. Renderer itself never creates a second competing SDL/pygame window. The game's normal PygameTerminal **is not switched** to GL. Input and game UI migration require G8 integration work, not another parallel owner.
2. **Explicit immutable draw commands** (`SpriteCommand`): texture identity/revision, source RGBA and dimensions, projected world-space bounds, CURRENT visibility clip rectangles, per-object opacity and local canopy fade. `commands_from_projected` consumes only the authorized G1 scene; it cannot create gameplay collision, discover cells or change saved state.
3. **Shader functions:** alpha sprite sampling, ambient color grade, world-space screen projection, fragment-local alpha cutout with a soft edge. Authoritative fog-of-war clips are applied as conservative OpenGL scissor rectangles *before* any pixels draw. Shadow materials do not inherit crown fade.
4. **GPU caching:** deterministic revision-keyed texture LRU with bounded 128 MiB default / 256 MiB maximum; 4,096 sprite command limit, 2,048 clip rectangles per sprite, 16,384 clip operations per frame. Consecutive compatible sprite draws batch up to 64 quads, retaining depth order. Context/program/texture failures surface `GPUBackendUnavailable` for fallback—not a false performance success.
5. **Window/resize:** `resize` updates projection without invalidating unchanged art textures. Real-world resize, fullscreen, alt-tab, driver resets, input mapping and screenshot pixel parity must still pass on Windows. This native shader probe is not a complete game renderer, renderer switchover, game lighting, weather, or GPU-performance acceptance.

### Native Windows acceptance commands

Install the optional graphics backend (the default installation does not require it):

```powershell
python -m pip install -e '.[gpu]'
python -m tools.worldspace_opengl_probe --size 1280x720 --frames 180 --output scratch/worldspace-gpu-720p.json --screenshot scratch/worldspace-720p.png
python -m tools.worldspace_opengl_probe --size 2560x1440 --frames 180 --output scratch/worldspace-gpu-1440p.json --screenshot scratch/worldspace-1440p.png
```

Do not set `SDL_VIDEODRIVER=dummy`. Inspect `GL_VENDOR`, `GL_RENDERER` and `GL_VERSION` in the JSON; a hosted VM's software render device does not certify real gaming hardware. A GPU context failure is reported as unavailable and never changes the default software renderer. `worldspace-opengl-probe.yml` is **manual**, not added to every push.

### Hard remaining gates / non-claims

- Actual gameplay GPU ownership swap, direct GPU terrain batching/atlas packing, render graph with NPCs and buildings, event and click parity, live native Windows high-resolution p95 frame times, context loss, full lighting source binding, fog/weather, packaged binary and long playtests remain open, as required by G5–G9.
- Existing GPU SDL2 alpha-only probe remains separate and untouched. Preserve `EARLY_ACCESS_PYGAME_PLAN.md`, `GPU_COMPOSITING_EXPERIMENT.md`, M2 closeout, caching/spatial indexing, runtime profiling, CI, player-save compatibility, and software fallback.
- The art bundle and shader contracts are renderer-owned only. No gameplay commands, save schema, generator version, settlement, NPC logic or input routing change.
