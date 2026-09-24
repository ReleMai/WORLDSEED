from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any

@dataclass(slots=True)
class StructureInstance:
    structure_id: str
    x: int
    y: int
    z: int
    owner: str = "player"
    condition: int = 100

@dataclass(slots=True)
class GroundPile:
    x: int
    y: int
    z: int
    items: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class CarcassState:
    uid: str
    species_id: str
    x: int
    y: int
    z: int
    killed_minute: int
    quality: int = 100
    skinned: bool = False
    butchered: bool = False
    deboned: bool = False
    hide_ruined: bool = False
    processed_by: str = ""
    source_uid: str = ""
    embedded_items: dict[str, int] = field(default_factory=dict)

@dataclass(slots=True)
class AnimalSignState:
    uid: str
    species_id: str
    x: int
    y: int
    z: int
    kind: str
    created_minute: int
    direction_x: int = 0
    direction_y: int = 0
    strength: int = 50
    source_uid: str = ""
    detail: str = ""

@dataclass(slots=True)
class ProcessingJobState:
    uid: str
    process_id: str
    station_key: str
    owner: str
    started_minute: int
    complete_minute: int
    inputs: dict[str, int] = field(default_factory=dict)
    outputs: dict[str, int] = field(default_factory=dict)
    status: str = "working"
    note: str = ""

@dataclass(slots=True)
class PreparedMealState:
    uid: str
    name: str
    method_id: str
    owner: str
    created_minute: int
    ingredients: list[str] = field(default_factory=list)
    portions: int = 1
    satiety: int = 0
    hydration: int = 0
    calories: int = 0
    protein: int = 0
    carbs: int = 0
    fat: int = 0
    fiber: int = 0
    food_groups: dict[str, int] = field(default_factory=dict)
    effects: dict[str, int] = field(default_factory=dict)
    spoil_minute: int = 0



@dataclass(slots=True)
class RoofState:
    structure_id: str
    x: int
    y: int
    z: int
    owner: str = "player"
    condition: int = 100

@dataclass(slots=True)
class ContainerState:
    uid: str
    x: int
    y: int
    z: int
    owner: str
    capacity_mass_g: int
    capacity_volume_ml: int
    items: dict[str, int] = field(default_factory=dict)
    condition: int = 100
    temperature_c: int = 20
    contamination: int = 0
    name: str = ""
    kind: str = "built"
    movable: bool = False
    source_id: str = ""
    salvage: dict[str, tuple[int, int]] = field(default_factory=dict)

@dataclass(slots=True)
class SoilState:
    x: int
    y: int
    z: int
    nitrogen: int = 70
    phosphorus: int = 70
    potassium: int = 70
    organic: int = 50
    disease_pressure: int = 0
    last_crop_id: str = ""

@dataclass(slots=True)
class CropPlot:
    crop_id: str
    x: int
    y: int
    z: int
    planted_minute: int
    growth: int = 0
    moisture: int = 70
    health: int = 100
    mature: bool = False
    disease: int = 0

@dataclass(slots=True)
class CreatureState:
    uid: str
    species_id: str
    x: int
    y: int
    z: int
    hp: int
    hunger: int = 0
    notable: bool = False
    name: str = ""
    wounds: list[dict] = field(default_factory=list)
    blood: int = 100
    pain: int = 0
    kills: int = 0
    bounty: int = 0
    cohort_key: str = ""
    behavior: str = "calm"
    alertness: int = 0
    stamina: int = 100
    threat_x: int | None = None
    threat_y: int | None = None
    threat_z: int | None = None
    last_threat_turn: int = -1
    last_move_turn: int = -1
    facing_dx: int = 0
    facing_dy: int = 1
    embedded_projectiles: list[dict] = field(default_factory=list)
    staggered_until_turn: int = -1

@dataclass(slots=True)
class PopulationCohort:
    key: str
    region_x: int
    region_y: int
    species_id: str
    count: int
    mean_health: int = 90
    stored_energy: int = 70
    disease: int = 0
    z: int = 0

@dataclass(slots=True)
class NPCState:
    uid: str
    name: str
    age: int
    occupation: str
    traits: list[str]
    x: int
    y: int
    z: int
    settlement_id: str
    faction_id: str
    hp: int = 100
    hunger: int = 0
    thirst: int = 0
    rest: int = 0
    wealth: int = 20
    goal: str = "work"
    goal_score: int = 0
    memories: list[dict] = field(default_factory=list)
    relationships: dict[str, dict[str, int]] = field(default_factory=dict)
    knowledge: list[str] = field(default_factory=list)
    spouse_uid: str = ""
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    home_id: str = ""
    workplace_id: str = ""
    property_id: str = ""
    employer_id: str = ""
    culture_id: str = ""
    religion_id: str = ""
    literacy: int = 0
    language_fluency: dict[str, int] = field(default_factory=dict)
    alive: bool = True
    infections: list[str] = field(default_factory=list)
    immunities: dict[str, int] = field(default_factory=dict)
    disease_history: list[str] = field(default_factory=list)

@dataclass(slots=True)
class SettlementState:
    uid: str
    name: str
    region_x: int
    region_y: int
    x: int
    y: int
    population: int
    culture_id: str
    religion_id: str
    faction_id: str
    wealth: int = 500
    stocks: dict[str, int] = field(default_factory=dict)
    prices: dict[str, int] = field(default_factory=dict)
    buildings: dict[str, int] = field(default_factory=dict)
    food_stress: int = 0
    law: dict[str, int] = field(default_factory=dict)
    knowledge: list[str] = field(default_factory=list)
    property_owners: dict[str, str] = field(default_factory=dict)
    labor_pool: dict[str, int] = field(default_factory=dict)
    budget: dict[str, int] = field(default_factory=dict)
    unemployment: int = 0
    housing_capacity: int = 0
    homeless: int = 0
    religious_tension: int = 0
    # Bounded daily market samples per good: [minute, price, stock].  Keeping
    # history with the settlement makes scarcity legible without an unbounded
    # event log.
    market_history: dict[str, list[list[int]]] = field(default_factory=dict)
    sanitation: int = 50
    healer_capacity: int = 0
    quarantine_level: int = 0
    health_policy: str = "open"
    outbreak_history: list[dict] = field(default_factory=list)

@dataclass(slots=True)
class FactionState:
    uid: str
    name: str
    culture_id: str
    treasury: int = 1000
    power: int = 50
    relations: dict[str, int] = field(default_factory=dict)
    at_war: list[str] = field(default_factory=list)
    laws: dict[str, int] = field(default_factory=dict)
    manpower: int = 0
    military_supply: int = 0
    war_exhaustion: int = 0

@dataclass(slots=True)
class CaravanState:
    uid: str
    origin: str
    destination: str
    goods: dict[str, int]
    wealth: int
    depart_minute: int
    arrive_minute: int
    status: str = "traveling"
    route_id: str = ""
    cargo_value: int = 0
    guards: int = 0
    pathogen_load: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class LaborReservationState:
    uid: str
    settlement_id: str
    process_id: str
    occupation: str
    workers: int
    assigned_day: int
    active: bool = True

@dataclass(slots=True)
class TradeRouteState:
    uid: str
    origin: str
    destination: str
    distance: int
    danger: int
    capacity: int
    last_used_minute: int = 0
    traffic: int = 0
    waypoints: list[str] = field(default_factory=list)
    travel_minutes: int = 0
    chunk_waypoints: list[str] = field(default_factory=list)

@dataclass(slots=True)
class PropertyState:
    uid: str
    settlement_id: str
    kind: str
    owner_uid: str
    value: int
    rent: int
    capacity: int
    occupants: list[str] = field(default_factory=list)
    condition: int = 100

@dataclass(slots=True)
class MigrationCohortState:
    uid: str
    origin: str
    destination: str
    count: int
    reason: str
    depart_minute: int
    arrive_minute: int
    status: str = "traveling"
    wealth: int = 0
    npc_uids: list[str] = field(default_factory=list)
    pathogen_load: dict[str, int] = field(default_factory=dict)

@dataclass(slots=True)
class HistoricEvent:
    uid: str
    minute: int
    event_type: str
    summary: str
    region_x: int = 0
    region_y: int = 0
    subjects: list[str] = field(default_factory=list)
    causes: list[str] = field(default_factory=list)
    salience: int = 10



@dataclass(slots=True)
class OfficeState:
    uid: str
    faction_id: str
    title: str
    holder_uid: str
    succession_rule: str
    started_minute: int
    previous_holders: list[str] = field(default_factory=list)

@dataclass(slots=True)
class DynastyState:
    uid: str
    name: str
    faction_id: str
    founder_uid: str
    members: list[str] = field(default_factory=list)
    prestige: int = 10

@dataclass(slots=True)
class ClaimState:
    uid: str
    claimant_id: str
    target_type: str
    target_id: str
    basis: str
    strength: int
    created_minute: int
    active: bool = True

@dataclass(slots=True)
class GraveState:
    uid: str
    person_uid: str
    person_name: str
    x: int
    y: int
    z: int
    death_minute: int
    grave_type: str = "grave"
    epitaph: str = ""

@dataclass(slots=True)
class DungeonSiteState:
    uid: str
    name: str
    chunk_x: int
    chunk_y: int
    z: int
    activated_minute: int
    traps: dict[str, bool] = field(default_factory=dict)
    locks: dict[str, bool] = field(default_factory=dict)
    occupant_uids: list[str] = field(default_factory=list)
    cleared: bool = False
    loot_seeded: bool = False
    current_controller: str = ""
    occupation_history: list[dict] = field(default_factory=list)

@dataclass(slots=True)
class FireCell:
    x: int
    y: int
    z: int
    intensity: int
    fuel: int

@dataclass(slots=True)
class FluidCell:
    x: int
    y: int
    z: int
    fluid: str
    amount: int
    contamination: int = 0

@dataclass(slots=True)
class DiseaseState:
    disease_id: str
    region_x: int
    region_y: int
    infected: int
    severity: int
    contagiousness: int
    name: str = ""
    settlement_id: str = ""
    recovered: int = 0
    deaths: int = 0
    immune: int = 0
    strain: int = 0
    first_minute: int = 0
    last_minute: int = 0
    policy: str = "open"
    trend: list[list[int]] = field(default_factory=list)

@dataclass(slots=True)
class InfectionState:
    uid: str
    disease_id: str
    host_type: str
    host_id: str
    exposed_minute: int
    stage: str = "incubating"
    viral_load: int = 10
    severity: int = 0
    symptomatic: bool = False
    treated: bool = False
    recovered_minute: int = 0
    source: str = "unknown"
    last_progress_minute: int = 0

@dataclass(slots=True)
class MagicLaw:
    uid: str
    source: str
    form: str
    catalyst: str
    stamina_cost: int
    potency: int
    discoverable: bool = True
    time_constraint: str = "any"
    terrain_constraint: str = ""
    instability: int = 10
    contamination: str = "arcane"
    consumes_catalyst: bool = False


@dataclass(slots=True)
class MagicTraditionState:
    uid: str
    culture_id: str
    name: str
    favored_sources: list[str]
    favored_forms: list[str]
    taboo_source: str = ""
    known_laws: list[str] = field(default_factory=list)

@dataclass(slots=True)
class SpellState:
    uid: str
    law_uid: str
    name: str
    ast: dict
    discovered_minute: int
    cast_count: int = 0

@dataclass(slots=True)
class RitualState:
    uid: str
    religion_id: str
    name: str
    law_uids: list[str]
    catalysts: dict[str, int]
    duration_minutes: int
    min_participants: int
    location: str
    effect: str
    performed_count: int = 0

@dataclass(slots=True)
class ArcaneContaminationState:
    x: int
    y: int
    z: int
    kind: str
    intensity: int
    source_law: str
    last_minute: int

@dataclass(slots=True)
class MythState:
    uid: str
    culture_id: str
    title: str
    origin_event_uid: str
    subject_uid: str
    belief: str
    created_minute: int
    adherents: int = 1

@dataclass(slots=True)
class CultureState:
    uid: str
    name: str
    values: list[str]
    naming_style: str
    taboos: list[str]
    craft_bias: str
    lexicon: dict[str, str] = field(default_factory=dict)

@dataclass(slots=True)
class ReligionState:
    uid: str
    name: str
    deity: str
    domains: list[str]
    taboo: str
    ritual: str
    sacred_animal: str





@dataclass(slots=True)
class LibraryState:
    uid: str
    settlement_id: str
    name: str
    book_uids: list[str] = field(default_factory=list)
    capacity: int = 40
    condition: int = 100

@dataclass(slots=True)
class KnowledgeSchoolState:
    uid: str
    settlement_id: str
    name: str
    focus: str
    member_uids: list[str] = field(default_factory=list)
    prestige: int = 10
    rival_uid: str = ""

@dataclass(slots=True)
class ReligiousInstitutionState:
    uid: str
    settlement_id: str
    religion_id: str
    name: str
    priest_uids: list[str] = field(default_factory=list)
    influence: int = 30
    holy_x: int = 0
    holy_y: int = 0
    holy_z: int = 0
    doctrine: str = "orthodox"

@dataclass(slots=True)
class MetalBatchState:
    uid: str
    item_id: str
    owner: str
    material: str
    mass_g: int
    temperature_c: int
    carbon_permille: int
    purity: int
    quality: int
    created_minute: int
    heat_until_minute: int = 0
    treatments: list[str] = field(default_factory=list)

@dataclass(slots=True)
class BookState:
    uid: str
    title: str
    author: str
    knowledge: str
    created_minute: int
    culture_id: str
    owner: str
    language_id: str = ""
    copied_from_uid: str = ""
    condition: int = 100

@dataclass(slots=True)
class ArtifactState:
    uid: str
    name: str
    base_item: str
    material: str
    quality: int
    creator: str
    created_minute: int
    owner: str = "player"
    history: list[str] = field(default_factory=list)
    components: dict[str, dict] = field(default_factory=dict)
    provenance: list[dict] = field(default_factory=list)
    condition: int = 100
    temperature_c: int = 20
    contamination: int = 0

@dataclass(slots=True)
class LegacyCharacter:
    name: str
    born_minute: int
    died_minute: int
    cause: str
    x: int
    y: int
    z: int
    achievements: list[str] = field(default_factory=list)

@dataclass(slots=True)
class LivingWorldState:
    clock_minute: int = 480
    structures: dict[str, StructureInstance] = field(default_factory=dict)
    roofs: dict[str, RoofState] = field(default_factory=dict)
    containers: dict[str, ContainerState] = field(default_factory=dict)
    soils: dict[str, SoilState] = field(default_factory=dict)
    ground_piles: dict[str, GroundPile] = field(default_factory=dict)
    carcasses: dict[str, CarcassState] = field(default_factory=dict)
    processing_jobs: dict[str, ProcessingJobState] = field(default_factory=dict)
    prepared_meals: dict[str, PreparedMealState] = field(default_factory=dict)
    crops: dict[str, CropPlot] = field(default_factory=dict)
    creatures: dict[str, CreatureState] = field(default_factory=dict)
    animal_signs: dict[str, AnimalSignState] = field(default_factory=dict)
    cohorts: dict[str, PopulationCohort] = field(default_factory=dict)
    npcs: dict[str, NPCState] = field(default_factory=dict)
    settlements: dict[str, SettlementState] = field(default_factory=dict)
    factions: dict[str, FactionState] = field(default_factory=dict)
    caravans: dict[str, CaravanState] = field(default_factory=dict)
    labor_reservations: dict[str, LaborReservationState] = field(default_factory=dict)
    trade_routes: dict[str, TradeRouteState] = field(default_factory=dict)
    properties: dict[str, PropertyState] = field(default_factory=dict)
    migration_cohorts: dict[str, MigrationCohortState] = field(default_factory=dict)
    history: list[HistoricEvent] = field(default_factory=list)
    history_archive: dict[str, dict[str, Any]] = field(default_factory=dict)
    dungeon_sites: dict[str, DungeonSiteState] = field(default_factory=dict)
    offices: dict[str, OfficeState] = field(default_factory=dict)
    dynasties: dict[str, DynastyState] = field(default_factory=dict)
    claims: dict[str, ClaimState] = field(default_factory=dict)
    graves: dict[str, GraveState] = field(default_factory=dict)
    fires: dict[str, FireCell] = field(default_factory=dict)
    fluids: dict[str, FluidCell] = field(default_factory=dict)
    diseases: dict[str, DiseaseState] = field(default_factory=dict)
    infections: dict[str, InfectionState] = field(default_factory=dict)
    magic_laws: dict[str, MagicLaw] = field(default_factory=dict)
    magic_traditions: dict[str, MagicTraditionState] = field(default_factory=dict)
    spells: dict[str, SpellState] = field(default_factory=dict)
    rituals: dict[str, RitualState] = field(default_factory=dict)
    arcane_contamination: dict[str, ArcaneContaminationState] = field(default_factory=dict)
    myths: dict[str, MythState] = field(default_factory=dict)
    cultures: dict[str, CultureState] = field(default_factory=dict)
    religions: dict[str, ReligionState] = field(default_factory=dict)
    libraries: dict[str, LibraryState] = field(default_factory=dict)
    knowledge_schools: dict[str, KnowledgeSchoolState] = field(default_factory=dict)
    religious_institutions: dict[str, ReligiousInstitutionState] = field(default_factory=dict)
    player_name: str = "Wanderer"
    # ``player_origin`` is retained for backwards compatibility with RC5 and
    # older saves. New characters use ``custom`` and are defined by point-buy
    # attributes, skills and talents instead of a class/origin.
    player_origin: str = "custom"
    player_sex: str = "male"
    player_sprite_index: int = 0
    player_attributes: dict[str, int] = field(default_factory=lambda: {
        "strength":5,"agility":5,"endurance":5,"intellect":5,"perception":5,"will":5
    })
    player_skills: dict[str, int] = field(default_factory=lambda: {
        "swimming":0,"athletics":0,"survival":0,"foraging":0,"woodcutting":0,"mining":0,
        "hunting":0,"fishing":0,"melee":0,"shield":0,"crafting":0,"medicine":0,"scholarship":0,
        "persuasion":0,"trading":0,"naturalism":0,"arcana":0
    })
    player_swimming_xp: int = 0
    player_fishing_xp: int = 0
    fishing_attempts: int = 0
    fishing_pressure: dict[str, int] = field(default_factory=dict)
    player_fishing_log: list[dict] = field(default_factory=list)
    player_talents: list[str] = field(default_factory=list)
    player_knowledge: list[str] = field(default_factory=lambda: ["craft:stoneworking", "craft:leatherwork"])
    # Discovery crafting is opt-in per world for backward compatibility. New
    # worlds enable it; v1-v6 saves retain the legacy visible-recipe behavior.
    player_crafting_discovery_enabled: bool = False
    player_discovered_items: list[str] = field(default_factory=list)
    player_discovered_recipes: list[str] = field(default_factory=list)
    player_crafting_experiments: int = 0
    player_literacy: int = 50
    player_languages: dict[str, int] = field(default_factory=lambda: {"core:trade_tongue": 100})
    player_equipment: dict[str, str] = field(default_factory=dict)
    player_equipped_artifacts: dict[str, str] = field(default_factory=dict)
    player_readied_weapon: str = ""
    player_aim_target: str = ""
    player_aim_zone: str = "center"
    player_aim_quality: int = 0
    player_facing_dx: int = 0
    player_facing_dy: int = 1
    player_guarding: bool = False
    player_defense_mode: str = ""
    player_defense_quality: int = 0
    player_body_parts: dict[str, int] = field(default_factory=lambda: {"head":100,"neck":100,"torso":100,"left_arm":100,"right_arm":100,"left_leg":100,"right_leg":100})
    player_wounds: list[dict] = field(default_factory=list)
    player_infections: list[str] = field(default_factory=list)
    player_immunities: dict[str, int] = field(default_factory=dict)
    player_nutrition: dict[str, int] = field(default_factory=lambda: {"protein":35,"vegetable":35,"grain":35,"fruit":35,"fats":35})
    player_diet_history: list[dict] = field(default_factory=list)
    player_food_effects: dict[str, int] = field(default_factory=dict)
    discovered_tiles: list[str] = field(default_factory=list)
    discovered_settlements: list[str] = field(default_factory=list)
    visited_settlements: list[str] = field(default_factory=list)
    discovered_npcs: list[str] = field(default_factory=list)
    discovered_factions: list[str] = field(default_factory=list)
    discovered_sites: list[str] = field(default_factory=list)
    discovered_species: list[str] = field(default_factory=list)
    discovered_events: list[str] = field(default_factory=list)
    discovered_routes: list[str] = field(default_factory=list)
    # Population reports are intentionally explicit knowledge. Keys are
    # ``region_x,region_y:species_id`` and values are the report minute.
    population_reports: dict[str, int] = field(default_factory=dict)
    player_rumors: list[str] = field(default_factory=list)
    resource_depletion: dict[str, int] = field(default_factory=dict)
    realized_regions: list[str] = field(default_factory=list)
    legacy: list[LegacyCharacter] = field(default_factory=list)
    artifacts: dict[str, ArtifactState] = field(default_factory=dict)
    books: dict[str, BookState] = field(default_factory=dict)
    metal_batches: dict[str, MetalBatchState] = field(default_factory=dict)
    next_uid: int = 1
    last_daily_minute: int = 0
    last_hourly_minute: int = 0
    last_monthly_minute: int = 0
    last_offline_wall_time: float = 0.0
    offline_policy: str = "safe"
    last_offline_minutes: int = 0
    last_offline_summary: dict[str, int] = field(default_factory=dict)
    ui_color: bool = True
    ui_unicode: bool = True
    ui_density: str = "dense"

    def uid(self, prefix: str) -> str:
        out = f"{prefix}:{self.next_uid}"
        self.next_uid += 1
        return out

    def to_dict(self) -> dict[str, Any]:
        def rows(table):
            return {k: asdict(v) for k, v in table.items()}
        return {
            "clock_minute": self.clock_minute,
            "structures": rows(self.structures), "roofs": rows(self.roofs), "containers": rows(self.containers), "soils": rows(self.soils), "ground_piles": rows(self.ground_piles), "carcasses": rows(self.carcasses), "processing_jobs": rows(self.processing_jobs), "prepared_meals": rows(self.prepared_meals), "crops": rows(self.crops),
            "creatures": rows(self.creatures), "animal_signs": rows(self.animal_signs), "cohorts": rows(self.cohorts), "npcs": rows(self.npcs), "settlements": rows(self.settlements),
            "factions": rows(self.factions), "caravans": rows(self.caravans), "labor_reservations": rows(self.labor_reservations), "trade_routes": rows(self.trade_routes), "properties": rows(self.properties), "migration_cohorts": rows(self.migration_cohorts), "history": [asdict(x) for x in self.history[-6000:]], "history_archive": dict(self.history_archive), "dungeon_sites": rows(self.dungeon_sites), "offices": rows(self.offices), "dynasties": rows(self.dynasties), "claims": rows(self.claims), "graves": rows(self.graves),
            "fires": rows(self.fires), "fluids": rows(self.fluids), "diseases": rows(self.diseases), "infections": rows(self.infections), "magic_laws": rows(self.magic_laws), "magic_traditions": rows(self.magic_traditions), "spells": rows(self.spells), "rituals": rows(self.rituals), "arcane_contamination": rows(self.arcane_contamination), "myths": rows(self.myths),
            "cultures": rows(self.cultures), "religions": rows(self.religions), "libraries": rows(self.libraries), "knowledge_schools": rows(self.knowledge_schools), "religious_institutions": rows(self.religious_institutions), "player_name": self.player_name, "player_origin": self.player_origin, "player_sex": self.player_sex, "player_sprite_index": int(self.player_sprite_index), "player_attributes": dict(self.player_attributes), "player_skills": dict(self.player_skills), "player_swimming_xp": self.player_swimming_xp, "player_fishing_xp": self.player_fishing_xp, "fishing_attempts": self.fishing_attempts, "fishing_pressure": dict(self.fishing_pressure), "player_fishing_log": list(self.player_fishing_log[-240:]), "player_talents": list(self.player_talents), "player_knowledge": list(self.player_knowledge), "player_crafting_discovery_enabled": self.player_crafting_discovery_enabled, "player_discovered_items": sorted(set(self.player_discovered_items)), "player_discovered_recipes": sorted(set(self.player_discovered_recipes)), "player_crafting_experiments": self.player_crafting_experiments, "player_literacy": self.player_literacy, "player_languages": dict(self.player_languages),
            "player_equipment": dict(self.player_equipment), "player_equipped_artifacts": dict(self.player_equipped_artifacts), "player_readied_weapon": self.player_readied_weapon, "player_aim_target": self.player_aim_target, "player_aim_zone": self.player_aim_zone, "player_aim_quality": int(self.player_aim_quality), "player_facing_dx": int(self.player_facing_dx), "player_facing_dy": int(self.player_facing_dy), "player_guarding": bool(self.player_guarding), "player_defense_mode": self.player_defense_mode, "player_defense_quality": int(self.player_defense_quality), "player_body_parts": dict(self.player_body_parts), "player_wounds": list(self.player_wounds), "player_infections": list(self.player_infections), "player_immunities": dict(self.player_immunities), "player_nutrition": dict(self.player_nutrition), "player_diet_history": list(self.player_diet_history[-240:]), "player_food_effects": dict(self.player_food_effects),
            "discovered_tiles": list(self.discovered_tiles[-120000:]),
            "discovered_settlements": sorted(set(self.discovered_settlements)), "visited_settlements": sorted(set(self.visited_settlements)), "discovered_npcs": sorted(set(self.discovered_npcs)),
            "discovered_factions": sorted(set(self.discovered_factions)), "discovered_sites": sorted(set(self.discovered_sites)),
            "discovered_species": sorted(set(self.discovered_species)), "discovered_events": sorted(set(self.discovered_events)), "discovered_routes": sorted(set(self.discovered_routes)), "population_reports": dict(self.population_reports), "player_rumors": list(dict.fromkeys(self.player_rumors))[-40:], "resource_depletion": dict(self.resource_depletion),
            "realized_regions": sorted(set(self.realized_regions)), "legacy": [asdict(x) for x in self.legacy], "artifacts": rows(self.artifacts), "books": rows(self.books), "metal_batches": rows(self.metal_batches), "next_uid": self.next_uid,
            "last_daily_minute": self.last_daily_minute, "last_hourly_minute": self.last_hourly_minute,
            "last_monthly_minute": self.last_monthly_minute, "last_offline_wall_time": self.last_offline_wall_time,
            "offline_policy": self.offline_policy, "last_offline_minutes": self.last_offline_minutes, "last_offline_summary": dict(self.last_offline_summary),
            "ui_color": self.ui_color, "ui_unicode": self.ui_unicode, "ui_density": self.ui_density,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "LivingWorldState":
        if not raw:
            return cls()
        s = cls()
        scalar = ["player_swimming_xp","player_fishing_xp","fishing_attempts","fishing_pressure","player_fishing_log","clock_minute","player_name","player_origin","player_sex","player_sprite_index","player_attributes","player_skills","player_talents","player_knowledge","player_crafting_discovery_enabled","player_discovered_items","player_discovered_recipes","player_crafting_experiments","player_literacy","player_languages","player_equipment","player_equipped_artifacts","player_readied_weapon","player_aim_target","player_aim_zone","player_aim_quality","player_facing_dx","player_facing_dy","player_guarding","player_defense_mode","player_defense_quality","player_body_parts","player_wounds","player_infections","player_immunities","player_nutrition","player_diet_history","player_food_effects","discovered_tiles","discovered_settlements","visited_settlements","discovered_npcs","discovered_factions","discovered_sites","discovered_species","discovered_events","discovered_routes","population_reports","player_rumors","resource_depletion","realized_regions","next_uid","last_daily_minute","last_hourly_minute","last_monthly_minute","last_offline_wall_time","offline_policy","last_offline_minutes","last_offline_summary","ui_color","ui_unicode","ui_density","history_archive"]
        for key in scalar:
            if key in raw:
                setattr(s, key, raw[key])
        maps = {
            "structures":StructureInstance,"roofs":RoofState,"containers":ContainerState,"soils":SoilState,"ground_piles":GroundPile,"carcasses":CarcassState,"processing_jobs":ProcessingJobState,"prepared_meals":PreparedMealState,"crops":CropPlot,"creatures":CreatureState,"animal_signs":AnimalSignState,"cohorts":PopulationCohort,
            "npcs":NPCState,"settlements":SettlementState,"factions":FactionState,"caravans":CaravanState,"labor_reservations":LaborReservationState,"trade_routes":TradeRouteState,"properties":PropertyState,"migration_cohorts":MigrationCohortState,"dungeon_sites":DungeonSiteState,"offices":OfficeState,"dynasties":DynastyState,"claims":ClaimState,"graves":GraveState,"fires":FireCell,"fluids":FluidCell,
            "diseases":DiseaseState,"infections":InfectionState,"magic_laws":MagicLaw,"magic_traditions":MagicTraditionState,"spells":SpellState,"rituals":RitualState,"arcane_contamination":ArcaneContaminationState,"myths":MythState,"cultures":CultureState,"religions":ReligionState,"libraries":LibraryState,"knowledge_schools":KnowledgeSchoolState,"religious_institutions":ReligiousInstitutionState,"artifacts":ArtifactState,"books":BookState,"metal_batches":MetalBatchState,
        }
        # New skills must appear on legacy saves even when the old save
        # serialized the entire skill dictionary before the skill existed.
        s.player_skills.setdefault("shield",0)
        for key, typ in maps.items():
            setattr(s, key, {k:typ(**v) for k,v in raw.get(key, {}).items()})
        s.history = [HistoricEvent(**v) for v in raw.get("history", [])]
        s.legacy = [LegacyCharacter(**v) for v in raw.get("legacy", [])]
        return s


def pos_key(x: int, y: int, z: int) -> str:
    return f"{x},{y},{z}"
