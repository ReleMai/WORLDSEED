# Discovery, workshops, salvage and ingredient tags

The workbench now has four primary tabs: Recipes, Workshops, Discovery and Salvaging.
The redundant Item Index tab was removed; Discovery notes keep each selected material's
specific/broad tags and learned uses. Empty screens no longer render placeholder IDs as items or processes.

- Scope/modules: `ui/workbench_panels.py` owns Discovery and Workshop layouts;
  `ui/salvage_panel.py` owns the single salvage grid, component preview and attached
  inspection/three-stage minigame. `app.py`, shared widgets and pygame input connect
  the panels. Shared recipe/item details expose ingredient alternatives and tags.
- Public contracts: all three panels keep explicit selection independent of hover
  and scrolling. Scrollbars, grid arrows, world movement and companion panels follow
  the existing retained-panel contract. Salvage uses existing StartSalvageCommand /
  SalvageActionCommand; [B] begins one item and [1]-[3] choose the current stage.
  Escape preserves an active project; completion stays inline and permits the next item.
- Persistent fields/migration: optional `player_crafting_log` records successful
  experiment recipe ID, minute and physical ingredients, bounded to the newest 80
  records in memory, on save and on load. Old saves default to an empty chronology;
  their complete known recipe catalogue remains visible. Latest discovery stays
  pinned through grid edits and history scrolling until dismissed or replaced.
  No save-schema or geography-version change. Existing salvage persistence is reused.
- Recipe/content contract: optional `input_tags` consumes quantities of suitable
  carried alternatives; optional `discovery_tags` matches actual samples against
  broad/specific clues. Exact inputs and catalysts reserve their own units before
  deterministic overlap-safe tag allocation. Recipe details show accepted items
  and the concrete proposed consumption. Existing exact recipe definitions remain
  unchanged. New player recipes connect plant scraps/grasses to fiber, prepared
  plant fiber to cordage, and mixed cordage to fishing line using existing assets.
  Tagged recipes cannot enter settlement production until that owner supports
  alternative ingredients; registry and runtime guards enforce this boundary.
- RNG/performance: existing `crafting.discovery_pot.v1` namespace remains unchanged.
  Five-slot clue matching is bounded; tag allocation reads carried item types and
  at most 16 authored requirements, never world entities. Presentation draws only
  visible item cards and uses existing bounded icon/detail caches.
- Tests/validation: compileall worldseed/tools/tests and 149 targeted tests pass,
  including salvage conservation/resume/repeat/keyboard flow, observational views,
  minimum/standard layouts, overlapping ingredient/catalyst allocation, discovery,
  existing crafting/economy/water integrations and all item assets. A representative
  SQLite save containing learned chronology round-trips and passes verify_save.py.
  All 16 Discovery/Workshop/Salvage preview modes and window sizes were inspected.
- Known limitations: old saves have no historical timestamps before this change;
  older learned recipes follow recent chronological entries alphabetically. The
  complete learned catalogue is retained even when the recent 80 chronology rolls
  over. Rendering was checked using real pygame SDL surfaces, not a live play session.
  The pre-existing main fast-gate portrait fingerprint failure remains outside this
  work unit; the new focused checks pass locally. Full release hardening was not run.
- Next dependency: live play feedback on information density and minigame pacing.

Preview tools: `tools/preview_workbench_panels.py` and `tools/preview_salvage_panel.py`.
