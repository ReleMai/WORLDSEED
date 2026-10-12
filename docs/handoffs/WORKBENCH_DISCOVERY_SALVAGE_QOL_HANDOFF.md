# Handoff: workshop discovery, salvage, household items and interaction QoL

## Overview
- Field experiments for workshop-only recipes return a persistent workshop hint without consuming sample items or awarding a recipe/prototype. Matching experiments at an available station discover them normally.
- Workshop discovery tabs are visible for physically reachable workshops. Crafting lists add All/Can Craft/Missing filters with smaller clickable rows.
- Salvaging supports careful three-stage disassembly with optional deterministic 5-position precision alignment, or a single-command quick salvage with low yield, no rare finds and 1 XP.
- NPC portrait clicks enlarge the existing composite without changing actor state.
- Containers retain the dual-pane inventory look and simulation-owned access/quantity/theft authority, with search and bounded batch transfers.
- Real-time clock is 3x slower than before. Standard crafting times cap at 70 in-game minutes, subject to normal skill bonuses.
- New food items: Berry Barley Bun and Hearth Root Stew, each with crafting recipe and inventory art fallback.
- New town food is an initial, once-only stock origin, then debited into new NPC household containers through the existing resource ledger; old/persisted containers are never refilled by the visual/gameplay update.

## Validation
Targeted GitHub Actions test new progression, salvage persistence, household foods, and existing UI/playtest regressions. Larger game-wide suite remains separate.
