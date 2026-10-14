# M3 shared retained-window chrome and semantic controls

Source baseline: canonical main after M2 GPU probe, `704b38bd4f4a33e644c270012af277ac66634be2`.

## Implemented

- `worldseed/ui/presentation_style.py` owns one retained-window frame painter used by the existing floating shell. Inventory, container, crafting, salvage and homestead windows now inherit the same read-only drawing primitive without separate geometry or hit-testing.
- `PointerUI._button` and the homestead button wrapper use one shared button-background painter. The established ordinary, primary and disabled styles are retained. Both call sites alone register action targets; disabled buttons cannot produce pointer tokens.
- Destructive `Remove site` and `Confirm removal` controls on the cabin depot are clearly red instead of ordinary/primary gold. The existing two-step confirmation, materials, navigation and authoritative commands are unchanged.
- Stable palette, screenshot-facing shell order, event routing, drag/resize geometry and focus remain owned by the existing renderer. No content, world generation, RNG, persistence or gameplay authority changes.

## Validation and acceptance boundaries

- Pure presentation contracts are covered by `tests.test_presentation_style` (including exact ordinary button styles, semantic disabled/danger roles and no event/display side effects).
- `tests.test_homestead_panels` also checks destructive control border pixels and original command tokens. Both remain in the existing Fast Gate.
- These changes do not claim four art scenes approved, native 1440p/4K acceleration, Windows driver coverage or completion of M3. M2 hardware experiment remains opt-in and separately measured.
- Next bounded M3 unit: shared typography/spacing/accessible focus and help across retained inventory, crafting, construction, health and conversation, accompanied by stable reference-image regressions. Preserve the existing mouse-only UI intent, WASD world movement and command authority.
