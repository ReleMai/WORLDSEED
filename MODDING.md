# WORLDSEED v1.0 RC5 — data modding

WORLDSEED's RC mod layer is intentionally **data-only**. The engine resolves manifests and loads compatible JSON data without importing arbitrary mod Python.

This makes deterministic load order, save diagnostics and security much easier to reason about.

## Directory layout

Create a `mods/` directory beside the game, then one folder per mod:

```text
mods/
  my_expansion/
    manifest.json
    data/
      items.json
      materials.json
      recipes.json
      structures.json
      crops.json
      species.json
      diseases.json
```

Only registries understood by the current loader are used.

## Manifest

Example:

```json
{
  "id": "my_expansion",
  "name": "My Expansion",
  "version": "0.1.0",
  "engine_min": "1.0.0-rc3",
  "dependencies": [],
  "load_after": []
}
```

Rules:

- `id` is a simple stable manifest ID; do not reuse another mod's ID.
- required `dependencies` must exist;
- dependency cycles fail loading;
- `load_after` participates in deterministic ordering when possible;
- duplicate protected/core content IDs are rejected rather than silently overwritten.

## Namespaces

New content IDs should use a namespace you control, for example:

```text
rele:blue_steel
rele:marsh_drake
rele:storm_temple
```

Do not define new content under `core:` unless editing the core project itself.

## Determinism

Data mods become part of the effective content set. The engine records a deterministic mod/content hash for diagnostics.

A mod should never depend on directory enumeration order or current wall-clock time to determine content.

## Save compatibility

Removing a mod from a world that already contains persistent references to its IDs may make that save invalid or incomplete. RC5 does not attempt to synthesize replacements for removed mod content.

For long-lived mods:

- keep IDs stable;
- add new content instead of renaming IDs casually;
- document removed/deprecated IDs;
- avoid changing semantic meaning of an existing ID.

## Executable mods

Arbitrary Python mod execution is deliberately outside the v1.0 RC contract. A future scripting API would need sandboxing/versioning/determinism decisions before it is safe to expose.

# RC7 data fields

RC7 expands the data contract for early-game content.

## Items

Items may define description/flavor, nutrition/macros, diet groups, utility roles, tool qualities, equipment/combat data and spoilage. A core item should have a functional use or downstream process.

## Recipes

Recipes can declare category, skill/difficulty, station, time, inputs/outputs and required tool qualities. Prefer capability requirements such as `cut`, `skin`, `mine`, `hammer`, `till` or `sew` over exact tool IDs.

## Natural resources

Resource definitions may constrain terrain, temperature, moisture, season, density/patch behavior, regrowth, tool requirements, blocking and yields.

## Species

Authored species can define habitat/climate, mass, health, group behavior, attacks and a carcass profile. Procedural species use the same runtime contracts.

## Crops

Crop definitions own growth duration, water/temperature, N/P/K consumption, disease family, seed and harvest outputs.

## Cooking methods

Cooking methods declare station/cookware/water needs, accepted ingredient roles/counts, duration and satiety/hydration modifiers. Meal nutrition is composed at runtime from ingredients.

Run `python tools/audit_content.py` before distributing a content mod.
