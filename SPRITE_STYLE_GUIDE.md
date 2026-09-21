# WORLDSEED Sprite Style Guide

## Direction

Sprites use grounded, readable pixel art rather than bright iconography. The target is a rugged simulation-game aesthetic: earth tones, limited highlights, clear silhouettes, and enough internal detail to distinguish function at small sizes.

## Base sizes

- terrain: 32x32 opaque tile
- item: 32x32 transparent icon
- crop: 32x40 transparent, 3 growth stages
- resource: up to 48x56 transparent, bottom anchored
- structure/furniture: 48x48 transparent
- animal: 56x48 transparent
- NPC/player: 32x48 transparent
- atlas cell: 64x64

The renderer scales using nearest-neighbor presentation logic and bottom-centers objects that are taller than one logical tile.

## Readability rules

1. silhouette first — an axe should read as an axe before color is considered
2. category does not imply identical shape — oak, pine, birch and willow are different
3. color supports identity but is not the sole differentiator
4. one-pixel highlights are allowed where they improve material reading
5. drop shadows are presentation aids only and stay subtle
6. transparent background for non-terrain assets
7. no visual detail may imply a mechanical property the item does not have

## Variation

Each authored animal species has four deterministic variants. Variants may alter coat shade, marking detail and small body accents without changing hitbox or species identity.

NPCs currently use 32 visual variants combining several skin tones, hair colors/styles and clothing palettes. NPC visual selection is deterministic from stable identity, so reloading a save does not change appearance.

## Data contract

`worldseed/assets/visuals.json` maps content IDs to sprite paths. Runtime code requests content IDs, not filenames.

A future hand-painted sprite can replace a generated file at the same path without changing simulation or save data.

## Quality gate

Run:

```bash
PYTHONPATH=. python tools/audit_visuals.py
```

The gate requires visual mappings and valid files for every item, terrain, natural resource, structure, crop and authored species, plus a minimum NPC variation pool.
