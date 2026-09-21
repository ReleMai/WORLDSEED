# Dev21 — Mouse-driven controls

Scope: shared widgets, pygame input/presentation, pointer target helper, startup controls, regional-map close control, HUD route definitions, bounded targeting and app close/save handling.

Controls:
- WASD moves the character in the world only. It cannot change menu selection or activate a menu action.
- Ten persistent HUD buttons: Inventory, Crafting, Build, Health, Map, Actions, World, Look, Help, Pause. World and Actions expose the remaining systems; Pause contains save/quit and access to the console.
- Menu cards activate on left-click. Hover selects without activation. Wheel and Previous/Next page lists; Back, right-click or Escape returns. Arrow/Enter navigation and numeric shortcuts remain optional.
- Wheel zooms only in world mode. UI/text/target modes never change world zoom.
- Appearance tabs/cards, character point-buy +/- controls, talents and confirmation buttons are clickable. Names/seeds still use keyboard text entry; WASD letters are accepted normally there.
- Direction prompts are clickable menus. Look, gather and hunting target modes accept map tile clicks and Confirm/Cancel buttons, with existing range/discovery limits preserved.

Contracts: `ui/router.py` owns HUD shortcut mappings. `ui/pointer.py` owns transient screen-space hit regions, mode changes, button rendering and page capacity; no simulation mutations occur there. Shared widgets interpret page-relative UI_SELECT/UI_HOVER tokens and retain selected route state. Hit targets rebuild every frame and invalidate on resize. Backend page capacity prevents invisible selectable cards. Static decorative tabs were replaced by location labels so they no longer appear to be dead buttons.

Safety: entering a modal screen or losing window focus clears held movement. Window close inside UI raises a typed request to the app boundary, which saves the active world and closes its database. Startup window close exits cleanly. Rendering/hover/scroll are observational.

Look detail also used an undefined width variable; it now derives width from the active display.

Persistence/RNG: no new persistent fields, migrations, generation versions or RNG streams. No new runtime dependencies beyond the existing pygame-ce.

Validation: see DEV21_VALIDATION.md and artifacts/dev21_* logs/screenshots. Tests cover actual SDL mouse events, exact hit selection, hover-only behavior, paging/selection retention, small-window bounds, stale targets after resize, typing, mouse creation controls, nested crafting/inventory routes, held-key clearing and modal close/save.

Limitations: keyboard text entry remains required for names/seeds; terminal fallback uses arrows/Enter/Escape. Existing gameplay/recipe discovery rules and static art remain unchanged. The old zero-supply bootstrap harness still bypasses normal discovery and attempts a locked recipe.
