# WORLDSEED RC14 Dev41 — Real-Time Social World

## Scope / modules changed

- `worldseed/sim/realtime.py` converts bounded monotonic wall time into authoritative game-minute advances.
- `worldseed/sim/engine.py` exposes `advance_realtime()`, keeps ordered simulation boundaries, and makes conversations command-time neutral.
- `worldseed/ui/terminal.py`, `worldseed/ui/pygame_terminal.py`, and `worldseed/app.py` pump active simulation while the player is idle or using non-pause menus.
- `worldseed/systems/dialogue.py` adds nested area, personal, and relationship topic trees with deterministic responses and bounded social gains.
- `worldseed/systems/property_intrusion.py` adds knocking, physically-present responders, threshold conversations, and temporary invitations.
- NPC profile/dialogue presentation now shows personal and derived community relationship information.

## Public APIs / contracts

- `RealtimeSimulationDriver.pump(now=None) -> int` advances complete game minutes and caps foreground catch-up after a stall.
- `Simulation.advance_realtime(minutes)` is the simulation-owned continuous-time entry point.
- `Simulation.begin_conversation(npc_uid)` starts the same authoritative knowledge/relationship path used by adjacent talk commands.
- `PropertySecuritySystem.knock_on_door(...)` returns `invited`, `door_talk`, `unanswered`, or an error outcome.
- Movement and conversation no longer advance the clock. Explicit duration actions such as waiting, crafting, gathering, and rest retain their authored fast-forward durations.
- The pause menu pauses the real-time driver. Dialogue, inventory, maps, and other active-play panels do not pause the world.

## Persistent fields / migration

- `DoorSecurityState.guest_access_until` stores sparse actor-to-expiry invitations in absolute game minutes.
- Missing invitation data in older schema-3 saves defaults to an empty mapping; no schema migration or world-generation version change is required.
- Expired home invitations are pruned and intact residence entrances are relocked by the existing scheduled property update.

## RNG namespaces

- Existing `dialogue` and `area-willingness` namespaces remain in use.
- Knocking uses relationship, trait, crime, time, and persuasion state without adding random rolls.

## Relationship and knowledge behavior

- Dialogue uses NavigationStack-backed topic branches rather than one flat response list.
- Listening and personal conversation improve trust, affection, and familiarity at most once per choice per three-game-hour bucket.
- Food/drink gifts transfer a real carried item into the NPC's authoritative inventory; needed gifts have stronger social effects.
- Region information checks personal trust, familiarity, derived community standing, personality guardedness, occupation, and player persuasion.
- Settlement standing is a read model derived from known player relationships with living residents, not a second reputation authority.

## Performance / LOD

- The input heartbeat checks at short bounded intervals but only invokes simulation when a whole game minute accrued.
- Foreground catch-up is capped at five game minutes. Long absences remain owned by offline advancement.
- Nearby NPCs continue to use existing Tier-A physical pathing and stable doors; distant populations retain aggregate cadence.

## Tests added / changed

- `tests/test_social_realtime_phase.py`: wall-clock conversion/cap/pause, boundary-safe vitals, nested dialogue effects, invitation persistence, and guarded doorstep conversation.
- `tests/test_dialogue_movement_phase.py`: new root topic contract.
- `tests/test_dev31_playtest_fixes.py`: movement no longer advances world time.
- Existing property security and NPC scheduling tests remain part of the targeted gate.

## Known limitations / next dependency

- The one-second-per-game-minute scale is currently a code constant rather than a settings slider.
- Direct NPC combat remains outside the current combat authority.
- Doorstep conversation does not animate a resident walking to the door; it requires the resident to be physically inside and presents the conversation immediately.
- Profession effects retain their existing hourly/coarse cadence so continuous locomotion cannot duplicate economic output.
