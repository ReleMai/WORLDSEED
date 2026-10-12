# WORLDSEED RC14 — Health attrition, combat log, and centered cabin placement

Baseline: `bc8b5504a3de72e17ce975b093f6cae682398936` (main).

## Root-cause findings

- `Simulation._update_vitals` previously applied starvation, dehydration,
  low blood volume, and extreme-temperature damage **on every invocation**.
  Realtime invokes vitals with one game minute, making attrition up to sixty
  times faster per game-hour than a once-per-hour rule; even zero-minute
  calls could drain health. This explains HP loss with full visible needs
  when temperature or blood were critical.
- `_handle_death` reset HP/hunger/thirst/blood but did not reset
  `body_temp` or `player_infections`. A replacement character could inherit
  the deceased person's fatal temperature and ongoing infection.
- The world activity footer showed general events only, without a durable
  breakdown of damage and attackers.
- The log-cabin ghost and placement click treated the cursor tile as the
  upper-left corner of the 3x3 blueprint rather than the footprint center.

## Changes

- Health attrition now applies once per *crossed game hour* (scaled for
  multi-hour advances). Zero-minute actions inflict no ambient HP attrition.
  Swimming exhaustion retains the existing five-minute exertion cadence.
- On succession, reset body temperature, blood, wounds, infections, immunities
  and fractional coordinates; preserve gear drops and legacy/death history.
- Record structured damage on the simulation, never renderer: incoming animal
  hits, outgoing melee/ranged/bash, bleeding, collisions, traps, disease,
  starvation, thirst, temperature, low blood, swimming, and falling roofs.
  Keep a bounded 240-entry record serialized in living-world state.
- A mouse-clickable Combat Log tab appears beside Events inside WORLD ACTIVITY.
  Damage rows expose clock, dealt/taken, HP, source, damage type, and body part.
  Health warnings for critical body temperature, low blood, and active infection
  appear on the HUD.
- The same centered blueprint anchor is used for both ghost preview and click
  placement, preserving the model's authoritative door positions.

## Validation plan

- Run focused deterministic vitals/respawn tests, ghost pointer tests, and
  graphical footer tab test on Windows SDL dummy display.
- Existing Dev62 legacy portrait fingerprint failure may still fail a later
  unrelated fast-gate step; record the actual failing step separately.
- Manual Windows desktop playtesting and checking historical save behavior
  remain necessary.
