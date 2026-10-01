# Dev46 continuous household interiors

## Scope and public behavior

Homes, inns and barracks can be entered by right-clicking a stable exterior
entrance. Existing locks, keys and invitations authorize the same portal.
Interior movement uses fixed-point coordinates (1000 units per outdoor tile
for scale only), including normalized diagonals, collision sliding and bounded
substeps. Outdoor WASD movement is unchanged. Interiors have expanded rooms,
partition walls and passable room openings. Furniture is freely positioned;
owners can right-click Reposition and left-click a location. Collision rejects
walls, overlapping furniture, occupied positions and blocked escape paths.

Residents use the same portal and collision geometry. Domestic movement/rest
runs on the existing absolute-minute NPC ticks, not rendering frames. Knocking
requests a resident's walk to the portal and exterior doorway; it neither
teleports them nor opens conversation. Indoor actors are excluded from outdoor
movement/social/render/stealth paths. Player outdoor commands are blocked inside.
Wounds, illness, needs and world time continue. Bed/chair use costs 30 minutes;
there is no zero-time repeated recovery. Dropped/death cargo stays in its space.

## Authority, persistence, performance

`interior_state.py` owns persistent plan/room/wall/furniture/pile records and
actor local coordinates; `interiors.py` owns geometry, portals and routines.
Existing WorldPos/NPC x/y/z remain exterior portal anchors, never interior cells.
Plans derive only from stable prepared settlement structures and original
fixture IDs. No additional beds, capacity, goods or economic output is minted.
Property ownership remains authoritative; guests cannot rearrange another home.
Prepared household fixtures are masked from exterior physical/render access
with their original plan records retained. Household storage remains in the
original container ledger and cannot be accessed through its exterior anchor.

Schema remains 3: additive JSON fields `interiors` and `interior_actors` have
empty legacy defaults and nested round-trip reconstruction. Geography versions
are unchanged. The save verifier checks integer/bounded geometry, references,
unique fixtures, waypoints and nonnegative pile cargo. Plans exist only for
entered homes; their geometry is bounded. A runtime per-space actor index is
reconstructed on load. Long waits retain existing coarse advancement rather
than replaying every domestic movement tick. Completed floor piles are removed
when collected. RNG namespaces: `interior-household-routine`,
`interior-household-room`; stable building and fixture identities are retained.

## Art and research

Built-in ImageGen authored floor, plaster/timber wall and transparent bed art;
final files and prompts live under `worldseed/assets/sprites/interiors/`.
Existing furniture and character art retains its content identity.
`tools/preview_dev46_interior.py` creates an observational headless screenshot
from an actual generated settlement and door admission, not a decorative demo.

Fixed bounded steps and render/simulation separation follow the principles in
[Fix Your Timestep](https://gafferongames.com/post/fix_your_timestep/).
[pygame vector documentation](https://www.pygame.org/docs/ref/math.html) informed
presentation transforms; simulation itself imports no pygame and uses integers.

## Verification and limits

57 targeted simulation, geometry, property, conversation, save and graphical
tests, a separate 65-test boundary regression, and the final 56-test
fixture/container-projection regression passed (overlapping modules),
including actual `verify_save.py` output `Save integrity: OK`.
Compilation passed. Headless render, pointer, narrow-window and observational
checks passed. This is development/integration evidence, not a full release
gate or live manual playtest.
The original dirty `D:\Codex Project\wsLIVING` checkout was preserved; this work
was validated and synchronized from the attached clean managed worktree.

This slice covers household/lodging interiors. Working workshop logistics,
interior station reservations, player-built shells, freely rotated furniture,
editable partitions and new exterior building-shell artwork remain dependencies.
Existing exterior tile shells/geography remain stable; this is not an automatic
old-world settlement layout rebuild. Interior storage retains the original
property-container authority but full indoor storage/crafting menus are pending.
