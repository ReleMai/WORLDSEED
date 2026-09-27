# Inventory and context UI handoff

The graphical inventory and container panels now use a warmer framed surface, clearer item slots and hover feedback. Storage shows mass and volume capacity gauges. The world right-click menu and item action menu use the same compact button panel, opening from the click point with a 145 ms ease-out. Button hit regions are registered at the final position, including when the menu is clamped against a window edge. The quantity label in the narrow inventory detail pane has been shortened to prevent overlap.

- Scope: `worldseed/ui/pygame_terminal.py`, `tests/test_dev37_floating_interaction_ui.py`.
- Simulation/save contracts: unchanged. Rendering and popup animation are observational; existing action tokens still dispatch through the menu widget.
- RNG and persistence: none.
- Verification: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYTHONPATH=repo python -m unittest discover -s repo/tests -p test_dev37_floating_interaction_ui.py -v` (9 passed); compileall of the changed files passed. Inventory and natural-container layouts were rendered and visually inspected at 1280 × 800.
- Performance: one 145 ms opening animation on a new menu, no continuous animation or additional simulation work. Repaints keep the menu open without replaying its opening animation.
- UI: floating panels retain drag, resize, filtering, item transfer, quantity controls, keyboard selection and Esc; the context menu preserves click actions and location labels.
- Known limit: the terminal backend keeps its existing text presentation. No new assets are required.

## Local HUD redesign

- Scope: `worldseed/ui/pygame_terminal.py`, `worldseed/ui/router.py`, `worldseed/app.py`, `tests/test_ui_rc2.py`, `tests/test_dev21_mouse_ui.py`.
- The world footer now shows up to five recent simulation log entries and the latest player action in a compact activity panel. Rendering reads existing log messages; it never creates events or advances time.
- The right sidebar retains player, weather and nearby context above a grid of ten vector icon buttons. Every button uses its existing global key token. Hovering for 1.2 seconds shows its name, purpose and shortcut; the tooltip restores the underlying sidebar pixels on exit.
- Normal, Stalk and Crouch are explicit movement stance buttons. They route through the existing `SetHuntingStanceCommand` and simulation log. This changes the authoritative movement stance; it does not add a second movement-speed state or alter saves.
- No asset, RNG, worldgen, migration or persistence changes. The icon and hover layers use bounded drawing and no simulation queries. Narrow windows clip the status section above the action bar, while keeping all ten actions and three stances visible.
- Validation: compileall; HUD click and observational integration test (passed with missing cloud artwork isolated in the scratch checkout); minimum/standard viewport hit-region and 1.2-second tooltip test; stance intent regression test. The final game frame was visually inspected at 1280 x 800.

## Centered menus and character art

- Scope: `worldseed/ui/pygame_terminal.py`, `worldseed/ui/pointer.py`, `worldseed/assets/visuals.json`, `worldseed/assets/sprites/characters/npc_rework/`, `tests/test_dev21_mouse_ui.py`.
- Ordinary graphical menus use a centered card over a cached forest/mountain scene with bounded drifting light motes. The shared chrome gives console, feature, document and appearance screens the same palette and header motion; floating/context panels retain their own window geometry and live-world backdrop. Unneeded Back/Previous/Next buttons are hidden on the main menu and unpaged menus.
- A software-drawn gold cursor with a pulsing ring is active in menu/text-entry modes. Its underlying pixels are restored on movement; native cursor returns in world mode and at shutdown. Menu animation uses wall clock only and never reads or mutates the simulation. Context overlays preserve live weather animation behind them.
- A distinct authored NPC roster has 12 male and 12 female transparent sprites, each 100 x 144 pixels, sourced from two generated 4 x 3 atlases. Three new male and three new female looks replace the first three player-appearance paths without changing the stable 10-choice picker or the stored appearance-index schema. Existing saves whose appearance index is 0-2 display the refreshed look at that index. NPCs have no recorded sex field; their visual variant is still chosen deterministically by stable NPC identity across the full mixed roster.
- Validation: 14 graphical pointer/menu tests passed, including centered 800 x 520 / 1280 x 800 layout, cursor movement, roster alpha and paging; two floating/context animation-state tests passed; compileall and JSON parsing passed. Menu images were visually inspected at both viewport sizes. The full pointer test in this scratch checkout isolated the missing newer cloud artwork, which is unchanged in GitHub.
- No simulation, save schema, RNG or world generation changes. Menu scene cache is per window size and cleared on resize; sprite files total about 400 KB.

## NPC sex persistence and sprite routing

- Scope: `worldseed/systems/state.py`, `worldseed/systems/names.py`, `worldseed/presentation/visuals.py`, `worldseed/ui/pygame_terminal.py`, `worldseed/assets/visuals.json`, `tests/test_npc_sex.py`.
- `NPCState.sex` is persisted as `male` or `female` through the existing state serialization. When an older NPC row lacks this field, dataclass construction assigns it deterministically from an unambiguous existing given name or a stable digest of NPC UID for ambiguous/new names. Existing UID, name, location and world-generation RNG are not changed. An explicit valid saved sex is preserved.
- The manifest labels all 24 authored NPC sprite paths with sex. `VisualRegistry.npc_paths(sex)` filters the existing roster, while no-argument `npc_paths()` remains compatible with galleries and audits. The renderer chooses a stable variant inside the NPC's sex group.
- New settlement representatives and children receive sex at NPC construction without changing name RNG consumption. Existing save rows gain the field on read and store it on the next normal save; no database migration or worldgen version bump is needed. Family pairing and birth rules still use their existing behavior; a later family-simulation phase can consume the new field explicitly.
- Verification: three NPC sex/migration/visual tests, the existing society determinism test, and the existing save round-trip test passed; compileall and manifest JSON parsing passed. No new assets, new RNG namespace, database schema, or unbounded render work.
