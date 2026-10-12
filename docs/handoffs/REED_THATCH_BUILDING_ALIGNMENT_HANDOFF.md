# WORLDSEED handoff — reed beds, roofing substitutions, cabin centering

## Intent
- Surface resourcegen v5 freshwater reeds on **harvestable riverbanks, wetlands, floodplains**, and adjacent grass, rather than mostly submerged river tiles.
- Add pine boughs as a guaranteed 2–4-unit pine-felling drop, before tool/skill yield bonuses. The new item uses the existing conifer-bough visual tag until authored pine art is available.
- Group reeds, pine/juniper boughs, beachgrass, saltmarsh grass, eelgrass, rush pith and brush as 1:1 alternative roof thatching for the primitive player log cabin.
- Keep physical source items in persistent blueprint deposits, so cancelling refunds the exact materials supplied.
- Center the rendered cabin sprite over the authoritative footprint for all orientations, with the gameplay door still marked independently.

## Compatibility and authority
- Reed patches use deterministic resourcegen v5 read-time placement on **empty** feature cells, including pre-generated chunks. No historic terrain, river, seeded resource or player-built structures are rewritten.
- Resourcegen versions 1–4 retain existing behavior.
- Building placement preview, command validation, structure footprint and entrance remain simulation-owned. Sprite alignment is presentation only.
- Other crafting recipes that demand reeds are unchanged. This patch expands substitutes for the player cabin's roof requirement only.

## Validation
```bash
python -m unittest tests.test_reed_thatch_resources tests.test_homestead_blueprints tests.test_homestead_ghost_ui tests.test_homestead_art
```
Use SDL dummy video/audio for graphical tests. Additionally visually check all ten cabin variants at each rotation, shoreline reed counts over several seeds, save/reload, mixed roof deposits and full refunds.

## Follow-up
Authored pine-bough sprites can replace the shared juniper-bough fallback. Expansion of roofing material families to future buildable home types should use an explicit recipe/material-category contract rather than blindly substituting in unrelated craft recipes.
