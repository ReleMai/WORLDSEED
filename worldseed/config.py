from pathlib import Path

PROJECT_NAME = "WORLDSEED"
ENGINE_VERSION = "1.0.0-rc14-dev28"
SAVE_SCHEMA_VERSION = 3

# Dev27: WORLDGEN v8 is now the default for newly created worlds. Existing
# saves remain pinned to the worldgen_version stored in their metadata, so
# v1-v7 geography is never silently regenerated under the geological v8 rules.
WORLDGEN_VERSION = 8
# Retained as a compatibility alias for v8 audit/development tooling created
# during the staged promotion period.
WORLDGEN_PREVIEW_VERSION = WORLDGEN_VERSION

# RC14 hydrology/plan/resource contracts remain independently versioned.
# Hydrology v2 and physical climate arrive in later WORLDGEN v8 phases.
HYDROLOGY_VERSION = 1
ENVIRONMENT_VERSION = 1
CLIMATE_VERSION = 1
WEATHER_VERSION = 2
LIGHTING_VERSION = 1
SETTLEMENT_PLAN_VERSION = 1
ROUTEGEN_VERSION = 1
RNG_PROTOCOL_VERSION = 1
RESOURCEGEN_VERSION = 3
CHUNK_SIZE = 32
REGION_CHUNKS = 16
DEFAULT_CACHE_CHUNKS = 384
AUTOSAVE_TURNS = 40
MINUTES_PER_ACTION = 5
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
