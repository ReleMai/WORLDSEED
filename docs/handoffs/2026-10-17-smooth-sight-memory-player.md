# Smooth visibility, interior memory and player readability

Baseline: main c2b96f3337be6214162926c0ebe893b9635ef3ba.

## Scope and public behavior

- Replace the indoor black fog strip overlay with inward feathered coverage on admitted sprites. Live floor blends into an equally graded remembered underlay; matching opacity prevents a second stepped seam at the live/memory boundary.
- Add a bounded shared sight-mask texture to SpriteCommand and the GL sprite shader. It can only attenuate existing authorized clips. CPU masks are capped at 256 x 256 with four cached pixel arrays; GPU residency retains the existing LRU budget. Fully opaque floor patches omit the mask work.
- Restore outdoor radial fading in the actual game viewport and feather the explored/unknown outline. Keep old per-tile edge shading disabled. Shift both mask coordinates and radial centers with the HUD viewport.
- Give remembered interior floor its own bounded 1,024-patch allowance instead of subtracting live patches from that allowance. A busy live view no longer leaves zero budget for saved rooms. Discovery remains on the existing gameplay movement/observation path.
- Draw the complete player sprite last, independent of floor LOS clips, walls, roofs, furniture and darkness. This self-visibility exception grants no NPC, terrain or room knowledge. The model provides a player-shaped reveal through overlapping art.
- Preserve roof artwork behind that player when the circular transparency would expose an empty, withheld floor buffer. Use the existing local transparency where admitted ground provides a backdrop. This prevents a black circular cutout without inventing a private interior.
- Fade the Alt-held outdoor radius overlay in over 180 ms and out over 250 ms. The fade can reverse continuously; idle animation reuses the captured scene, without simulation time, discovery changes or extra UI uploads.
- Group constant indoor darkness by opacity before command construction, reducing command preparation overhead. Shift each shared mask only once per viewport update.

## Persistence and authority

No persistent fields, migration, RNG namespace, world-generation, collision, NPC admission or key-routing changes. Existing remembered walls, floor details and last-seen furniture continue to use their saved data. No renderer performs observation or terrain generation. W/A/S/D remain movement keys.

## Validation

- Compileall for worldseed, tools and tests; diff whitespace check.
- 104 affected tests completed with five optional graphics-backend skips. An initial invocation included a nonexistent test module; the corrected invocation passed.
- After final shade grouping and viewport changes: 52 targeted tests completed with three optional EGL skips.
- Native Windows SDL/OpenGL main-window interior and focus/input tests passed on RTX 4060 Ti. A new native Alt animation test passed and verifies no idle scene recapture or authoritative mutation.
- New regressions cover mask bounds/caching, exact unknown-pixel exclusion, softened stair-edge pixel values, full player body clipping/order, memory surviving a full live tile budget, and reversible Alt timing.
- Actual interior move_player calls in the prepared fixture retained 659 remembered patches alongside 336 live patches and 265 saved coarse cells. The player remained the final draw command. Screenshots inspected under docs/evidence/smooth-sight-player.
- Corrected the benchmark screenshot export to read already-blended RGB. Memory alpha is a renderer classification channel, so alpha-compositing it again incorrectly erased remembered pixels in exported images.

## Performance and limitations

Native offscreen 960 x 640, 90-frame trace: median capture 12.998 ms, preparation 10.304 ms, synchronized draw 3.518 ms, total 27.119 ms, p95 total 28.744 ms, median 33 draw calls, 501 final-frame commands, 21,149,100 resident texture bytes. The previous pass measured 24.039 ms median total: the continuous masks/underlay add about 3 ms in this trace. This is a visual-quality tradeoff, not a claim of higher interactive FPS.

Unknown silhouettes are conservatively feathered inward; no unseen cells are added to round their outline. Explored memory retains the shape of observed space, rather than becoming an unrelated perfect circle. Large modded interiors still have bounded rendering budgets. Native fixtures and main-window tests ran; the user's specific save was not available for reproduction. Next check is player feedback on the Windows build at their viewport/zoom.
