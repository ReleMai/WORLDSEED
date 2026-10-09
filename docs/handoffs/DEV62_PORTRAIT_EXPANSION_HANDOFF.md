# RC14 Dev62 — Expanded portrait features

Baseline: canonical `ReleMai/WORLDSEED` main at
`385b1bc1fcded4481647e2a9aab88d6059c7e836`. Engine/package:
`1.0.0-rc14-dev62` / `1.0.0rc14.dev62`.

## Content and rendering

The v2 portrait catalog contains 202 composable feature definitions and 102
palettes. Base geometry includes 12 heads, 12 jaws, 10 ears, 14 noses, 18 eyes,
14 brows, 14 mouths, 30 hairstyles, 12 facial-hair styles, 6 necks and 13 clothing
silhouettes. New layers provide 9 tattoo motifs, 11 skin markings, 12 accessories,
9 cloth details and 6 shading styles. Palettes include 24 skin, 24 hair, 16 eye,
24 cloth, 8 ink and 6 metal color sets. Male/female weights overlap across pools.

The expansion adds distinct silhouettes such as bobs, pixie cuts, mohawks,
locs, cornrows, double braids, afros and ponytails; clothing includes hoods,
capes, waistcoats, wraps, high collars, lacing and fur trims. Eye outlines vary
by style as well as width, slant and lid geometry. Details include geometric
tattoos, freckles, moles, scars, dimples, birthmarks, vitiligo, ear/nose jewelry,
pendants and glasses. Cloth patterns and lighting planes remain separate from
the facial features, rather than replacing them with a whole-face color filter.

`presentation/portraits.py` owns immutable descriptors, versioned selection and
composition. `presentation/portrait_layers.py` paints reusable masked details.
Tattoo and skin overlays are clipped to their intended surface; foreground hair
and accessories remain separate layers. Youth, adult and elder rendering uses
the same underlying identity with age-appropriate detail changes. Clothing,
jewelry and scars are cosmetic portrait components, not inventory or injury
authority. Portraits expose no private occupation, biography or discovery state.

## Compatibility and persistence

`portrait_spec(seed, npc_uid, sex, age=30, *, version=2)` describes a face.
`portrait_catalog(version=2)` returns a detached authoring copy.
`PortraitComposer(max_entries=96, max_bytes=16*1024*1024).render(spec, size=128)`
retains the existing bounded LRU contract. Version participates in cache keys.
Catalog loading is cached for the two supported versions, and each selection
uses stable sorted IDs and an independent RNG domain per feature/palette.
Namespaces are `presentation:npc-portrait:v1` and `presentation:npc-portrait:v2`.
Rendering consumes no mutable RNG and reads no world or simulation state.

`NPCState.portrait_version` is an additive integer identity pin. Newly created
NPCs default to 2. Existing saved NPC rows missing the field load as 1; loading
copies rows without adding migration data to the caller's raw dictionary.
Explicit pins survive round trips. The save verifier accepts missing legacy
pins and integers 1/2, and rejects booleans, malformed or unsupported versions.
The app forwards this pin in both conversation and profile data; old lightweight
adapters lacking the field use v1. Save schema remains 3 and geography is unchanged.

`data/portrait_features_v1.json` preserves the exact Dev61 catalog bytes and the
v1 render path preserves its pixels. New content lives in the v2 catalog at
`data/portrait_features.json`. Tests compare 48 original descriptors and RGBA
fingerprints captured from commit `385b1bc`, including male/female/unknown and
three age stages. Existing portraits do not silently reroll when v2 is added.
Future catalog changes must retain each saved version's identity mapping or
introduce another explicit compatibility boundary.

## Validation and next work

Focused checks cover content/style validation, actual pixels for every new
feature, deterministic order/namespace isolation, all legacy fingerprints,
cache entry/memory budgets, stranger privacy, chat/profile consistency and
mixed v1/v2 SQLite checkpoint/reload. A representative mixed-version save is
verified with `tools/verify_save.py`. Complete previews show randomized adult,
youth and elder faces plus the same face with individual features changed,
including compact 64px crops. Run `python tools/preview_dev62_portraits.py` to
regenerate the checked-in `artifacts/dev62-portrait-*.png` sheets.

The final combined development check passed all 125 targeted tests in 5.2
seconds, including graphical checks without skips. The unchanged Dev31 startup
module separately passed its six tests in 79.3 seconds. Compilation, diff
validation and strict mixed-version save verification also passed. Pixel checks
distinguish all 202 feature definitions at 64px and 128px, and all 102 palettes;
all 48 legacy fingerprints and the original catalog hash remain unchanged.
All five preview sheets were visually inspected. Full manual release validation
is separate.

The preceding Dev61 automatic gate passed its conversation/portrait checks,
then timed out in the combined Dev41/Dev31 step. Logs identify four expensive
world-startup fixtures, rather than an assertion or native portrait failure.
CI now gives the unchanged Dev31 module its own bounded 180-second check and
keeps the fast social/dialogue modules in a separate 90-second check. Assertions
and test content remain unchanged; the automatic gate includes the two new
Dev62 modules early after compilation.

Player portrait selection and hereditary likeness remain future consumers.
This expansion does not add a new inventory, culture, injury or world-generation
authority beside the existing simulation.
