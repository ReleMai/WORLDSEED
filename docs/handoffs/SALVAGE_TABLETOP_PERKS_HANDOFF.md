# WORLDSEED — Interactive Salvaging (tabletop protocol v2)

## Integration
- Main authoritative system: `worldseed/systems/salvaging.py`
- Minigame definitions and deterministic component interactions: `worldseed/systems/salvage_games.py`
- Skill trees, prerequisites, spending, refunds: `worldseed/systems/salvage_perks.py`
- Graphical controller and independent draggable panel: `worldseed/ui/salvage_panel.py`
- Command mediation: `StartSalvageGameCommand`, `SalvageActionCommand`, `QuickSalvageCommand`, `SalvagePerkCommand`, `ResetSalvagePerksCommand`, `ResearchSalvageDossierCommand`.
- Save format extends existing state with `player_salvage_perks`, `player_salvage_respecs`, and `player_salvage_dossiers`.

## Minigame types
1. **Disassembly Bench** (unfasten, carve, sort): inspect joints; select connection; release supports before dependent joints; use Unfasten, Wedge or Cut.
2. **Fracture & Extraction** (crush): select fracture regions based on public visual cues; use Tap, Wedge or Firm Strike; incorrect force damages materials.
3. **Material Recovery Table** (strip, clean): inspect fabric/organic layers; Unpick, Wash, Dry or Cut; sequence dependent layers.

Each board contains four or five deterministic component challenges. Players can inspect individual components to reveal the safest tool for extra in-game minutes. All selection and action mutations are server-authoritative. The puzzle is seeded once at the time of source reservation; reopening the UI or saving/loading cannot reroll it. Successful completion returns a 0–100 quality result and rolls the existing deterministic catalog loot table once.

**Legacy compatibility:** Existing version-1 three-choice sessions are still resumed and finished unchanged. The standard mouse-driven salvaging window launches version-2 jobs. The original legacy/terminal commands remain available.

## Perks and progression
Each level from 1 to 10 earns one spendable point. Each tree has five levels with unlock gates 1/3/5/7/10. Players can mix paths within 10 total points:
- **Precision:** Seam Sense → Steady Hands → Intact Recovery → Gentle Undo → Conservator.
- **Scavenging:** Fast Hands → Sorted Scrap → Sweep Job → Makeshift Rig → Wreckbreaker.
- **Ingenuity:** Tell-Tale Marks → Workshop Whisper → Notes From Ruins → Targeted Search → Lost Arts.

One free reset on existing/new saves, with additional tokens at Salvaging levels 5 and 10 (maximum three banked). Workshop dossiers require three distinct pristine salvage sources, and discoveries only resolve at an actually reachable workshop. Field hints do not reveal workshop recipes.

## Player verification
1. Open the Salvaging window from Crafting and check that it is an independent movable/resizable window.
2. Choose wooden/metal, brittle and textile sources; each should show its distinct material board with clickable parts.
3. Close during work, save/reload, and reopen. The identical reserved source, component progress, survey clues and condition should remain.
4. Try disallowed actions, selecting locked joints, and repeated completion; ensure no extra resources are minted.
5. Open Skill Perks, purchase tier 1, verify tier/level gating, unlock an action and exercise it in-game.
6. Try batch salvage with Scavenging, preserve high-quality rare parts with Precision, and record a workshop dossier with Ingenuity.
7. Test a legacy saved version-1 unfinished salvage job for safe resumption.

## Validation
`python -m unittest discover -s tests -p "test_salvage_tabletop.py" -v`
`python -m unittest discover -s tests -p "test_salvaging.py" -v`
`python -m unittest discover -s tests -p "test_salvage_panel.py" -v`
`python -m unittest discover -s tests -p "test_salvaging_ui.py" -v`

CI: `.github/workflows/salvage-tabletop-check.yml`

## Follow-up balancing
- Tune material-specific target density, operation fatigue, and stronger cascading fracture/fiber damage.
- Observe UX on minimum (800×520) and standard (1280×800) windows, especially tooltip overlap.
- Broaden discovery dossier recipe eligibility and notebook presentation.
- Add fully authored material-specific illustrations and optional tool audio, while keeping gameplay independent of assets.
