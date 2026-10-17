# WORLDSEED — overhead clearance and interior wall types
Date: 2026-10-16

## Intent
Keep the current Windows GPU build's **already-admitted** overhead art readable when an actor sprite intersects it. Apply the same localized character cutout as mature tree crowns to public building roof shells, placed roof objects, and any other OVERHEAD instance, while preserving the existing tree behavior. Avoid global transparency, black-box roof cutaways that disclose hidden rooms, and any changes to roof/door hitboxes.

## Implemented
- `worldseed/presentation/gpu_cover_fade.py`: common, bounded cover/actor overlap policy. It returns `fade_center`, `fade_radius`, and `local_alpha` only if the viewer's body touches already-admitted per-cell cover clips. Renderer transparencies never query the world or mutate the simulation.
- `worldseed/presentation/gpu_buildings.py`: public roof shell SpriteCommands receive that local cutout. Independent door artwork and click/physical hit regions remain unchanged.
- `worldseed/presentation/gpu_scene_bridge.py`: applies the same logic to placed roof objects and other overhead layers that do not already have tree clearance. No fade for hidden viewer cells, remembered roof snapshots, or `show_player=False`.
- `worldseed/presentation/interior_wall_styles.py`: classify perimeter shell rectangles as **structural** and interior room dividers as **partition** using actual fixed-point walls and `plan.width/height`. Structural visuals use existing heavier authored fieldstone, oak-panel or limewash assets; partitions retain their `interior_materials` style. This distinction is presentation-only, with no migration.
- `worldseed/presentation/gpu_interiors.py`: immutable prepared wall-type tuples, drawn with the matching texture in live and remembered clips. Perimeter spans are selected by visible floor fragments, rather than an all-or-nothing whole-wall ray fan. Preserves exact existing LOS admitted floor scissors and keeps unvisited rooms private.
- `worldseed/systems/interiors.py`: limits the earlier PR #75 alternate-doorway apron fallback to regular buildings; homestead safety retains the original exact prepared exit.
- `tests/test_gpu_overhead_and_structural_walls.py`: tests clip authorization, local roof fade, real shell coordinates, authored wall style sources, and complete wall classification.

## Validation
Tests are registered in the bounded Fast Gate (`tests.test_gpu_overhead_and_structural_walls`), and the new rendering files trigger the Windows GPU candidate workflow. The CI workflow `38989320625` flagged a hidden-viewer safety regression; an additional patch now enforces `viewer.cell in visible_cells` for overhead fade (matching tree-authority). Check the new CI SHA, never previous failed runs, before merging this branch.

## Important invariants
- The shader only modifies the alpha of **already visible**, **already clipped** art. It cannot authorize a room, discover terrain, or change visibility rules.
- Structural and partition wall classification does not change collision, wall position, light occlusion, building supports, ownership, loot or save format.
- Saved structural snapshots remain static remembered geometry; renderer cannot read private live furniture/actors through a newly faded roof.
- Do not infer acceptance from Linux EGL alone. Once CI and the Windows binary pass, request Windows screenshots around building eaves and inside a 2-room house.

## Next review
1. Confirm roof fades ONLY where it blocks the torso near public door edges (day and night).
2. Confirm both wall styles are legible at native Windows zoom, including previously visited walls.
3. Benchmark indoor sight clipping and GPU draw passes with representative furnished homes.
4. Future architecture can separate roof/wall sprites as physical placed render objects; this pass intentionally leaves authoritative `BuildingShell` collision unchanged.
