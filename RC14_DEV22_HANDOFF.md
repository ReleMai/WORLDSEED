# Dev22 — authoritative terrain atlas

## Scope and root cause

The old gameplay region map converted a regional biome summary into decorative
terrain art and joined river exits to region centers. Those pictures were not
the local terrain. The graphical Map route now uses `world/atlas.py` and
`ui/atlas_map.py`, projecting actual stored/local tiles. The former schematic
renderer is retained only as a compatibility/tooling helper, not used by gameplay.

## Controls and presentation

- Map HUD button / M opens a 512-cell-wide surface atlas around the player.
- Mouse wheel or Zoom buttons select 128, 256, 512, 1024 or 2048-cell views.
- Click pan buttons or use arrows; Center returns to the player. WASD is unchanged.
- Click terrain to inspect its exact cell ID/name/coordinates; click POIs or their
  list entries for names, location and type. The list is pageable. Overlapping
  icon buckets suppress visual clutter without dropping list records.
- Back, right-click, Esc, M or Enter closes. Resize preserves center/zoom.
- Small and large window screenshots and a reproducible QA preview script are
  included. Preview settlements are explicitly labeled synthetic fixtures;
  their terrain comes from the real v7 generator.

## Authority and public API

`read_atlas(sim, center=None, span=512)` returns a bounded `AtlasSnapshot` with
chunk terrain and known `AtlasMarker` records. `terrain_at(x,y)` is exact for
available surface cells. Negative coordinates use the same floor division as
local chunks. Source priority: loaded local chunk, otherwise version-matching
stored base plus saved deltas, then current dirty edits.

No atlas read loads/generates chunks, advances time, realizes settlements,
invokes hydrology, changes LRU ordering, writes the database, or advances simulation RNG.
One paused UI snapshot/raster is cached per map session and replaced on pan/zoom;
opening the map again refreshes live state. Maximum span 2048 bounds chunk probes
to 65 x 65 and the render raster to 512 x 512. At distant zoom, cell colors are
area-averaged; terrain inspection still reads exact cells.

Known settlement records provide village/city markers (population >=1000 is a
presentation size class, not a newly simulated city). Camps are existing known
campfires/shelters, grouped per 8-cell block. Cave icons require a discovered
surface cave tile. Historical site archetypes are read from known site records;
underground markers explicitly show depth and approximate chunk-center location,
not an invented surface entrance. No POI exists merely because art was supplied.

## Persistence, compatibility and limits

Save schema stays 3, worldgen stays 7, no new simulation fields or RNG namespaces.
Versions 1–7 read their own tiles without migrating geography. Generated chunks
are now retained in the existing rebuildable database cache when first locally
materialized, before authoritative terrain deltas are applied. This prevents
explored coverage from disappearing after LRU eviction. Normal save/commit owns
durability; inspection never writes. Cache growth follows generated/explored space.

Uncharted regions and unavailable/deleted base caches remain dark. The atlas does
not fabricate a full region from a few samples or regenerate an old save on open.
Revisiting missing terrain through normal play restores coverage. This is an
honest partial survey, not a claim that every possible infinite seed is exhaustively
tested or that all ungenerated regions are visible. Roads are not drawn as fake
straight-line connections; a future overlay should consume authoritative route
geometry. Underground floor mapping remains a future feature; this is a surface
atlas with known underground-site projections. Terminal mode retains its report.

Future/modded terrain IDs use the registry tags and a visible fallback color;
all surface core terrain IDs have explicit palette coverage in atlas_styles.json.
The full suite also exposed an existing catalog-dependent ruin-wall blending
inconsistency. The dynamic catalog now excludes authored ruin masonry from
terrain feathering, matching the existing hard-edge tests.

## Art

Nine new built-in image-generation POI illustrations are packaged in
`worldseed/assets/atlas_poi.png`, with a data-driven 3x3 layout in
`worldseed/assets/atlas_styles.json`. The renderer slices and alpha-trims cells
at load time; no Pillow or other runtime dependency was added.

Generation prompt: a transparent-background square atlas, exactly nine isolated
icons in an equally spaced 3x3 grid: village (three timber thatched cottages),
walled city (slate roofs inside stone walls), camp (canvas tents and fire), cave
(natural rocky arch), ruined fortress, temple, timber mine mouth with pickaxe,
ancient archive with scroll emblem, crypt mausoleum. Cohesive professional
hand-painted cartographic miniatures, elevated three-quarter view, readable at
32 pixels, moss green/ochre/ivory/slate/brown, top-left lighting, fine dark contour,
large cell padding, no labels, grid lines, lettering, scenery or framing,
genuine transparent alpha. Asset creation used the built-in image tool.

## Validation

See `DEV22_VALIDATION.md` and artifacts/dev22_* test logs. Includes seed/version
tile identity, negative coordinates, discovery filtering, generated-cache reload,
delta precedence, observational checks, mod fallback, real SDL clicks/hover,
paging/zoom/pan/inspection and narrow/large window coverage.
