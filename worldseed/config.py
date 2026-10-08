from pathlib import Path

PROJECT_NAME = "WORLDSEED"
ENGINE_VERSION = "1.0.0-rc14-dev60"
SAVE_SCHEMA_VERSION = 3

# Dev27: WORLDGEN v8 is now the default for newly created worlds. Existing
# saves remain pinned to the worldgen_version stored in their metadata, so
# v1-v7 geography is never silently regenerated under the geological v8 rules.
WORLDGEN_VERSION = 8
# Retained as a compatibility alias for v8 audit/development tooling created
# during the staged promotion period.
WORLDGEN_PREVIEW_VERSION = WORLDGEN_VERSION

# RC14 geography subsystems remain independently versioned. Hydrology v2 is
# the current new-world drainage contract; existing saves remain pinned to the
# hydrology_version recorded in their metadata.
HYDROLOGY_VERSION = 2
# Projection/morphology is versioned separately from the drainage-domain solve.
# Dev29 v2 saves without this metadata infer morphology v1; new saves use v2.
HYDROLOGY_MORPHOLOGY_VERSION = 2
# Phase 5 coastline materialization is independently pinned. Dev32 worlds
# missing this metadata remain on coast version 0 and keep their old shoreline.
COAST_MORPHOLOGY_VERSION = 2
ENVIRONMENT_VERSION = 1
CLIMATE_VERSION = 1
WEATHER_VERSION = 2
LIGHTING_VERSION = 1
# Regional civilization Phase 1 changes settlement siting/morphology and
# introduces the first authoritative sparse regional route planner.
# Phase 2 binds settlement gateways to selected strategic routes and gives
# routes exact local physical corridors/infrastructure state.
# Phase 3 adds dynamic hazard rerouting, frontier control/tolls/patrols and
# interactive physical crossings. Settlement geometry remains v5-compatible.
# Dev50 south-facing portals, crossable gates and bounded unbound gateways.
# Stored v1-v11 generation stays pinned; explicit access repairs are deltas.
SETTLEMENT_PLAN_VERSION = 12
LEGACY_SETTLEMENT_PLAN_VERSION = 10
ROUTEGEN_VERSION = 4
# Claim monuments are persistent regional control anchors.  Versioning their
# generated placement separately keeps existing worlds from silently moving
# political geography when the scoring or spacing contract changes.
TERRITORY_VERSION = 1
RNG_PROTOCOL_VERSION = 1
RESOURCEGEN_VERSION = 4
CHUNK_SIZE = 32
REGION_CHUNKS = 16
DEFAULT_CACHE_CHUNKS = 384
AUTOSAVE_TURNS = 40
MINUTES_PER_ACTION = 5
MOVE_MINUTES = 0
# Continuous-play clock.  Half a wall-clock second advances one game minute while
# gameplay is active; long stalls are capped and resumed from "now" instead of
# replaying an unbounded backlog.  Explicit long actions may still fast-forward.
REALTIME_SECONDS_PER_GAME_MINUTE = 0.5
REALTIME_MAX_CATCHUP_MINUTES = 5
# Nearby NPC action execution remains on deterministic game-time boundaries.
# The boundaries are now fed by continuous time rather than player movement.
SIMULATION_TICK_MINUTES = 1
# Long explicit waits retain bounded coarse simulation instead of replaying tens
# of thousands of exact local ticks. Normal play remains on the fixed tick.
ACTIVE_TICK_REPLAY_LIMIT_MINUTES = 360
ACTIVE_REGION_RADIUS = 1
OFFLINE_CAP_DAYS = 30
DEFAULT_OFFLINE_POLICY = "safe"

# RC13 startup world preparation. WORLDSEED remains deterministically unbounded,
# but a large surface envelope around a new spawn is generated and persisted
# during the loading screen so ordinary early exploration reads prepared chunks
# instead of paying generation cost in the movement loop.
INITIAL_PREGEN_CHUNK_RADIUS = 8
LOAD_WARM_CHUNK_RADIUS = 2
RESOURCE_CHUNK_CACHE_LIMIT = 384

PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_ROOT / "data"
DEFAULT_SAVE_DIR = Path.cwd() / "saves"
