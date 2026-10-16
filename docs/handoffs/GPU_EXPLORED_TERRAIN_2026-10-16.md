# WORLDSEED — GPU explored terrain visibility (2026-10-16)

## Cause
The authoritative simulation already persists compact discovered tile membership and maintains current LOS separately. The software renderer uses both. The Windows OpenGL path captured discovered coordinates but omitted their terrain from the snapshot and explicitly filtered them from the ground draw pass. Previously visited exterior terrain therefore went black once out of sight.

## Change
- Live exterior capture reads only *prepared resident* terrain for currently visible and already discovered viewport cells. No unknown tile reads, generation, database access, or discovery mutation.
- Current sight keeps full-opacity terrain and authorized living props. Explored-but-not-current terrain is drawn at 0.42 opacity; no NPC, creature, resource, fire, or unentered building interior is revealed from memory.
- A read-only `show_explored_memory=False` parameter retains the existing current-sight-only presentation for future blindness effects. No blindness gameplay/status was added.
- Retain current-LOS `visible_ground_cells` metrics. The scene stays bounded by viewport caps, and exploration persistence continues to use existing discovery serialization.
- Indoor floor/room visibility remains conservative, wall-occluded, and unchanged. Persistent interior-room exploration memory would require a separately specified simulation-owned indoor discovery contract.

## Validation
Targeted regressions are in `tests/test_live_gpu_scene.py`, `tests/test_gpu_live_materials.py`, and `tests/test_gpu_main_game.py`. Check saved-world reloads using existing compact discovery and GPU main-game contracts, and review the Fast Gate outcome before considering the native Windows build verified.

## Manual Windows acceptance
Discover a landmark, walk beyond sight, confirm that ground remains recognizable but darkened. Unknown terrain stays black and hidden animals/NPCs cannot be interacted with. Save, quit, reload and revisit the sight edge. Test close to a building and an entered interior to ensure private spaces remain concealed. Use an eventual blindness status to pass `show_explored_memory=False` only during that status.
