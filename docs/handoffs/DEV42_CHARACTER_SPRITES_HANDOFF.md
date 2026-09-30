# Dev42 normalized character sprites handoff

## Scope / modules changed

- Replaced the active player selections with ten new male and ten new female appearances.
- Replaced the active NPC pool with ten new male and ten new female appearances.
- Player and NPC asset paths are disjoint; none of the forty active sprites is reused.
- Added `tools/import_dev42_characters.py` and retained the four generated source sheets under `artifacts/source-art/`.
- Updated `worldseed/assets/visuals.json`, the visual regression suite, and Fast Gate coverage.

## Art generation

- Built-in image generation produced four independent 5x2 source sheets: player male, player female, NPC male, and NPC female.
- Player prompts emphasized distinctive survivor/protagonist clothing. NPC prompts emphasized ordinary professions and practical work wear, preventing player/NPC art reuse by construction as well as by manifest path.
- A background-extraction edit supplied genuine alpha before deterministic slicing and normalization.

## Public APIs / contracts

- `VisualRegistry.player_paths(sex)` returns exactly ten Dev42 player sprites for each supported sex.
- `VisualRegistry.npc_paths(sex)` returns exactly ten Dev42 NPC sprites for each supported sex.
- Every active character sprite is RGBA `160x256`, has a 232-pixel visible height, is centered at x=80, and ends at the shared y=248 foot baseline.

## Persistent fields / migration

None. Existing `player_sex` and `player_sprite_index` values remain valid because selection still resolves modulo ten variants per sex.

## RNG namespaces

None. NPC variant selection retains its existing deterministic presentation selection.

## Tests added / changed

- Added `tests/test_character_sprite_normalization.py` to enforce group counts, disjoint player/NPC paths, unique pixel content, canvas dimensions, center alignment, visible height, and foot baseline.
- Fast Gate runs the new tests with the existing NPC-sex and graphical-asset suites.
- Focused character, NPC-sex, and graphical tests pass directly and through the bounded runner; content and visual audits pass.
- A local wheel build contains all forty nested character assets.

## Performance implications

No simulation cost. The renderer loads the same class of PNG assets through the existing bounded visual cache.

## UI exposure

- Character creation shows the new player-only artwork.
- Local map rendering selects NPC-only artwork by recorded NPC sex.
- Shared centering and baselines prevent visual displacement from the actor's authoritative occupied tile.

## Known limitations

- Sprites remain static front-facing figures; directional animation is outside this work unit.
- Legacy Dev20 and `npc_rework` images remain as inactive historical assets and are not referenced by the active character manifest.

## Next dependency

Any future actor-art import must use the same normalization contract or deliberately version the renderer anchor contract.
