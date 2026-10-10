# RC14 Dev64 — Generated item art and a sorted item database

Baseline: canonical `ReleMai/WORLDSEED` main at
`e45eaf41d50663e21617faceee2eff59bd4eee39`
(freshly fetched and verified before this work). Engine/package:
`1.0.0-rc14-dev64` / `1.0.0rc14.dev64`.

Publication status: implementation and targeted development validation are
complete. The coherent Dev64 commit includes all artwork, source provenance,
sorted definitions, regenerated catalogs, UI changes, tests and documentation.

## Scope and item identity

Dev64 refreshes the existing 643-item database with a complete set of new
AI-generated inventory icons in a consistent hand-painted visual style. It adds
no items or recipes. Every existing item ID, name, asset basename, sprite tag,
gameplay tag, physical statistic and nutrition value is preserved. Runtime
sprites retain the individual `worldseed/assets/sprites/items/<asset>.png` paths.
All inventory artwork is normalized to transparent 64px canvases, including fish
whose former source sprites were 192×128. Other visual groups retain their
existing dimensions and files.

Artwork is generated through `image_gen` from explicit named-object briefs.
The import pipeline extracts those generated pixels; it does not draw substitute
objects or repaint missing icons with procedural shapes. Review remains necessary
to confirm that a generated object actually matches its assigned item name.

## Canonical classification and ordering

`worldseed/content/item_catalog.py` owns the shared category order, readable
labels, subcategory order, classification corrections and deterministic sort
key. `item_sort_key` accepts either JSON mappings or runtime `ItemDef` objects.
It orders records by category, subcategory, case-insensitive name and stable ID.
Runtime mod groups sort deterministically after core groups; core authoring and
atlas generation validate categories and subcategories strictly.

The canonical categories are resources, plants, herbs, food, seeds, materials,
medicine, tools, weapons, ammunition, armor, utility, miscellaneous finds and
special items. Plants retain wild/farmed groups, and herbs retain cooking,
medical and poisonous groups. No poisonous classification is invented for a
plant that has no corresponding authored identity or behavior.

The 204 miscellaneous finds are 180 village objects and 24 animal parts.
Their 11 groups are damaged hardware, broken woodwork, worn textiles, worn
leatherwork, broken ceramics, broken glassware, discarded paperwork, broken
stonework, damaged mechanisms, spent provisions and animal parts. Each village
group contains 18 distinct objects. The 48 wild finds remain plants or herbs.
Corn and pumpkin are farmed plants; five finished fishing lines are tools;
four reusable pottery catalysts are utility items. Healer intermediates remain
crafting materials until finished into supported treatments. Spoiled provisions
remain salvage inputs with no invented food value.

| Category | Items |
| --- | ---: |
| Resources | 11 |
| Plants | 65 |
| Herbs | 13 |
| Food | 77 |
| Seeds | 10 |
| Materials | 106 |
| Medicine | 4 |
| Tools | 83 |
| Weapons | 15 |
| Ammunition | 2 |
| Armor | 34 |
| Utility | 15 |
| Miscellaneous finds | 204 |
| Special | 4 |
| Total | 643 |

`items.json` is physically stored in this order. `ContentRegistry.load` sorts the
combined core/mod item map once at load, and the atlas builder and item browsing
screens use the same helper. Both `build_salvage_content.py` and the legacy
`build_rc7_content.py` apply canonical classification and ordering at item-save
time, after food statistics have been resolved. `sort_item_catalog.py --check`
rejects stale classification or ordering.

Inventory and crafting material browsing follow the catalog order, retain
selection and paging, and stay observational. Graphical inventory filters page
through all 14 categories rather than overflowing their panel. Category metadata
does not grant treatment, eating, combat or equipment behavior; actions continue
to use authoritative IDs, gameplay tags and physical fields.

## Generated sources and reproducible imports

`tools/prepare_item_icon_generation.py` prepares named-object briefs and ordered
sheet assignments. The generation manifest pins each source image to explicit
item IDs and grid coordinates. `tools/import_generated_item_icons.py` retains
original sheets at `worldseed/assets/source_items/dev64/<sheet-id>.png` and
records sheet and item provenance in
`worldseed/assets/source_items/dev64/manifest.json`.

Sheet provenance records the generator, prompt, source SHA-256, source size,
ordered item IDs, blank cells and reviewed grid boundaries. When artwork drifts
across rectangular cells, the importer isolates whole connected foreground
components by their expected grid centers. It retains a hashed ownership map,
component bounds and extraction parameters so adjacent objects cannot bleed into
one another. These maps partition existing source pixels; they add no artwork.
Per-item provenance
records the exact source cell, transparency-trim bounds, output dimensions,
centering offset, decoded RGBA hash and encoded PNG hash. The importer requires
real RGBA transparency and rejects empty cells, nearly opaque backgrounds,
unexpected occupied blank cells, solid pixels on cut boundaries, duplicate item
assignments, duplicate decoded sprites and mismatched asset/sprite tags. Reviewed
boundary overrides and reviewed component isolation correct drifting generated
grids without cutting through visible objects. The complete set is reviewed at
inventory size as well as against each source sheet's ordered names.

The technical transform trims transparent margins, resamples premultiplied RGBA
with Lanczos and centers the result on a transparent 64px canvas. Original
generated source pixels are retained so the final sprite can be reproduced and
verified exactly. No runtime image generation or source-sheet processing occurs
when playing the game. Legacy sprite generators preserve published generated
art by default; replacing it requires their explicit `--replace-generated-art`
authoring option.

The accepted set contains one 19-component sheet, seventeen 36-object sheets,
and a final twelve-object 4×3 sheet. Two unsuitable final-sheet attempts were
excluded from the checked-in set. All 643 objects were reviewed at native
inventory size in nine canonical contact pages. Source ownership maps prevent
neighboring objects from entering crops, and all 643 runtime atlas cells retain
the imported RGBA bytes exactly.

For the active generation manifest, the import workflow is:

```bash
python tools/import_generated_item_icons.py --manifest /workspace/scratch/dev64-generation-manifest.json --sheet <sheet-id> --validate-only --preview /workspace/scratch/dev64-review.png
python tools/import_generated_item_icons.py --manifest /workspace/scratch/dev64-generation-manifest.json --sheet <sheet-id>
python tools/import_generated_item_icons.py --verify --require-complete --report artifacts/dev64-generated-art-verification.json --review-pages artifacts/dev64-item-review
python tools/build_sprite_atlases.py --items-only
python tools/sort_item_catalog.py --check
```

The scratch manifest and review paths are session-local authoring inputs. The
checked-in generated sheets and provenance manifest are the durable source
record. Final atlases, the readable `ITEM_ATLAS.md` and item catalog must be
regenerated only after the imported sprites and finalized database agree.

## Contracts, performance and persistence

Changed modules are the item catalog helper and registry, item JSON, item browsing
presentation, classification/generation tools, source import tools, generated
art and catalog outputs, and focused regression tests. Save schema remains 3;
world generation remains 8 and resource generation remains 5. Geography, crop
placement, species, recipes, salvaging yields and item quantities are unchanged.
There are no new persistent fields, save migrations or simulation RNG namespaces.

The shared registry sort runs once when content loads. UI work remains bounded by
the visible inventory/catalog page. Reusing stable individual sprite references
keeps the existing runtime loading contract. Generated source sheets are offline
authoring evidence, not a second runtime or simulation authority.

## Validation record and next dependency

Completed targeted development validation:

- Full provenance verification: 19 retained source sheets, 643 imported/catalog
  items, 643 unique decoded pixel hashes, exact source-pixel reproduction passed.
  Durable report: `artifacts/dev64-generated-art-verification.json`.
- Native-size visual review: all 643 objects across nine pages, with complete
  labels and stable IDs. Index: `artifacts/dev64-item-review/README.md` and
  `dev64-items-review-index.json`. Full catalog: `worldseed/assets/ITEM_ATLAS.md`
  and `item_catalog.png`; runtime atlas includes all 643 items in 26 sections.
- `dev64-final-regressions`: **76 tests passed**, 5.365s test time / 6.5s bounded
  runner time. Modules: item asset catalog, item database, generated item icons,
  craftable sprite coverage, salvaging UI, crafting pot UI, crafting expansion,
  fish/container sprites and tabletop art; selected UIRC4 input, stance routing
  and graphical asset checks. Pygame checks ran using the dummy display backend.
- Content audit passed: 643 items, 324 recipes and 252 salvage inputs. Visual
  audit passed: 1,307 unique manifest assets, 20.1s bounded runner time.
- Canonical sort check, full Python compilation and `git diff --check` passed.
  A HEAD comparison confirmed that every item field except category/subcategory
  is unchanged. Inventory/category browsing covers all 643 items without state
  mutation, and every source, ownership map and output hash is checked by CI.

The automatic fast gate now runs `tests.test_item_asset_catalog`,
`tests.test_item_database` and `tests.test_generated_item_icons` together under
its existing bounded runner. This is targeted development validation; the
comprehensive manual release suite and long simulation matrices were not run
for this artwork/catalog update. No implementation dependency remains.
