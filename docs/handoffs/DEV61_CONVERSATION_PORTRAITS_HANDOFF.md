# RC14 Dev61 — Paused conversations and composite portraits

Baseline: canonical `ReleMai/WORLDSEED` main at
`f9afe2a77147e67c7cc6778c2d12e7e42b1ab65c`. Engine/package:
`1.0.0-rc14-dev61` / `1.0.0rc14.dev61`.

## Behavior and ownership

Conversation time is frozen before the nearby-person picker opens and remains
frozen through all topic branches, inspections and gift selection. Direct chat
entry acquires the same hold. Closing chat resumes from a fresh wall-clock
baseline; reading time never becomes an NPC movement burst. Exceptions and
window close release holds. Existing explicit pause and combat suspension keep
their independent authority.

`sim/realtime.py::RealtimeSimulationDriver.pause_realtime()` is a nest-safe
context manager. `Terminal.pause_realtime()` and `PygameTerminal.pause_realtime()`
suppress their pump callbacks and delegate the hold to the installed bound
driver. The scoped depth is transient driver/backend state. App wrappers own
the route lifetime; UI rendering still cannot advance simulation time.

NPC conversation and profile shells display the character name once. Graphical
chat exposes one Inspect button in its title bar; terminal chat retains one
ordinary inspection choice. Conversation scenes retain their existing option
API. The graphical portrait strip separates role, context and relationship
information and shows `TIME PAUSED`. The nested topic path, complete paged prose,
keyboard word focus, reply paging and retained route behavior remain intact.
Backend reply capacity matches the new geometry.
Profile overview rows omit facts already shown in the identity cards and avoid
a second Traits summary; the complete underlying data stays available to the
terminal backend and existing document routes.

## Portrait composition and persistence

`presentation/portraits.py` derives an immutable face descriptor from world seed,
NPC UID and sex. Independently selected parts compose a front-facing pixel
portrait: head, jaw, ears, eyes, eyebrows, nose, mouth, hair, facial hair, neck
and clothed bust. The validated `data/portrait_features.json` catalog contains
7 head shapes, 6 jaws, 5 ears, 7 noses, 6 eye shapes, 6 brows, 6 mouths,
14 hairstyles, 8 facial-hair variants, 3 necks and 6 busts, plus 12 skin,
11 hair, 8 eye and 12 clothing palettes. Male and female weights favor different
silhouettes while sharing facial-feature pools. Youth, adult and elder details
change without rerolling the underlying facial identity.

`portrait_spec(seed, npc_uid, sex, age=30)` returns the descriptor;
`PortraitComposer(max_entries=96).render(spec, size=128)` returns a cached pygame
surface. App chat and profile data carry the same descriptor. The renderer reads
no simulation state. Portraits remain stable across route changes, resizing,
reloads and unrelated name, occupation, wealth or relationship changes. Unknown
NPCs show their visible face while their name and private profile stay hidden.

No persistent fields, save-schema migration or geography changes. Portraits are
derived presentation with bounded surface caching; they do not consume mutable
simulation RNG or realize populations. Pygame stays inside presentation/UI.
The existing authored map actor sprites continue to provide world movement art.
The RNG namespace is `presentation:npc-portrait:v1`, with independent domains
per part, palette and facial detail. Sorting content IDs prevents catalog key
order from changing selection. The LRU has both an entry limit (96 by default)
and a memory limit (16 MiB by default); oversized surfaces bypass caching.

## Validation and next dependency

Focused checks cover driver/backend/app pause lifetimes, nested inspection and
gifts, prior pause/combat, no catch-up, exceptions/window close, terminal versus
graphical Inspect choices, deterministic identity and generation order,
catalog validation, aging, pixel diversity, bounded caching and observational
rendering. UI checks compare actual portrait pixels across chat/profile and
resized nested screens, count rendered names and Inspect targets, and verify
every paged choice and linked word stays clickable. The automatic fast gate
includes the four new Dev61 test modules.

Regenerate the composited gallery with `python tools/preview_npc_portraits.py`.
Regenerate actual-scene chat, narrow nested chat and profile previews with
`python tools/preview_dev61_conversations.py`. Preview creation asserts that
authoritative state and inventory remain unchanged. Artifacts live under
`artifacts/dev61-*.png`.

Development validation: 134 combined conversation, portrait, introduction,
profile, realtime and combat regressions passed in 3.4 seconds. An additional
portrait memory-budget regression was added and the portrait module was checked
again. `compileall`, `git diff --check` and both bounded preview tools passed.
No pygame checks were skipped. Four checked-in PNGs were visually inspected,
including the 640×440 nested panel. Full manual release validation is separate.

The preceding Dev60 automatic gate reached an unexplained native exit in the
Windows facade audit (exit `4294967295`, no Python traceback), before its
conversation checks. Facade audit code and assets were unchanged by that work.
Dev60/Dev61 conversation tests now run immediately after compilation so these
features receive Windows coverage independently of a later facade audit failure.
The facade issue needs a Windows reproduction with native crash diagnostics if
it recurs; it is not established as a longstanding baseline failure.

Feature-pool changes must preserve the v1 identity mapping or introduce an
explicit compatibility strategy before they can change existing faces.
Animation, player portrait selection and hereditary likeness remain future
consumers rather than new simulation authority.
