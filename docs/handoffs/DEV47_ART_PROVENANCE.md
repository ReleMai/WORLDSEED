# Dev47 authored art provenance

## Generation and integration

Mode: built-in ImageGen, text-to-image, `transparent_background: true`, one independent call per asset. No reference images were supplied. 49 new PNGs were copied unmodified, retaining their genuine alpha and original generated files. Renderer scaling/rotation is presentation-only. No background extraction, cropping, or raster editing was used.

The 27 shells cover every current enclosed building function plus six residence appearances. Two door leaves render and select independently. Nineteen new furnishing sprites plus the existing unique Dev46 single bed cover all 20 core furniture definitions. Exact existing custom workshop station counterparts also render indoors; unrelated execution aliases do not borrow incorrect art.

QA: `python tools/preview_dev47_buildings.py --catalog-gallery` produces the actual prepared-plan exterior view and labelled source-art sheets. Preview state is checked observationally. New PNG transparency and unique furniture/house paths have automated coverage. These are headless presentation checks, not a manual live-game playtest.

## Exact prompts

Replace `{subject}` with the corresponding table subject. Initial shell template applies to residence, residence_2, residence_3, inn, barracks, smithy; remaining shells use the second template.

### Initial six shells

```text
Use case: stylized-concept. Asset type: WORLDSEED 2D RPG building shell sprite. Subject: {subject}. Camera: orthographic near-top-down with just enough south-facing facade visible, roof closed and dominant, north at top; NOT diamond isometric. One isolated complete building centred and tightly framed inside square image. Earthy detailed hand-painted game art readable at 200px. South facade has exactly one empty dark doorway recess at bottom centre for a separately drawn door sprite; no actual door leaf. No ground, scenery, people, fences, tools outside footprint, cast shadow beyond footprint, text, labels or watermark. Genuine transparent background with clean alpha silhouette, no checkerboard drawn into image.
```

### Remaining shells

```text
Use case: stylized-concept. Asset type: WORLDSEED 2D RPG exterior sprite. Subject: {subject}. Orthographic near-top-down, closed dominant roof, small south-facing facade visible, north at top, not diamond isometric. Single complete isolated building tightly centred in square canvas. Detailed earthy hand-painted medieval game art readable at 200px. Exactly one empty doorway recess at bottom centre of south facade; NO actual door leaf (drawn separately). Genuine transparent background and clean alpha. No ground/scenery/people/exterior props/cast shadow outside footprint/text/watermarks.
```

### Furniture

```text
Use case: stylized-concept. Asset type: WORLDSEED freely placed interior furniture sprite. Subject: {subject}. Single isolated object, orthographic near-top-down view north at top, enough front face visible for depth, NOT diamond isometric. Earthy detailed hand-painted medieval RPG art, strong readable silhouette at 48px. Object tightly centred in square canvas with a little transparent margin. Genuinely transparent background with clean alpha. No room/floor/ground/other furniture/people/shadow outside silhouette/text/labels/watermark.
```

### Separate doors

```text
Use case: stylized-concept. Asset type: WORLDSEED separately clickable exterior doorway sprite. Subject: one closed medieval {door} in a matching thin {frame} doorframe, dark threshold below. Front facing orthographic slightly overhead, flat rectangular door, tightly centred, detailed earthy hand-painted RPG art readable at 32px. Genuine transparent background. No building/wall/roof/ground/people/text/shadow/watermark.
```

Wood substitutions: `{door}` = `warm oak plank door with black iron hinges`, `{frame}` = `timber`. Iron substitutions: `{door}` = `reinforced grey iron-banded oak door with rivets`, `{frame}` = `stone`.

## Saved game assets and subjects

The additional school/archive scribe station uses its own `assets/sprites/interiors/dev47/scribe_desk_piece.png`. Its exact prompt is:

```text
Use case: stylized-concept. Asset type: WORLDSEED freely placed interior school/archive scribe station sprite. Subject: one sturdy medieval oak scribe desk with a stack of bound books, open manuscript, rolled parchment, green glass ink bottle and feather quill. Single isolated object, orthographic near-top-down view north at top, enough front face visible for depth, NOT diamond isometric. Earthy detailed hand-painted medieval RPG art, strong readable silhouette at 48px. Object tightly centred in square canvas with a little transparent margin. Genuinely transparent background with clean alpha. No room/floor/ground/other furniture/people/shadow outside silhouette/text/labels/watermark.
```

Paths are relative to `worldseed/`. Registration lives in `assets/visuals.json`.

| Asset path | Subject |
| --- | --- |
| assets/sprites/buildings/dev47/residence.png | a small rustic timber cottage with pitched weathered brown-shingle roof and a stone chimney |
| assets/sprites/buildings/dev47/residence_2.png | a rounded white plaster and dark timber cottage with a steep thatched roof and small chimney |
| assets/sprites/buildings/dev47/residence_3.png | an L-shaped warm stone home with reddish slate roof and timber trim |
| assets/sprites/buildings/dev47/inn.png | a large two-storey medieval inn and tavern, timber-framed cream walls, rich dark green slate roof, two chimneys and a hanging tankard emblem |
| assets/sprites/buildings/dev47/barracks.png | a fortified low stone barracks, grey slate roofs, small battlement details and shield emblem |
| assets/sprites/buildings/dev47/smithy.png | a sturdy blacksmith workshop, dark stone walls, soot-dark tiled roof, tall forge chimney and small anvil emblem |
| assets/sprites/buildings/dev47/residence_4.png | a small round fieldstone cottage with conical dark thatch roof |
| assets/sprites/buildings/dev47/residence_5.png | a long narrow timber home with mossy shingle roof and stone hearth chimney |
| assets/sprites/buildings/dev47/residence_6.png | a compact two-storey plaster cottage with a red tile hip roof and blue shutters |
| assets/sprites/buildings/dev47/outskirt_camp.png | a modest timber bunkhouse with weathered wood roof and sheltering porch |
| assets/sprites/buildings/dev47/workshop.png | a broad timber carpentry workshop with shingled gable roof and a small saw emblem |
| assets/sprites/buildings/dev47/mill.png | a stone grain mill with timber upper storey and tan tiled roof, a millstone emblem |
| assets/sprites/buildings/dev47/fishery.png | a timber fish-processing house with blue-grey shingle roof and a fish emblem |
| assets/sprites/buildings/dev47/bakery.png | a warm stone bakery with russet tile roof, bread emblem and oven chimney |
| assets/sprites/buildings/dev47/butcher.png | a whitewashed timber butchery with dark red roof and cleaver emblem |
| assets/sprites/buildings/dev47/weavery.png | a long timber weaving hall with pale blue-grey slate roof and spindle emblem |
| assets/sprites/buildings/dev47/tannery.png | a rugged wood-and-stone tannery with faded brown tiled roof and hide emblem |
| assets/sprites/buildings/dev47/pottery.png | a small pottery workshop with ochre plaster walls, red roof and kiln chimney |
| assets/sprites/buildings/dev47/brewery.png | a stout timber brewery and bar with dark slate roof, vat vent and barrel emblem |
| assets/sprites/buildings/dev47/mason_yard.png | a stone masonry workshop with heavy grey slate roof and chisel emblem |
| assets/sprites/buildings/dev47/barn.png | a large timber livestock barn with tall warm red roof and hayloft facade |
| assets/sprites/buildings/dev47/market.png | a roofed timber market hall with green tile roof and broad covered storefront |
| assets/sprites/buildings/dev47/clinic.png | a clean plaster herbal clinic with green-grey shingle roof and leaf emblem |
| assets/sprites/buildings/dev47/watchhouse.png | a compact fortified stone watchhouse with blue slate roof and small watch turret |
| assets/sprites/buildings/dev47/shrine.png | a stone shrine sanctuary with aged copper roof and small carved sun emblem |
| assets/sprites/buildings/dev47/archive.png | a stone-and-timber archive with steep blue roof and scroll emblem |
| assets/sprites/buildings/dev47/school.png | a bright plaster schoolhouse with red tile roof and book emblem |
| assets/sprites/interiors/dev47/double_bed_piece.png | a wide medieval wooden double bed with two pillows and muted red woven blanket |
| assets/sprites/interiors/dev47/bunk_bed_piece.png | a rustic two-tier timber bunk bed with two visible straw mattresses |
| assets/sprites/interiors/dev47/small_table_piece.png | a small square wooden dining table with sturdy carved legs |
| assets/sprites/interiors/dev47/large_table_piece.png | a long rectangular timber communal dining table, empty top |
| assets/sprites/interiors/dev47/bench_piece.png | a long wooden seating bench with simple backrest |
| assets/sprites/interiors/dev47/stool_piece.png | a round three-legged rustic wooden stool |
| assets/sprites/interiors/dev47/chair_piece.png | a sturdy wooden chair with high slatted back |
| assets/sprites/interiors/dev47/wall_shelf_piece.png | a low wooden wall shelf containing a few ceramic jars |
| assets/sprites/interiors/dev47/cupboard_piece.png | a tall closed carved timber cupboard with two doors |
| assets/sprites/interiors/dev47/house_chest_piece.png | a low iron-bound wooden storage chest with closed rounded lid |
| assets/sprites/interiors/dev47/wardrobe_piece.png | a tall medieval clothes wardrobe with dark timber double doors |
| assets/sprites/interiors/dev47/writing_desk_piece.png | a timber writing desk with parchment and feather quill |
| assets/sprites/interiors/dev47/brazier_piece.png | a squat iron brazier with glowing orange coals |
| assets/sprites/interiors/dev47/house_hearth_piece.png | a rustic stone hearth fireplace with visible amber embers |
| assets/sprites/interiors/dev47/washbasin_piece.png | a ceramic washbasin filled with blue water on a timber stand |
| assets/sprites/interiors/dev47/cradle_piece.png | a small wooden baby cradle containing only cream bedding |
| assets/sprites/interiors/dev47/woven_rug_piece.png | a rectangular earthy woven rug with geometric blue and rust border |
| assets/sprites/interiors/dev47/partition_screen_piece.png | a folded three-panel timber and cloth privacy screen |
| assets/sprites/interiors/dev47/lamp_stand_piece.png | a narrow wrought-iron stand holding a glowing oil lamp |
| assets/sprites/buildings/dev47/door_wood.png | Closed oak plank doorway |
| assets/sprites/buildings/dev47/door_iron.png | Reinforced iron-banded doorway |

Retained single bed: `assets/sprites/interiors/cottage_bed.png` (Dev46 original, unique to `core:single_bed_piece`). Existing station sources remain registered under their original structure asset IDs and corresponding exact interior fixture IDs.

