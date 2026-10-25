# WORLDSEED project memory

This is a navigation surface over the canonical repository documentation.
Open the repository's `docs` folder as an Obsidian vault. Start with the
[documentation index](../../README.md) and [development workflow](../DEVELOPMENT.md).
The [root AGENTS.md](https://github.com/ReleMai/WORLDSEED/blob/main/AGENTS.md)
is the coding contract; read its local checkout before changing code.

## Find the relevant evidence

| Work | Starting point |
| --- | --- |
| Current handoffs | [Documentation index](../../README.md#current-handoffs) |
| Generated item art and provenance | [Dev64 handoff](../../handoffs/DEV64_ITEM_ART_DATABASE_HANDOFF.md) |
| Current GPU controls and weather | [Dev65 handoff](../../handoffs/DEV65_GPU_RECOVERY_2026-10-22.md) |
| NPC/job experiments | [Simulation lab](../NPC_JOB_LAB.md) |
| Physical settlements | [Settlement redesign](../SETTLEMENT_INTERIOR_REDESIGN.md) |
| Tool connections | [Memory and Context7 setup](../MEMORY_AND_CONTEXT_SETUP.md) |

Check dates, superseding notes, and the current code before applying a historical
handoff. Similarity search finds candidates; it does not establish authority.

## Record durable knowledge

Use the [decision template](DECISION_TEMPLATE.md) for a new proposal. Once accepted,
record the implementation/evidence and link it from the relevant system document.
Use the [handoff template](HANDOFF_TEMPLATE.md) for completed substantial work and
save it under `docs/handoffs/`. Update the documentation index in the same change.
Keep one canonical decision and link to it; avoid copied manuals or chat dumps.

Ask an assistant: “Read AGENTS.md and the relevant linked documents. Cite the
source path and applicable version for each architectural constraint. Identify
superseded guidance before proposing changes.” Accepted decisions belong in Git;
an assistant needs access to these files to use them as persistent context.
