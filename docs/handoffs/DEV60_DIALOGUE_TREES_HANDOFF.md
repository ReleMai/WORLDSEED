# RC14 Dev60 — Deterministic conversation trees

Baseline: canonical `ReleMai/WORLDSEED` main at
`606156ab03db8cc0113b4d5b93fccc6145526aef`. Engine/package:
`1.0.0-rc14-dev60` / `1.0.0rc14.dev60`.

## Behavior and ownership

NPC speech contains structured links into detailed, layered topic trees. The
graphical panel shows underlined topic words, a clickable path, nested parent
excerpts and paged current speech. Topic navigation uses `NavigationStack`;
Esc pops one level and restores the parent's speech, response, choice and text
page. Tab focuses words and Enter follows them; arrows select ordinary replies.
Terminal speech reflows and pages with `[` / `]`, with the same keyword routes.
Action replies append to speech, keeping the original topic words accessible.

`systems/dialogue_context.py::build_dialogue_facts(ctx, npc)` reads existing
authorities into a flat scalar vocabulary. A default generated representative
with the existing economy fixture exposes 465 measured facts. Keys cover
attributes, skills, inventory, real carried copper wealth, equipment, wounds,
nutrition, languages, NPC needs and memories, household bindings, settlement
prices and shortages, housing, sanitation, border pressures, faction war,
culture, religion, weather, game time and interior presence. Missing authorities
have availability flags and safe defaults. Modded actor/town maps extend the
vocabulary without changing the selector.

`systems/dialogue_tree.py` validates and caches immutable authored content from
`data/dialogue_topics.json`. Requirements support nested all/any/not predicates
and typed comparisons. Missing facts fail closed. Applicable storylets are
ranked by priority before stable seeded tie-breaking. Every private node checks
its complete ancestor chain; directly requesting a descendant cannot bypass
trust. Unintroduced NPCs expose the existing introduction/visible-inspection
choices, and incoming private answers are scrubbed.

The catalog contains 108 authored nodes, 64 conditional storylets, 59 distinct
predicate keys and 11,138 words across base speech and variants. The existing
five main topic routes bring the total to 113. Branches extend five levels
including the root. Route IDs remain dotted, legacy-compatible UI selectors;
authored content identities use `core:dialogue.<route>` metadata.

`DialogueScene` appends `spans` and `topic_label`; `DialogueSpan(text, topic)`
preserves exact speech and topic identity through wrapping. The original scene
call remains compatible; the optional `facts` mapping supplies broader state.
The five established knowledge actions remain explicit disclosure requests;
their linked words open detailed explanatory branches through Tab/Enter or
clicks. Browsing does not discover names, grant skills, spend items or advance
game time. Gifts and knowledge disclosure retain their existing action owners.

## Persistence, determinism and bounds

No save schema or geography version changes. Conversation routes and speech are
transient and discarded when chat closes. Cycles return to a retained ancestor;
the route stack has a 24-level safeguard. Current speech is complete and paged;
parent excerpts are summaries, with the full answer retained on its route.

Explicit positive social actions share a three-game-hour reward budget, stored
as `relationships["player"]["dialogue_positive_bucket"]` in the already persisted
relationship map. Missing legacy keys default safely. Choice memories stay
bounded to 40; budget persistence prevents farming by pruning or cycling aliases.
Negative consequences remain applicable after a positive reward is spent.
RNG namespaces are the existing `dialogue` and new `dialogue.storylet`; neither
rendering nor selection consumes mutable random state.

Fact extraction uses direct actor/town bindings, the existing indexed local
NPC query and bounded map/recent-memory reads. It never prepares geography or
scans the total realized population. The legacy standing helper samples at
most 128 introduced identities. The authored catalog is cached once per process;
dialogue authoring changes require a restart to refresh it.

## Validation and next work

Regression coverage includes causal response changes, reproducibility, malformed
content, ancestor privacy gates, anti-farming round trips, observational context,
deep simulated-key navigation, stale pointer rejection, route restoration,
terminal geometry, font-exact word wrapping, clipped hit targets, resize,
keyboard focus and complete prose paging. The automatic fast gate includes
the four new dialogue test modules.

Development validation: 75 dialogue, introduction, knowledge, context, graphical
and pointer regressions passed in the bounded final run. The 22 engine/navigation
checks passed again after the final content thresholds and visible topic labels
were completed. The existing arrow/Enter and retained-menu navigation checks
also passed individually under their bounded runners. `compileall`,
`git diff --check`, a representative SQLite
checkpoint/reload and `tools/verify_save.py` passed. Root/deep actual-scene
previews are checked into `artifacts/dev60-dialogue-*.png` and regenerated with
`python tools/preview_dev60_dialogue.py`; preview generation asserts state and
inventory remain unchanged.

The introduction regression now checks that zero-duration commands leave the
clock unchanged without invoking `_advance_time`, matching the existing Dev59
realtime command boundary. The broader historical mouse/UI sweep revealed
unchanged baseline mismatches: `test_dev21_mouse_ui` still expects three stances
(Aggressive is now a fourth) and 24 player sprites (the current roster has 20).
A full `test_ui_rc2` sweep reached its 180-second development deadline while
constructing world fixtures; it was not retried with a larger limit. Focused
shared-navigation and conversation/pointer checks replace that oversized sweep
for this work unit. Full manual release validation is not claimed.

This is an authored deterministic system. Further writing can extend the same
catalog and predicates. Existing trade/attack dialogue behaviors are retained;
this change adds no new transaction, NPC combat or skill-training authority.
Specific locations and wildlife remain explicit testimony, rather than inferred
sightings from the explanatory branches. Continue with additional occupation,
culture and event-specific writing within these same authority boundaries.
