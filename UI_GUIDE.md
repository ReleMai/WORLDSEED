# WORLDSEED v1.0 RC6 — terminal UI architecture

WORLDSEED's simulation can become arbitrarily deep; the control scheme must not become arbitrarily complicated with it. RC6 retains the retained screen-stack and canonical input model, and extends the UI contract to discovery-gated information, startup/pause flows, contextual adjacent interactions, and mouse/paste isolation.

## Player mental model

Normal play should require only seven concepts:

```text
WASD / arrows   move
Enter           do something
TAB             understand/manage the world
I               inventory
L               inspect space
?               help
Q               save and quit
```

Everything else is an optional accelerator. New systems should normally enter either the **Action Hub** or the **World Console**, not claim another globally required hotkey.

## Screen ownership

```text
raw terminal key
      ↓
ui/router.py          semantic Intent
      ↓
app.py                dispatch / command creation
      ↓
simulation kernel     authoritative state mutation
      ↓
ui/renderer.py        observational gameplay HUD
      ↓
ui/screens.py         observational reports/detail views
```

Supporting modules:

```text
ui/layout.py       responsive geometry
ui/widgets.py      menus, panels, pagers
ui/navigation.py   menu information architecture
ui/alerts.py       read-only causal alert projection
ui/terminal.py     platform input + presentation only
```

The renderer and report screens may **never** realize regions, advance time, roll simulation RNG, alter inventories, or write persistent state merely because the player opened a screen.

## Responsive layout modes

`compute_layout()` owns the viewport geometry.

### Wide

Used when the terminal is at least roughly 124 columns and 28 rows and dense UI is enabled.

```text
+------------------------------------------------------+---------------------------+
|                                                      | STATUS                    |
|                    WORLD MAP                         | health / needs            |
|                                                      |                           |
|                                                      | ALERTS                    |
|                                                      |                           |
|                                                      | NEARBY                    |
|                                                      |                           |
|                                                      | GEAR                      |
+------------------------------------------------------+---------------------------+
| recent event / action result                                                     |
| compact status                                                                    |
| WASD Move   Enter Actions   TAB Console   I Pack   L Look   ? Help   Q Save/Quit |
+-----------------------------------------------------------------------------------+
```

### Standard

The map owns the width. Status is moved below it. No sidebar is squeezed alongside the map.

### Compact

A minimal status line and the same essential controls are retained. Advanced information remains available through TAB.

### Tiny

Below 60×18, WORLDSEED displays a resize message instead of allowing the shell to wrap and corrupt the interface.

## No-overlap rule

A rendered frame must satisfy both:

```text
rendered_line_count <= terminal_height
visible_width(line) <= terminal_width
```

ANSI escape sequences do not count as visible width. Tests cover 60×18, 80×24, 100×30, 124×32 and 160×45.

`Terminal.present()` homes the cursor, resets attributes, writes the new frame, then clears the remainder of the old alternate-screen buffer. A shorter modal therefore cannot leave fragments of a previous longer screen behind it.

## Menus

Menus support a game-like WASD navigation model as well as arrows:

```text
W / Up          previous item
S / Down        next item
D / Enter       select / move forward
A / Esc         back exactly one UI layer
PageUp/PageDown page
Home / End      first / last
Q               optional back alias inside menus
1-9             optional quick choice on current page
```

The terminal backend canonicalizes platform-specific raw key values before UI code sees them. In particular, Windows `msvcrt.getwch()` emits the physical Escape key as the literal `\x1b` character; WORLDSEED normalizes that value to the canonical `ESC` token. Widgets defensively normalize it a second time so fake/test backends and future terminal adapters cannot silently bypass Back behavior.

Numbers are shortcuts, not the primary navigation requirement.

All menus use `ui/widgets.py::select_menu`. Feature code should not create bespoke menu loops.

## Action Hub — Enter

The Action Hub is for **verbs**:

```text
Interact
  gather
  pick up
  inspect
  inventory/storage

Survival
  eat
  equipment
  wound treatment

Work
  craft
  build
  dismantle
  farming

Combat
  attack

World
  market
  books
  magic
  vertical travel
```

A new player-action system should normally add itself here.

## World Console — TAB

The World Console is for **information, management and causality**.

```text
[!] Alerts
[@] Character & survival
[.] Local world & construction
[W] World, settlements & ecology
[$] Society, economy & politics
[*] Knowledge, religion & magic
[#] Records, chronicle & world ledger
[~] Simulation & settings
```

Each category opens a smaller second-level menu. This prevents a flat list of 15–30 unrelated screens.

## Long information

The pager reflows legacy/report output to the actual terminal width. Long records support arrows, PageUp/PageDown, Home and End. This is important because a 70-year-old NPC, artifact provenance chain or settlement ledger can legitimately become much longer than one terminal screen.

## HUD information budget

The normal map HUD contains only information useful for the next few actions:

- survival state;
- severe alerts;
- genuinely nearby actors;
- equipped gear;
- current terrain/room;
- last action result.

A distant housing shortage, trade-route ledger or century-old chronicle entry belongs in the World Console, not in the combat HUD.

## Adding a new UI feature

1. Decide whether it is a **verb** (Action Hub) or **information/management** (World Console).
2. Add navigation metadata to `ui/navigation.py`.
3. Use `select_menu`, `view_text`, and `panel`; do not create custom terminal loops unless a spatial interaction truly requires one.
4. Keep state mutation inside a simulation command/system.
5. Add an observational test for any read-only screen.
6. Add viewport tests if the feature changes the gameplay HUD.
7. Never allocate a global letter if the feature can be discovered through Enter or TAB.

## Power-user shortcuts

Direct hotkeys remain supported for frequent players, but they are secondary. `ui/router.py` is the only authoritative global key table. The module asserts that `W/A/S/D` can never collide with menu shortcuts.

## Retained screen stack

All hierarchical interfaces must use `NavigationStack` / `RouteState`. A route stores:

```text
route id
title
selected row
scroll offset
payload / record identity
```

The required navigation semantics are:

```text
push child        -> preserve parent state
ESC on child      -> pop child
ESC on root       -> dismiss feature to gameplay
replace route     -> explicit operation only
render/input      -> top route only
```

Never implement a feature by nesting blocking menus and then restarting the root menu after a child closes. That loses navigation context and is the navigation bug RC3 fixes. Parent selection and scroll must survive a child route.

`Q` may act as Back inside a modal/menu for accessibility, but only gameplay root interprets Q as save/quit.

Breadcrumbs should be derived from the stack, never manually assembled from feature-specific globals.


## Startup, pause and discovery UI

Startup is a first-class routed UI: Main Menu → Continue/New/Load/Help/Quit. New Game is a wizard rather than free-form terminal prompts. Gameplay-root ESC opens Pause; ESC inside a child UI still means Back.

UI code must respect the **player-knowledge boundary**. A screen may not display a proper NPC/town/faction/site/event name simply because the simulation model contains it. Use the simulation's `known_*` helpers/discovery collections. Unknown nearby NPCs render as Stranger.

Contextual interaction screens should prefer reachable targets (current tile + cardinal neighbors) and say what tool/action is required before failing. This is especially important for mining walls, chopping blocking trees, storage and structures.

# RC7 craft/build/food UI rules

- Group recipes and structures by player purpose, not internal file/order.
- Show `READY` or `NEEDS` before selection.
- Use readable material names and counts; hide raw content IDs.
- Detail panes explain description, time, station/tool/skill requirements and what the result enables.
- Cooking is ingredient selection with a live nutrition preview.
- Carcass processing presents only valid next operations for the selected carcass.
- Timed processing jobs must be inspectable as work-in-progress rather than disappearing until completion.
- Health UI separates immediate vitals from Nutrition & Diet history.

## RC8 custom-window presentation

The UI's information architecture remains renderer-independent. `PygameTerminal` implements the same basic present/read-key contract as the ANSI backend, so World Console, inventory, crafting, construction and other retained menu flows run inside the dedicated game window without simulation changes.

The local world view uses `present_game()` for a hybrid sprite map. Right-click maps to Back/Escape; mouse wheel maps to page movement. Future hover/click semantics must be implemented in the presentation layer and must not mutate simulation merely because the pointer moved.

`M` opens the graphical Region Map described in the RC14 Dev5 handoff. Each block represents 512 x 512 world cells. Discovered regions show their prepared plan's dominant biome and relief, regional road/trail connections, prepared water connections, and known settlements. Shared exits use their stored 0..511 offsets; the current region is outlined. Unknown regions stay dark. Missing plans are shown as uncharted, never generated by opening the map. Underground discoveries do not reveal the surface. Full-screen transitions clear gameplay hover overlays so moving the cursor cannot repaint the local view over the regional map. Dev5 lines are strategic connections; exact local road corridors and ford/bridge crossings remain Dev6 work.

Regional terrain artwork is procedural: biome symbols, moisture-dependent vegetation/color, cold tint, and relief ridges come from that region's existing terrain summary. The same region retains the same artwork when reopening or resizing the map. Road, water, settlement and player overlays remain visible above it. These atlas symbols summarize terrain character rather than marking exact local trees or mountain positions. See `docs/REGIONAL_TERRAIN_ASSETS.md` for profiles and sample asset export.


## RC14 parallel UI track — unified graphical inventory

The graphical inventory is a single retained surface rather than a pack-summary menu followed by a second carried-items menu and then a third action menu.

- Pressing **I** opens the carried-item icon grid directly.
- Selecting or hovering an item keeps the grid visible and updates an inspection pane on the same screen.
- The inspection pane shows the item icon, description, category, quantity, per-item mass/volume and relevant food/tool/weapon/equipment facts.
- Legal actions are contextual buttons on that pane. Current actions are **Use**, **Drop**, **Split amount**, and **Store** when a reachable container exists.
- **Split** is a UI quantity selector, not a second inventory authority. The authoritative inventory remains the existing item-count model; the selected amount is consumed only when a command such as Drop or Store is submitted.
- Mouse actions have keyboard parity: U use, X drop, H half/split, E store, [ / ] adjust quantity, M select all, arrows navigate items, and Esc closes the inventory.
- Item selection, hover and quantity changes are presentation state only. Drop, eat, equip, read and store still execute through simulation commands.
- The terminal backend retains the hierarchical fallback so the graphical redesign does not remove non-pygame access.
