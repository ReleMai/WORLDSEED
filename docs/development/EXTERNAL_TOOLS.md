# WORLDSEED external development tools

Decision date: 2026-10-25. Scope: developer tooling, not a renderer migration or
live AI dependency in the shipped game. The user authorized selecting the five
most useful tools and starting implementation. These rankings are judgments about
fit with the current project, not claims of benchmarked output superiority.

## Top five

| Choice | Why it benefits WORLDSEED | Initial implementation |
| --- | --- | --- |
| Obsidian + Smart Connections | Makes existing architecture decisions, handoffs and evidence easier to find across sessions. Local Markdown preserves readable, versioned project memory. | A vault over the existing `docs/` tree, navigation and reusable decision/handoff templates. Smart Connections installation and indexing remain desktop setup. |
| Scenario | Custom style models can help future icons and props match the existing hand-painted art. A structured request preserves prompt/model choices for repeatable review. | Credential-free request planning and an explicit API submission path, with an example icon brief. A licensed account, key/secret and suitable model are required for live generation. |
| Meshy + Blender | Produces candidate 3D props and converts them into consistent 2D views usable by the current sprite renderer. Fixed cameras and lighting support asset consistency. | Meshy task planning/submission plus a local GLB-to-transparent-PNG Blender bake tool. Meshy requires an API key; Blender is a separate local executable. |
| ElevenLabs Sound Effects | Adds tailored environmental and action sounds to make harvesting, crafting and exploration more readable and atmospheric. | Sound request planning/submission and staged audio output. Requires an API key and a plan permitting intended use. Playback/event mapping is a separate future game feature. |
| Context7 | Gives coding agents current, version-specific external library documentation, reducing time spent on incorrect API assumptions. | Project configuration examples and setup instructions. Activation in the chosen coding client is still required; coverage for pygame-ce/ModernGL must be checked. |

The two paired choices are workflows: Smart Connections adds AI retrieval to
Obsidian; Blender makes Meshy output useful to WORLDSEED's sprite pipeline.
Keep the current coding agent, Git history and bounded regression gates.

## Project memory

Open `docs/` as the Obsidian vault. Follow
[memory and context setup](MEMORY_AND_CONTEXT_SETUP.md). The vault navigates the
canonical documents in place; it is not a second wiki. `AGENTS.md` remains the
coding contract. Repository state, explicit accepted decisions and current
handoffs take precedence over generated summaries and historical notes.

An assistant must have file access and consult the relevant documents for this
to work. Installing Obsidian alone does not give a chat persistent memory.
Semantic matches are suggestions; read the source and its status/version.

## Asset authoring

Use the external-assets CLI described below to stage requests outside runtime
assets. Planning is offline. Live submission requires an explicit `--execute`;
it may consume paid credits and does not automatically retry a generation POST.
No credentials are present in this checkout. No paid generation has been run
as part of the initial implementation.

From the repository root:

```sh
python tools/external_assets.py doctor
python tools/external_assets.py plan --brief config/external_tools/examples/scenario-icon.json
python tools/external_assets.py plan --brief config/external_tools/examples/meshy-prop.json
python tools/external_assets.py plan --brief config/external_tools/examples/elevenlabs-crafting.json
```

Copy a brief to ignored `scratch/`, choose a new stable trial ID, and edit it.
Scenario's example has a placeholder model ID: replace it with an account model
whose documented inputs accept `prompt` and `aspectRatio`. This adapter supports
only that input subset; custom model training is not automated.

When credentials and credit settings are ready, submit one trial:

```sh
python tools/external_assets.py submit --brief scratch/my-trial.json --execute
python tools/external_assets.py status --brief scratch/my-trial.json --task-id TASK_ID --execute
```

The doctor reports booleans, never key values. Submission records and responses
go to `scratch/external-tools/<id>/`. ElevenLabs returns staged `unreviewed.mp3`
and a hash record directly; it has no asynchronous `status` command. Scenario
and Meshy return task IDs; `status` makes one GET without an unbounded polling
loop. Read completion/error information in the staged response. The tool does
not download generated image/model URLs: use the provider's dashboard/download
workflow for the local source file. Meshy currently submits geometry-only
preview tasks; texturing/refinement is a separate provider step.

Reusing a submitted ID is rejected to avoid duplicate generation. If a request
times out, check task history in the provider before choosing a new ID: a lost
response does not prove that the provider did no work. A new ID starts a new
trial and can consume additional credits.

For 3D props, use the [Blender bake workflow](BLENDER_SPRITE_BAKING.md).
Inspect silhouettes, materials, scale, camera angle and ground contact at actual
game resolution before accepting a model or sprite. A generated 3D model is
not automatically a game-ready asset.

For approved 2D item art, preserve the existing pipeline:
`prepare_item_icon_generation.py` -> source generation -> reviewed sheet manifest
-> `import_generated_item_icons.py --validate-only` -> import -> atlas rebuild
-> generated-art verification and relevant tests. A provider response or an
individual image is not automatically a valid source sheet. See the
[Dev64 asset handoff](../handoffs/DEV64_ITEM_ART_DATABASE_HANDOFF.md).

Store the prompt, provider/model version, reference permissions, source hash,
editing/baking settings and final accepted hash alongside approved sources.
The scratch directory is local staging, not durable provenance: move approved
source material and its reviewed records into the existing source-art structure
as part of a deliberate asset publication.

## Activation and quality trial

1. Open the vault and install Smart Connections Core from Obsidian's Community
   Plugins if semantic retrieval is wanted. Use local embeddings initially.
2. Configure Context7 in the coding client, resolve the actual library/version,
   and inspect returned documentation before relying on it.
3. Set provider credentials in the calling process. The example environment
   file lists variable names; scripts do not automatically load `.env` files.
4. Plan and inspect one request for each provider. Run live generation only
   after account/model/credit settings are ready.
5. Trial 20 icons, three static props and 10-15 sounds. Record accepted outputs,
   cleanup minutes, native-size style match and total cost per accepted asset.

Account creation, subscriptions, custom model training, desktop plugin
installation and in-game audio playback are not claimed as completed by this
repository scaffold. No runtime save, content or world-generation contracts
change in this work unit.

## Official references

- [Obsidian local storage](https://obsidian.md/help/data-storage)
- [Smart Connections capabilities](https://smartconnections.app/smart-connections/)
- [Scenario custom-generation API](https://docs.scenario.com/)
- [Scenario plans and commercial permissions](https://www.scenario.com/pricing)
- [Meshy API](https://docs.meshy.ai/en/api/text-to-3d)
- [Meshy ownership and attribution](https://help.meshy.ai/en/articles/9992001-can-i-use-meshy-assets-commercially-license-copyright-explained)
- [Blender features](https://www.blender.org/features/)
- [ElevenLabs sound generation](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert)
- [ElevenLabs creative terms](https://elevenlabs.io/creative-terms)
- [Context7 documentation](https://context7.com/docs/overview)

Provider endpoints and plan terms can change. Validate the chosen model's input
schema and license before a new production batch; permissions for uploaded
references and training data are separate from a tool subscription.
