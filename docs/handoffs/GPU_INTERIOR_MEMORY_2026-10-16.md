# WORLDSEED — Indoor explored-area memory

Indoor fog now uses a fixed, plan-local 500-unit discovery grid saved on each
`InteriorPlan.explored_cells`. The simulator alone records visibility on entry,
stair use, movement and indoor simulation updates. Saving/reloading is additive:
legacy plans default to empty exploration records and are discovered normally.

The live OpenGL interior projection preserves its existing wall-occluded,
light-constrained foreground sight. Remembered floor polygons are drawn at
42% opacity, while live furniture, piles, NPCs, stairs, lighting and interaction
hit-testing remain strictly current-sight-only. Every floor has an independent
plan UID and discovery record. Unsupported huge plans fail closed.

`show_explored_memory=False` keeps the original blacked-out view for future
blindness/darkness effects; gameplay does not yet create that status effect.

Validation gates: enter/move/save/load/return; hidden room and floor isolation;
no renderer mutation or exterior reads; GPU visibility and Windows builds.
