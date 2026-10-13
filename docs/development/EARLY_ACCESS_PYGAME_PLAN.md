# WORLDSEED Pygame Engine and Early Access Development Plan

Prepared for ReleMai on October 12 2026. Code baseline: canonical `ReleMai/WORLDSEED` main at `c85a6e2d6d498c51094155d9699d075e6ccd00f6`. This is a development plan. The work below is proposed unless explicitly described as existing or verified.

## 1 Recommendation and scope

Keep Python and pygame-ce for the next development phase. Strengthen the custom engine already present, complete a small sustainable survival experience, and establish a consistent visual presentation. Reconsider a renderer or engine replacement only when a measured limitation remains after those improvements.

Pygame can support WORLDSEED's present 2D desktop design. The practical limits are how much work happens each frame, how world state grows, and how much custom tooling the team can maintain. No library removes the need for good simulation boundaries, reliable saves, and useful player progression.

The next product target should be a coherent experience: gather supplies, make tools, prepare safe food and water, establish a usable home, recover from injury, and undertake longer expeditions or trade. Existing simulation breadth should support this experience before additional professions, house families, or large content batches are added.

Private testing can begin earlier than paid early access. A reliable 30 to 60 minute loop with clear known issues is useful for invited testers. Public early access needs sustained value, coherent presentation, dependable saves, and a supportable packaged build. Steam expects customers to receive a playable current product and accurate disclosure of incomplete features. [9]

### Current evidence

The prior audit verified the complete 2541 file canonical snapshot, ran 35 focused tests successfully, and confirmed current development CI success. Four isolated probes exposed save retry, cabin occupancy, spatial scaling, and discovery problems. The snapshot preflight was rechecked for this plan. No new game implementation or extended live playtest is claimed.

The bounded dummy-display benchmark measured 11.964 seconds for simulation initialization, 32.038 ms mean warm drawing at 2560 by 1392, and 2.241 ms mean movement command cost. These are a baseline for that harness, not live FPS or percentile results. Current full release validation remains separate from passing development checks.

## 2 The custom engine to build

WORLDSEED already implements a custom engine around pygame-ce. Improve it through small extractions from existing code. Keep authoritative state in the simulation and retain the command, generation, LOD, discovery, and persistence contracts.

| Responsibility | Existing foundation | Proposed improvement |
| --- | --- | --- |
| Runtime | RealtimeSimulationDriver and timing helpers | One lifecycle and event loop with bounded command dispatch and drawing |
| Simulation access | Command dataclasses and system queries | A small facade for commands and local observational read models |
| Presentation | PygameTerminal and presentation modules | Separate terrain, actors, camera, effects, widgets and animation |
| Preparation | Prepared chunks and regional plans | A bounded queue that publishes completed data at controlled boundaries |
| Persistence | SQLite transactions and saved deltas | SaveService with safe acknowledgement, recovery and explicit runtime paths |
| Content tools | JSON registry, validators and NPC lab | Focused scene, animation, item, recipe and building previews |

The runtime polls events, captures input, dispatches validated commands, advances permitted game time, obtains local read models, and draws. Simulation retains sole ownership of health, inventory, AI effects, collision, RNG and saving decisions. Animation interpolates visual positions and never creates a second movement or economy authority.

A render snapshot contains the viewport, visible actors, HUD, and requested panel data. Deep-copying the entire world every frame would recreate the current scaling problem. Keep stationary objects and moving actors in separate spatial indexes; update membership on tile, interior, life-state or LOD transitions.

The simulation tick remains anchored to game minutes. Wall time may drive visual interpolation and effects. Ordinary realtime play, hostile action-driven combat, paused conversation, and accelerated long work must retain explicit transitions. Test identical command sequences at different render rates.

Workers receive immutable inputs and return prepared results. They must not mutate live simulation or borrow its SQLite connection. Use a process or native routine only for a measured CPU hotspot. Start with bounded scheduling and safe publication; adding concurrency prematurely creates new failure modes.

This is a focused WORLDSEED framework. A general engine editor, new ECS, plugin system, native rewrite, or immediate GPU conversion is outside the first useful scope.

## 3 Stability and performance work

### Save correctness

Priority P0. `app._save` drains dirty terrain before the database write succeeds. The injected-failure probe left zero pending changes where one needed to survive for retry. Snapshot changes without clearing them, commit successfully, then acknowledge exactly the saved revisions. Keep chunk pins and retry data on serialization, write or commit failure. Surface a clear failure and recovery route. [10]

Completion requires failure injection, retry, reload and chunk-eviction regressions. If saving later uses a worker, edits made after its snapshot must survive acknowledgement. Measure snapshot capture, JSON encoding, SQL and explicit backups separately before changing persistence format.

### Construction safety

Priority P0. Advancing a cabin to Frame while standing inside its footprint succeeded and made all four adjacent exit cells impassable. Check occupancy and reachable exits before stage changes. Complete the same stable door and interior contract used by collision and interactions. Test players, NPCs, every rotation, rejection, cancellation and reload. [11]

### Local work and persistent discovery

Priority P1. Continuous NPC movement scans all realized NPCs. Fractional movement also invalidates a renderer index that rescans eleven world collections. Maintain active actor sets and incremental chunk indexes. A microbenchmark with no local NPCs rose from 0.182 ms for 1000 distant NPCs to 9.072 ms for 50000. The requirement is local cost that stays nearly constant as distant state grows. [12]

Discovery currently removes old cells beyond a 120000 cell cap and rebuilds indexes. A capped update averaged 80.905 ms in an isolated probe. Replace this with compact per-chunk discovery and incremental persistence. Preserve exact known cells, old save defaults and the distinction between sight and memory. [13]

### Rendering and asset work

Profile simulation, preparation, terrain, actors, UI, effects and display presentation independently. Record p50, p95, p99, worst stalls, cache sizes and allocations. Keep a repeatable dense-village scene, wilderness scene, open-panel scene and large-save fixture.

Load, convert and scale assets outside critical frame paths; existing loaders already use `convert_alpha`. Cache bounded visual variants and text. Batch compatible draw groups with `blits` or restricted `fblits`, preserving ordering and alpha behavior. Cache unchanged terrain and UI composition by revisions. [1]

Use viewport culling, bounded effects, and explicit cache eviction. Benchmark partial display updates rather than assuming dirty rectangles are faster. Test one frame-pacing policy with fallback; vsync is backend-dependent. Keep events serviced during lengthy work because the queue can overflow. [2][3]

### Preparation and runtime paths

Measure cold and warm region crossings, then prepare approaching regions with a bounded queue. Rendering and hovering must never plan geography. Preserve deterministic generation order and recorded legacy versions.

Introduce RuntimePaths for read-only assets and writable saves, settings, mods, logs and crash reports. Current paths often depend on the launch directory. Support a durable user-data location and explicit portable mode, with discovery/import of legacy saves rather than silent relocation. Pin tested dependency versions for distributed builds.

## 4 Presentation that feels finished

The game has substantial item, actor, building and interior artwork. Coverage is ahead of visual integration: actors still use static front-facing sprites, primary panels retain dense terminal conventions, and building presentation needs consistent alignment. A first art pass should establish a common visual language rather than commission another large asset batch.

### Four reference scenes

Create one approved forest, camp, village street and interior using the current renderer. Agree on projection, actor height, building scale, palette, lighting, shadows, terrain detail, selection and typography. Doors, feet, collision and click targets must align with authoritative geometry. Art may not move a physical boundary to make a scene look convenient.

Use the scenes as screenshot regressions and as the standard for future assets. Choose a few supported zoom levels, prepare art for those scales, and avoid accidental smoothing or inconsistent pixel density. Define roof and wall visibility so entrances and indoor actors remain readable.

### Shared graphical interactions

Build reusable panels for inventory, crafting, building, health, conversation and settings. Use one spacing system, font hierarchy, button language, tooltip format and disabled-state treatment. Show missing tools, materials, station access and risk before commitment. After success, show what was consumed, gained and changed.

Preserve NavigationStack, central key routing, retained selection/scroll, observational inspection and mouse/keyboard parity. Enter remains the action hub and TAB the information hierarchy. WASD stays reserved for movement; configurable bindings must enforce that invariant. A third-party widget library may sit behind these contracts.

### Motion sound and accessibility

Add directional idle and walk animation, followed by a small set of gathering, work, attack, hurt and rest cues. Tie action visuals to simulation results and durations. Avoid animation that suggests goods were produced before their authoritative transfer.

Add basic ambient and action audio with separate volume controls and a fully usable muted mode. Provide larger text/UI, reduced effects, non-color-only danger cues, keyboard focus, clear hover selection and reliable focus-loss behavior. Test 1280 by 720 and 1920 by 1080 plus resizing and common Windows scaling settings.

Completion means an unfamiliar tester can identify an interactable object, understand an unsuccessful action, follow health warnings, and use the main panels without debug identifiers or clipped controls. Smooth rendering alone does not achieve that.

## 5 Survival and progression work

### A usable home and ordinary recovery

Finish the existing cabin before adding more home families. Connect a stable entrance, persistent interior, safe exit, furnishing/storage, bed, shelter and insulation. Keep container identity and contents through furniture movement. Verify gather, build, enter, use, save, reload and leave as one player sequence.

Add bounded non-magical HP and blood recovery conditioned on food, water, rest and treatment. Wound and body-part recovery already exist; ordinary rest primarily restores stamina and reduces pain. Correct temperature logic so effective zero exposure stops adverse drift. Show treatment needs and recovery progress. [14]

### A sustainable daily loop

Add actual player sleep debt and meaningful sleeping conditions after the recovery loop works. Connect exertion and sprint costs to simulation authority. Balance hunger/thirst around decisions and travel rather than constant meter maintenance.

Enforce existing prepared-meal spoilage deadlines, then add compact freshness batches for relevant raw foods. Make drying, smoking and appropriate storage extend expedition supplies. Give vessels filled quantity/capacity and consistent transfer, drinking and purification rules. Connect cooking and heating to real fuel and lit state using existing item/fire authority. [14]

### Reasons to keep playing

Connect hunting experience to practice. Strengthen existing tracking, fishing, processing, farming, salvage perks, material quality and trade before adding many new systems. Introduce traps only after inventory ownership, persistence and bounded checking are established.

Provide a readable progression from primitive tools and camp supplies to a secure home, preserved provisions, useful metal equipment and longer expeditions. Resources, seed varieties, specialists, buyers, knowledge and local shortages should create travel goals through existing causes. Audit recipes for useful outputs and remove dead ends from the introductory path.

Test wilderness survival, homesteading and settlement trade/crafting as three viable approaches. A proposed initial content target is 10 to 20 hours of purposeful play, established through player sessions rather than recipe counts.

## 6 Research on a practical pygame stack

### Keep the Surface renderer first

pygame-ce already provides efficient converted surfaces and batch drawing. Retain it while fixing algorithms and measuring caches. Adding another renderer will not accelerate Python AI, save serialization or whole-world scans. [1]

The SDL2 Renderer and Texture API is a possible later textured-2D GPU backend, but its official documentation labels it experimental. Isolate it behind a backend interface and test device resets, resizing, fullscreen, alpha and fallback before adoption. [4]

ModernGL is another optional renderer path when profiling demonstrates a need for GPU batching or shaders. It can use an existing OpenGL context and requires OpenGL 3.3 or later. It requires implementation of a renderer, texture lifecycles and driver testing. Avoid retaining CPU full-scene drawing plus full-scene texture uploads every frame. [5]

Choose at most one GPU experiment and retain the working Surface backend initially. Neither is an early prerequisite.

### Evaluate UI help on one screen

pygame_gui supports themed controls, windows and anchored layouts with pygame-ce. Evaluate a settings or inventory screen through an adapter. Keep WORLDSEED's navigation, input authority and discovery filtering. Measure creation effort, text/layout quality, large-list behavior and runtime cost before wider adoption. [6]

Existing widgets may be sufficient after a coherent visual pass. Avoid two competing focus or global input systems. Preload fonts and disable development theme watching in distributed builds.

### Package a standalone Windows build

Current playtest tooling produces a source/assets ZIP. Evaluate PyInstaller one-folder mode with explicit assets, game data, hidden imports and runtime paths. It bundles Python so testers do not need a development installation. It does not speed up the simulation. Prove one-folder installation before one-file packaging, which extracts components during launch. Build and test on the target operating system. [7]

Retain SQLite and JSON content. Use standard profiling and project diagnostics first. Conventional CPython threads do not automatically improve CPU-heavy Python work; use measured process/native experiments only where boundaries are safe. [8]

## 7 Delivery milestones and first session

| Milestone | Scope | Exit condition |
| --- | --- | --- |
| M0 Reliable baseline | Reconcile local work, identify build, capture fixtures | One reproducible current baseline and preserved local work |
| M1 Safe private test | Save retry, cabin occupancy, critical input feedback | Reliable 30 to 60 minute invited test |
| M2 Smooth local play | Spatial indexes, discovery, caches, pacing | Local work remains bounded as distant state grows |
| M3 Coherent presentation | Four reference scenes, main panels, key animations | Core loop visually consistent and readable |
| M4 Sustainable survival | Functional cabin, recovery, sleep, food/water/fuel | Multi-day survival without reset exploits |
| M5 Purposeful progression | Equipment, farming, trade and expedition goals | Sustained play across selected seeds and approaches |
| M6 Early access candidate | Package, settings, compatibility, hardening, support | Release criteria met on the exact candidate |

Treat milestones as dependency order, not a promised calendar. Visual work may overlap a stable code boundary, but keep one coherent publishing work unit at a time. Estimate implementation only after the first two bounded tasks and the rendering baseline.

### The first thirty minutes

Minutes 0 to 5 introduce movement, interaction, time/pause and nearby safe opportunities. Minutes 5 to 15 produce one primitive tool, food and clean water. Minutes 15 to 25 establish camp/storage or start a cabin and explain rest/health. Minutes 25 to 30 include save/reload and a meaningful choice of hunting, fishing, gathering, trade or construction.

Use optional contextual guidance over real commands and discovered knowledge. Explain the next practical goal without forcing a scripted quest chain or revealing hidden world state. Three unfamiliar testers should complete this sequence without developer intervention before widening the test group.

## 8 Verification and early access criteria

Measure on named hardware with recorded OS, Python/build, resolution, seed and save size. Proposed targets below require calibration; they are not achieved claims.

| Measurement | Proposed initial target |
| --- | --- |
| Ordinary 1080p frame time | p95 at most 16.7 ms and p99 at most 33.3 ms |
| Ordinary input acknowledgement | p95 at most 50 ms |
| Unexplained routine stalls | No stall above 100 ms in the reference scenarios |
| Local scaling | At most 20 percent extra local cost with ten times distant state |
| Save snapshot capture | Initially at most 50 ms on the gameplay thread |
| Long preparation or work | Visible progress and responsive window events |

Record expensive save and region events separately rather than hiding them in averages. If a lower frame target is necessary on minimum hardware, publish it honestly and keep consistent pacing.

A private build needs the short core loop, recoverable saves and actionable diagnostics. Public early access should additionally pass these checks:

- No unresolved critical crash, lost-goods/save-loss defect or core progression blocker across ten varied multi-hour invited sessions, including a four-hour session.
- Candidate save/load, failed/interrupted save, legacy-save, cache-rebuild and more-than-120000-cell discovery checks pass.
- Frame/input targets and bounded RAM/save growth hold on representative explored saves and a deliberate long-simulation fixture.
- The complete home, food/water, recovery and progression loops work across several seeds, with readable explanations.
- The standalone build launches offline on clean Windows without developer Python or install-time pip commands; assets and diagnostics are included.
- Controls, text scaling, audio/effects settings, pause behavior, and error messages are usable. Known issues and save compatibility are stated.
- Current manual release validation and appropriate bounded conservation/soak checks pass on the exact packaged candidate. Development CI remains a separate level of evidence.

Report problems with build identity, seed, scenario, reproduction steps and a player-approved save copy when needed. Crash reports and saves stay local unless the player explicitly submits them. Steam's guidance is a publication boundary; the numeric targets above are WORLDSEED proposals. [9]

## 9 First implementation work units

1. Save retry preservation and failure UI, with a failing-save regression.
2. Cabin stage occupancy/access safety, with player and NPC regressions.
3. Runtime timing instrumentation and repeatable reference scenes.
4. Active actor/static indexes and compact discovery persistence.
5. Shared graphical panel style and a complete usable cabin/recovery sequence.
6. Standalone packaging and invited first-session playtesting.

Start each unit from freshly verified main, preserve unrelated local work, run bounded targeted checks, and publish one coherent validated change with a handoff. Persistent changes need defaults, round trips and a schema decision; generation contracts must remain pinned. Do not expand the feature list during release hardening.

## 10 Sources and handoff

Research checked October 12 2026. Recommendations about implementation effort and product scope are engineering judgments. The sources below document capabilities and constraints; they do not demonstrate WORLDSEED performance.

1. [pygame-ce Surface conversion and batching](https://pyga.me/docs/ref/surface.html)
2. [pygame-ce display updates and frame pacing](https://pyga.me/docs/ref/display.html)
3. [pygame-ce event queue](https://pyga.me/docs/ref/event.html)
4. [pygame-ce experimental SDL2 video API](https://pyga.me/docs/ref/sdl2_video.html)
5. [ModernGL context creation and requirements](https://moderngl.readthedocs.io/en/latest/topics/context.html)
6. [pygame_gui quick start](https://pygame-gui.readthedocs.io/en/latest/quick_start.html), [layout](https://pygame-gui.readthedocs.io/en/latest/layout_guide.html), [themes](https://pygame-gui.readthedocs.io/en/latest/theme_guide.html)
7. [PyInstaller operating modes and distribution](https://pyinstaller.org/en/stable/operating-mode.html)
8. [Python threading and CPU constraints](https://docs.python.org/3/library/threading.html)
9. [Steam Early Access guidance](https://partner.steamgames.com/doc/store/earlyaccess)
10. [Save coordinator](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/app.py#L505), [dirty delta drain](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/world/world.py#L200), [database transaction](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/persistence/database.py#L297)
11. [Cabin stage transitions](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/systems/homestead_blueprints.py#L123), [footprint collision](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/systems/building.py#L185)
12. [NPC frame movement](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/systems/free_movement.py#L144), [renderer spatial cache](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/ui/pygame_terminal.py#L3575)
13. [Discovery cap and index rebuild](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/sim/engine.py#L290)
14. [Player recovery and temperature](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/sim/engine.py#L758), [prepared meal expiry metadata](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/systems/food.py#L107)
15. [Existing packaging](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/tools/package_playtest.py), [runtime configuration](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/config.py), [retained navigation](https://github.com/ReleMai/WORLDSEED/blob/c85a6e2/worldseed/ui/session.py)

Scope of this work unit: planning documentation and its editable Word edition. Public APIs, persistent fields, migration, RNG namespaces, gameplay behavior and runtime performance are unchanged. Verification covers source references, document structure and rendered layout. The prior code audit's results are distinguished from future acceptance criteria. Next dependency: reconcile the current checkout and implement save retry preservation before introducing asynchronous saving or new construction behavior.
