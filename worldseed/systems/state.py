from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from worldseed.systems.names import npc_sex_for_identity
from worldseed.systems.discovery import DiscoveryTiles, DISCOVERY_FORMAT_VERSION

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
    organ_damage: dict[str, int] = field(default_factory=dict)
    harvested_parts: list[str] = field(default_factory=list)

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
class AnimalHomeState:
    uid: str
    species_id: str
    x: int
    y: int
    z: int
    kind: str
    created_minute: int
    group_key: str = ""
    occupant_uids: list[str] = field(default_factory=list)
    stored_items: dict[str, int] = field(default_factory=dict)
    last_used_minute: int = 0
    discovered: bool = False

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
    settlement_id: str = ""
    property_id: str = ""
    room_id: str = ""
    access: str = "owner"
    lock_level: int = 0
    locked: bool = False
    picked: bool = False
    pick_attempts: int = 0
    last_tampered_minute: int = -1
    keyholder_uids: list[str] = field(default_factory=list)
    lock_uid: str = ""
    seeded_from_settlement: bool = False
    # Indoor storage keeps the same goods/lock identity, but is indexed by UID
    # rather than an exterior tile. Coordinates remain the building anchor.
    profile_id: str = ""
    interior_space_id: str = ""
    interior_furniture_uid: str = ""

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
    charge_committed_until_turn: int = -1
    charge_momentum: int = 0
    pack_role: str = ""
    panic: int = 0
    last_display_turn: int = -1000
    last_attacked_turn: int = -1000
    thirst: int = 0
    home_uid: str = ""
    activity_until_turn: int = -1
    activity_target_x: int | None = None
    activity_target_y: int | None = None
    activity_target_z: int | None = None
    last_need_minute: int = -1
    domestic: bool = False
    settlement_id: str = ""
    pen_id: str = ""

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
class HouseholdState:
    uid: str
    settlement_id: str
    member_uids: list[str] = field(default_factory=list)
    home_id: str = ""
    storage_uids: list[str] = field(default_factory=list)
    food_shortage: int = 0
    days_short: int = 0
    last_consumed_minute: int = -1
    logistics_mode: str = "aggregate"
    reserve_days: int = 3
    target_stock: dict[str, int] = field(default_factory=dict)
    unmet_needs: dict[str, int] = field(default_factory=dict)
    last_procurement_minute: int = -1
    last_income_minute: int = -1
    total_spent: int = 0
    total_income: int = 0
    ledger: list[dict] = field(default_factory=list)
    diet_mix: dict[str, int] = field(default_factory=dict)
    nutrition_quality: int = 50
    fuel_shortage: int = 0
    hygiene_shortage: int = 0
    medical_shortage: int = 0
    hardship_score: int = 0
    stable_days: int = 0

@dataclass(slots=True)
class HouseholdDeliveryState:
    uid: str
    household_uid: str
    settlement_id: str
    carrier_uid: str
    item_id: str
    quantity: int
    destination_uid: str
    copper_value: int
    reserved_minute: int
    status: str = "assigned"
    picked_minute: int = -1
    delivered_minute: int = -1
    coarse_due_minute: int = -1
    physical_cargo: bool = False

@dataclass(slots=True)
class WorkplaceLogisticsState:
    uid: str
    settlement_id: str
    property_id: str
    storage_uid: str
    process_id: str
    representative_uids: list[str] = field(default_factory=list)
    last_run_minute: int = -1
    physical_batches_total: int = 0
    staged_inputs_total: dict[str, int] = field(default_factory=dict)
    retained_outputs_total: dict[str, int] = field(default_factory=dict)
    market_outputs_total: dict[str, int] = field(default_factory=dict)
    overflow_outputs_total: dict[str, int] = field(default_factory=dict)
    blocked_reason: str = ""
    ledger: list[dict] = field(default_factory=list)

@dataclass(slots=True)
class WorkplaceShipmentState:
    uid: str
    workplace_uid: str
    settlement_id: str
    carrier_uid: str
    item_id: str
    quantity: int
    source_uid: str
    reserved_minute: int
    status: str = "assigned"
    picked_minute: int = -1
    delivered_minute: int = -1
    coarse_due_minute: int = -1

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
    sex: str = ""
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
    # Phase 4 named representatives carry real goods.  This is intentionally
    # separate from settlement stocks: material becomes aggregate only through
    # an explicit physical-goods transfer/logistics boundary.
    inventory: dict[str, int] = field(default_factory=dict)
    skills: dict[str, int] = field(default_factory=dict)
    skill_xp: dict[str, int] = field(default_factory=dict)
    home_id: str = ""
    home_room_id: str = ""
    bed_fixture_id: str = ""
    workplace_id: str = ""
    work_room_id: str = ""
    property_id: str = ""
    employer_id: str = ""
    culture_id: str = ""
    religion_id: str = ""
    literacy: int = 0
    language_fluency: dict[str, int] = field(default_factory=dict)
    # Outdoor graphical locomotion keeps the authoritative tile coordinate in
    # x/y while these fractions identify the actor within that tile.
    fx: float = 0.5
    fy: float = 0.5
    alive: bool = True
    infections: list[str] = field(default_factory=list)
    immunities: dict[str, int] = field(default_factory=dict)
    disease_history: list[str] = field(default_factory=list)
    family_uid: str = ""
    lineage_uid: str = ""
    kinship: dict[str, str] = field(default_factory=dict)
    backstory: dict[str, str] = field(default_factory=dict)
    needs: dict[str, int] = field(default_factory=dict)
    wants: list[str] = field(default_factory=list)
    assigned_process_id: str = ""
    work_assignment_day: int = -1
    work_hours_today: int = 0
    routine_phase: str = ""
    facing_dx: int = 0
    facing_dy: int = 1

    # Equipment reserves units already in inventory; it is never another copy
    # of the carried goods. Cash continues to use the existing wealth ledger.
    equipment: dict[str, str] = field(default_factory=dict)

    # Keep an established face pinned to the feature catalog it was born with.
    # Rows saved before this field existed load as v1; newly born NPCs use v2.
    portrait_version: int = 2

    def __post_init__(self) -> None:
        if self.sex not in ('male','female'):
            self.sex=npc_sex_for_identity(self.name,self.uid)

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
    currency_id: str = ""
    currency_name: str = ""
    currency_value: int = 100
    barter_enabled: bool = True
    route_centrality: int = 0
    frontier_status: str = "core"
    border_pressure: int = 0
    patrol_pressure: int = 0
    resource_specializations: list[str] = field(default_factory=list)
    crop_ids: list[str] = field(default_factory=list)
    livestock_species_ids: list[str] = field(default_factory=list)

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
    archetype: str = "regional_power"
    seat_region: str = ""
    banner_style: str = ""
    doctrine: str = ""
    prominence: int = 0
    hinterland_regions: list[str] = field(default_factory=list)
    influence_regions: dict[str, int] = field(default_factory=dict)
    road_investment: int = 50
    toll_policy: int = 50

@dataclass(slots=True)
class ClaimMonumentState:
    """Persistent physical source of territorial influence.

    Generated placement is stable; capture, damage, supply and garrison fields
    are authoritative history state and must survive any regional cache rebuild.
    """
    uid: str
    monument_type: str
    region_x: int
    region_y: int
    x: int
    y: int
    strategic_value: int
    base_control: int
    max_reach: int
    generation_version: int = 1
    controller_faction_id: str = ""
    claimant_faction_id: str = ""
    capture_progress: int = 0
    integrity: int = 100
    garrison_strength: int = 0
    supply_level: int = 0
    last_supplied_minute: int = 0
    contested: bool = False
    siege_state: str = "peace"
    discovered_by: list[str] = field(default_factory=list)

@dataclass(slots=True)
class TerritoryControlState:
    region_x: int
    region_y: int
    controller_faction_id: str = ""
    control_strength: int = 0
    rival_faction_id: str = ""
    rival_strength: int = 0
    contested: bool = False
    source_uids: list[str] = field(default_factory=list)

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
    toll_paid: int = 0


@dataclass(slots=True)
class CasingIntelState:
    property_id: str
    settlement_id: str
    owner_uid: str = ""
    sessions: int = 0
    suspicion: int = 0
    alarm_level: int = 0
    last_started_minute: int = -1
    last_observed_minute: int = -1
    surveyed_cells: list[str] = field(default_factory=list)
    room_ids: list[str] = field(default_factory=list)
    storage_uids: list[str] = field(default_factory=list)
    occupant_uids: list[str] = field(default_factory=list)
    door_uids: list[str] = field(default_factory=list)
    lock_uids: list[str] = field(default_factory=list)
    entrance_known: bool = False
    owner_known: bool = False
    witness_uids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DoorSecurityState:
    uid: str
    settlement_id: str
    property_id: str
    x: int
    y: int
    z: int = 0
    role: str = "entrance"
    owner_uid: str = ""
    access: str = "private"
    locked: bool = False
    lock_level: int = 0
    condition: int = 100
    forced: bool = False
    picked: bool = False
    pick_attempts: int = 0
    last_tampered_minute: int = -1
    # Explicit key/access grants are sparse exceptions layered over the
    # authoritative home/work/property bindings. Physical key items are a
    # later consumer of this grant list rather than a second permission model.
    keyholder_uids: list[str] = field(default_factory=list)
    # Temporary social invitations are distinct from ownership and physical
    # keys. Values are absolute game minutes and expire deterministically.
    guest_access_until: dict[str, int] = field(default_factory=dict)
    lock_uid: str = ""
    # Work entrances may be locked by the local schedule. Track that provenance
    # so opening hours never unlock a lock changed by another authoritative
    # action, and so picked/forced doors are not silently repaired.
    schedule_locked: bool = False
    last_schedule_minute: int = -1
    # A knock is a request, not a conversation teleport. The selected resident
    # must walk to the exact door tile before the door opens.
    answering_npc_uid: str = ""
    answer_requested_minute: int = -1
    answered_minute: int = -1
    answer_outcome: str = ""


@dataclass(slots=True)
class PhysicalKeyState:
    uid: str
    lock_uid: str
    owner_uid: str
    label: str = "Key"
    copied_from_uid: str = ""
    created_minute: int = 0

@dataclass(slots=True)
class TrespassState:
    property_id: str
    settlement_id: str
    active: bool = False
    entered_minute: int = -1
    last_seen_minute: int = -1
    warned: bool = False
    warning_count: int = 0
    search_level: int = 0
    entry_method: str = ""
    witness_uids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SecurityIncidentState:
    uid: str
    settlement_id: str
    property_id: str
    actor_uid: str
    kind: str
    minute: int
    severity: int
    witnessed: bool = False
    witness_uids: list[str] = field(default_factory=list)
    door_uid: str = ""
    resolved: bool = False


@dataclass(slots=True)
class TheftRecordState:
    uid: str
    settlement_id: str
    thief_uid: str
    victim_uid: str
    item_id: str
    quantity: int
    value: int
    minute: int
    witnessed: bool = False
    resolved: bool = False
    property_id: str = ""
    source_kind: str = ""
    witness_uids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MarketTransactionState:
    uid: str
    settlement_id: str
    kind: str
    actor_uid: str
    counterparty_uid: str
    currency_id: str
    copper_value: int
    minute: int
    offered: dict[str, int] = field(default_factory=dict)
    requested: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class LaborReservationState:
    uid: str
    settlement_id: str
    process_id: str
    occupation: str
    workers: int
    assigned_day: int
    active: bool = True
    representative_uids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PhysicalGoodsTransferState:
    uid: str
    settlement_id: str
    actor_uid: str
    container_uid: str
    direction: str
    minute: int
    items: dict[str, int] = field(default_factory=dict)
    unit_values: dict[str, int] = field(default_factory=dict)
    total_value: int = 0
    source_kind: str = ""
    source_uid: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class MiningTripState:
    uid: str
    miner_uid: str
    settlement_id: str
    cave_x: int
    cave_y: int
    depth: int
    target_x: int
    target_y: int
    target_z: int
    stand_x: int
    stand_y: int
    ore_terrain_id: str
    ore_item_id: str
    cave_distance: int
    unit_value: int
    started_minute: int
    storage_uid: str = ""
    extracted_quantity: int = 0
    delivered_quantity: int = 0
    delivered_value: int = 0
    status: str = "planned"
    completed_minute: int = -1
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ActivityReservationState:
    uid: str
    actor_uid: str
    settlement_id: str
    activity: str
    phase: str
    affordance_uid: str
    target_uid: str
    target_kind: str
    x: int
    y: int
    z: int
    use_x: int
    use_y: int
    use_z: int
    reserved_minute: int
    duration_minutes: int
    status: str = "reserved"
    started_minute: int = -1
    completed_minute: int = -1
    expires_minute: int = -1
    metadata: dict = field(default_factory=dict)

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
    physical_route_id: str = ""
    toll_copper: int = 0
    patrol_strength: int = 0
    contested: bool = False

@dataclass(slots=True)
class RouteInfrastructureState:
    route_id: str
    condition: int = 100
    traffic: int = 0
    blocked: bool = False
    last_used_minute: int = 0
    last_maintenance_minute: int = 0
    last_update_month: int = -1
    last_hazard_hour: int = -1
    hazard_level: int = 0
    hazard_reason: str = ""
    hazard_regions: list[str] = field(default_factory=list)
    closed_until_minute: int = 0
    crossing_conditions: dict[str, int] = field(default_factory=dict)
    blocked_crossings: list[str] = field(default_factory=list)
    temporary_crossing_closures: dict[str, int] = field(default_factory=dict)
    crossing_locations: dict[str, list[int]] = field(default_factory=dict)
    detour_regions: list[str] = field(default_factory=list)
    detour_portals: list[dict] = field(default_factory=list)
    detour_crossings: list[dict] = field(default_factory=list)
    detour_updated_minute: int = 0
    reroute_count: int = 0
    control_faction_id: str = ""
    contested: bool = False
    toll_copper: int = 0
    patrol_strength: int = 0

@dataclass(slots=True)
class BorderPostState:
    uid: str
    route_id: str
    x: int
    y: int
    region_x: int
    region_y: int
    controlling_faction_id: str = ""
    rival_faction_id: str = ""
    toll_copper: int = 0
    patrol_strength: int = 0
    treasury_collected: int = 0
    contested: bool = False
    active: bool = True
    last_update_minute: int = 0

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
    architecture_style: str = "vernacular"
    settlement_morphology: str = "organic"
    public_space_tradition: str = "common"
    color_words: list[str] = field(default_factory=list)

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
    player_fx: float = 0.5
    player_fy: float = 0.5
    # WorldPos remains the exterior portal anchor; these records own local space.
    interiors: dict[str, Any] = field(default_factory=dict)
    interior_actors: dict[str, Any] = field(default_factory=dict)
    homesteads: dict[str, dict] = field(default_factory=dict)
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
    animal_homes: dict[str, AnimalHomeState] = field(default_factory=dict)
    cohorts: dict[str, PopulationCohort] = field(default_factory=dict)
    npcs: dict[str, NPCState] = field(default_factory=dict)
    households: dict[str, HouseholdState] = field(default_factory=dict)
    household_deliveries: dict[str, HouseholdDeliveryState] = field(default_factory=dict)
    workplace_logistics: dict[str, WorkplaceLogisticsState] = field(default_factory=dict)
    workplace_shipments: dict[str, WorkplaceShipmentState] = field(default_factory=dict)
    settlements: dict[str, SettlementState] = field(default_factory=dict)
    factions: dict[str, FactionState] = field(default_factory=dict)
    claim_monuments: dict[str, ClaimMonumentState] = field(default_factory=dict)
    territory_control: dict[str, TerritoryControlState] = field(default_factory=dict)
    caravans: dict[str, CaravanState] = field(default_factory=dict)
    labor_reservations: dict[str, LaborReservationState] = field(default_factory=dict)
    activity_reservations: dict[str, ActivityReservationState] = field(default_factory=dict)
    physical_goods_transfers: dict[str, PhysicalGoodsTransferState] = field(default_factory=dict)
    mining_trips: dict[str, MiningTripState] = field(default_factory=dict)
    trade_routes: dict[str, TradeRouteState] = field(default_factory=dict)
    route_infrastructure: dict[str, RouteInfrastructureState] = field(default_factory=dict)
    border_posts: dict[str, BorderPostState] = field(default_factory=dict)
    theft_records: dict[str, TheftRecordState] = field(default_factory=dict)
    market_transactions: dict[str, MarketTransactionState] = field(default_factory=dict)
    properties: dict[str, PropertyState] = field(default_factory=dict)
    door_security: dict[str, DoorSecurityState] = field(default_factory=dict)
    physical_keys: dict[str, PhysicalKeyState] = field(default_factory=dict)
    trespass_states: dict[str, TrespassState] = field(default_factory=dict)
    security_incidents: dict[str, SecurityIncidentState] = field(default_factory=dict)
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
        "swimming":0,"athletics":0,"survival":0,"foraging":0,"farming":0,"woodcutting":0,"mining":0,
        "hunting":0,"fishing":0,"melee":0,"shield":0,"crafting":0,"salvaging":0,"medicine":0,"scholarship":0,
        "persuasion":0,"trading":0,"stealth":0,"naturalism":0,"arcana":0
    })
    player_swimming_xp: int = 0
    player_fishing_xp: int = 0
    fishing_attempts: int = 0
    fishing_pressure: dict[str, int] = field(default_factory=dict)
    player_fishing_log: list[dict] = field(default_factory=list)
    player_salvaging_xp: int = 0
    player_salvage_perks: list[str] = field(default_factory=list)
    player_salvage_respecs: int = 1
    player_salvage_dossiers: dict[str, list[str]] = field(default_factory=dict)
    salvaging_attempts: int = 0
    player_salvage_session: dict[str, Any] = field(default_factory=dict)
    player_salvage_log: list[dict] = field(default_factory=list)
    player_talents: list[str] = field(default_factory=list)
    player_knowledge: list[str] = field(default_factory=lambda: ["craft:stoneworking", "craft:leatherwork"])
    # Discovery crafting is opt-in per world for backward compatibility. New
    # worlds enable it; v1-v6 saves retain the legacy visible-recipe behavior.
    player_crafting_discovery_enabled: bool = False
    player_discovered_items: list[str] = field(default_factory=list)
    player_discovered_recipes: list[str] = field(default_factory=list)
    player_unseen_recipes: list[str] = field(default_factory=list)
    player_crafting_experiments: int = 0
    # Recent experiment chronology; the complete learned catalogue stays above.
    player_crafting_log: list[dict[str, Any]] = field(default_factory=list)
    player_crafting_hints: list[dict[str, str]] = field(default_factory=list)
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
    player_disengage_turn: int = -1
    player_hunting_stance: str = "normal"
    player_hunting_xp: int = 0
    player_body_parts: dict[str, int] = field(default_factory=lambda: {"head":100,"neck":100,"torso":100,"left_arm":100,"right_arm":100,"left_leg":100,"right_leg":100})
    player_wounds: list[dict] = field(default_factory=list)
    player_combat_log: list[dict] = field(default_factory=list)
    player_infections: list[str] = field(default_factory=list)
    player_immunities: dict[str, int] = field(default_factory=dict)
    player_nutrition: dict[str, int] = field(default_factory=lambda: {"protein":35,"vegetable":35,"grain":35,"fruit":35,"fats":35})
    player_diet_history: list[dict] = field(default_factory=list)
    player_food_effects: dict[str, int] = field(default_factory=dict)
    player_bounties: dict[str, int] = field(default_factory=dict)
    player_crime_heat: dict[str, int] = field(default_factory=dict)
    player_stealth_mode: bool = False
    player_casing_property_id: str = ""
    player_trespass_property_id: str = ""
    player_toll_passes: dict[str, int] = field(default_factory=dict)
    casing_intel: dict[str, CasingIntelState] = field(default_factory=dict)
    discovered_tiles: DiscoveryTiles | list[str] = field(default_factory=DiscoveryTiles)
    discovered_settlements: list[str] = field(default_factory=list)
    visited_settlements: list[str] = field(default_factory=list)
    discovered_npcs: list[str] = field(default_factory=list)
    # A name learned through testimony is not an exchange of introductions.
    # Entries grow only with personally met, persistent named people.
    introduced_npcs: list[str] = field(default_factory=list)
    discovered_factions: list[str] = field(default_factory=list)
    discovered_sites: list[str] = field(default_factory=list)
    discovered_species: list[str] = field(default_factory=list)
    discovered_events: list[str] = field(default_factory=list)
    discovered_routes: list[str] = field(default_factory=list)
    # Political geography is testimony, not omniscient map data. Each entry is
    # a bounded snapshot learned from an inhabitant and may become stale.
    learned_regions: dict[str, dict[str, Any]] = field(default_factory=dict)
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
        discovery = self.discovered_tiles if isinstance(self.discovered_tiles, DiscoveryTiles) else DiscoveryTiles(self.discovered_tiles)
        return {
            "clock_minute": self.clock_minute,
            "player_fx": float(self.player_fx), "player_fy": float(self.player_fy),
            "interiors": rows(self.interiors), "interior_actors": rows(self.interior_actors),
            "homesteads": {uid: dict(site, stored=dict(site.get("stored", {}))) for uid,site in self.homesteads.items()},
            "structures": rows(self.structures), "roofs": rows(self.roofs), "containers": rows(self.containers), "soils": rows(self.soils), "ground_piles": rows(self.ground_piles), "carcasses": rows(self.carcasses), "processing_jobs": rows(self.processing_jobs), "prepared_meals": rows(self.prepared_meals), "crops": rows(self.crops),
            "creatures": rows(self.creatures), "animal_signs": rows(self.animal_signs), "animal_homes": rows(self.animal_homes), "cohorts": rows(self.cohorts), "npcs": rows(self.npcs), "households": rows(self.households), "household_deliveries": rows(self.household_deliveries), "workplace_logistics": rows(self.workplace_logistics), "workplace_shipments": rows(self.workplace_shipments), "settlements": rows(self.settlements),
            "factions": rows(self.factions), "claim_monuments": rows(self.claim_monuments), "territory_control": rows(self.territory_control), "caravans": rows(self.caravans), "labor_reservations": rows(self.labor_reservations), "activity_reservations": rows(self.activity_reservations), "physical_goods_transfers": rows(self.physical_goods_transfers), "mining_trips": rows(self.mining_trips), "trade_routes": rows(self.trade_routes), "route_infrastructure": rows(self.route_infrastructure), "border_posts": rows(self.border_posts), "theft_records": rows(self.theft_records), "market_transactions": rows(self.market_transactions), "properties": rows(self.properties), "casing_intel": rows(self.casing_intel), "door_security": rows(self.door_security), "physical_keys": rows(self.physical_keys), "trespass_states": rows(self.trespass_states), "security_incidents": rows(self.security_incidents), "migration_cohorts": rows(self.migration_cohorts), "history": [asdict(x) for x in self.history[-6000:]], "history_archive": dict(self.history_archive), "dungeon_sites": rows(self.dungeon_sites), "offices": rows(self.offices), "dynasties": rows(self.dynasties), "claims": rows(self.claims), "graves": rows(self.graves),
            "fires": rows(self.fires), "fluids": rows(self.fluids), "diseases": rows(self.diseases), "infections": rows(self.infections), "magic_laws": rows(self.magic_laws), "magic_traditions": rows(self.magic_traditions), "spells": rows(self.spells), "rituals": rows(self.rituals), "arcane_contamination": rows(self.arcane_contamination), "myths": rows(self.myths),
            "cultures": rows(self.cultures), "religions": rows(self.religions), "libraries": rows(self.libraries), "knowledge_schools": rows(self.knowledge_schools), "religious_institutions": rows(self.religious_institutions), "player_name": self.player_name, "player_origin": self.player_origin, "player_sex": self.player_sex, "player_sprite_index": int(self.player_sprite_index), "player_attributes": dict(self.player_attributes), "player_skills": dict(self.player_skills), "player_swimming_xp": self.player_swimming_xp, "player_fishing_xp": self.player_fishing_xp, "fishing_attempts": self.fishing_attempts, "fishing_pressure": dict(self.fishing_pressure), "player_fishing_log": list(self.player_fishing_log[-240:]), "player_talents": list(self.player_talents), "player_knowledge": list(self.player_knowledge), "player_crafting_discovery_enabled": self.player_crafting_discovery_enabled, "player_discovered_items": sorted(set(self.player_discovered_items)), "player_discovered_recipes": sorted(set(self.player_discovered_recipes)), "player_unseen_recipes": sorted(set(self.player_unseen_recipes)), "player_crafting_experiments": self.player_crafting_experiments, "player_literacy": self.player_literacy, "player_languages": dict(self.player_languages),
            "player_crafting_log": deepcopy(self.player_crafting_log[-80:]), "player_crafting_hints": deepcopy(self.player_crafting_hints[-200:]),
            "player_salvaging_xp": self.player_salvaging_xp, "player_salvage_perks": list(self.player_salvage_perks), "player_salvage_respecs": self.player_salvage_respecs, "player_salvage_dossiers": deepcopy(self.player_salvage_dossiers), "salvaging_attempts": self.salvaging_attempts,
            "player_salvage_session": deepcopy(self.player_salvage_session), "player_salvage_log": deepcopy(self.player_salvage_log[-80:]),
            "player_equipment": dict(self.player_equipment), "player_equipped_artifacts": dict(self.player_equipped_artifacts), "player_readied_weapon": self.player_readied_weapon, "player_aim_target": self.player_aim_target, "player_aim_zone": self.player_aim_zone, "player_aim_quality": int(self.player_aim_quality), "player_facing_dx": int(self.player_facing_dx), "player_facing_dy": int(self.player_facing_dy), "player_guarding": bool(self.player_guarding), "player_defense_mode": self.player_defense_mode, "player_defense_quality": int(self.player_defense_quality), "player_disengage_turn": int(self.player_disengage_turn), "player_hunting_stance": self.player_hunting_stance, "player_hunting_xp": int(self.player_hunting_xp), "player_body_parts": dict(self.player_body_parts), "player_wounds": list(self.player_wounds), "player_combat_log": list(self.player_combat_log[-240:]), "player_infections": list(self.player_infections), "player_immunities": dict(self.player_immunities), "player_nutrition": dict(self.player_nutrition), "player_diet_history": list(self.player_diet_history[-240:]), "player_food_effects": dict(self.player_food_effects),
            "player_bounties": dict(self.player_bounties), "player_crime_heat": dict(self.player_crime_heat),
            "player_stealth_mode": bool(self.player_stealth_mode),
            "player_casing_property_id": self.player_casing_property_id,
            "player_trespass_property_id": self.player_trespass_property_id,
            "player_toll_passes": dict(self.player_toll_passes),
            # Optional versioned schema-3 fields replace the lossy legacy cap.
            # Explicit legacy export is available on DiscoveryTiles; retaining
            # an expanded duplicate here would defeat compact checkpoints.
            "discovered_tiles": [],
            "discovered_format_version": DISCOVERY_FORMAT_VERSION,
            "discovered_chunks": discovery.to_chunks(),
            "discovered_settlements": sorted(set(self.discovered_settlements)), "visited_settlements": sorted(set(self.visited_settlements)), "discovered_npcs": sorted(set(self.discovered_npcs)),
            "introduced_npcs": sorted(set(self.introduced_npcs)),
            "discovered_factions": sorted(set(self.discovered_factions)), "discovered_sites": sorted(set(self.discovered_sites)),
            "discovered_species": sorted(set(self.discovered_species)), "discovered_events": sorted(set(self.discovered_events)), "discovered_routes": sorted(set(self.discovered_routes)), "learned_regions": dict(self.learned_regions), "population_reports": dict(self.population_reports), "player_rumors": list(dict.fromkeys(self.player_rumors))[-40:], "resource_depletion": dict(self.resource_depletion),
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
        # All blueprint inventory is explicit authoritative stock, not a cache.
        s.homesteads = {uid: dict(site, stored=dict(site.get("stored", {}))) for uid,site in raw.get("homesteads", {}).items()}
        from worldseed.systems.interior_state import InteriorPlan, InteriorActor
        s.interiors = {k: InteriorPlan.from_dict(v) for k, v in raw.get("interiors", {}).items()}
        s.interior_actors = {k: InteriorActor.from_dict(v) for k, v in raw.get("interior_actors", {}).items()}
        scalar = ["player_swimming_xp","player_fishing_xp","fishing_attempts","fishing_pressure","player_fishing_log","clock_minute","player_fx","player_fy","player_name","player_origin","player_sex","player_sprite_index","player_attributes","player_skills","player_talents","player_knowledge","player_crafting_discovery_enabled","player_discovered_items","player_discovered_recipes","player_unseen_recipes","player_crafting_experiments","player_literacy","player_languages","player_equipment","player_equipped_artifacts","player_readied_weapon","player_aim_target","player_aim_zone","player_aim_quality","player_facing_dx","player_facing_dy","player_guarding","player_defense_mode","player_defense_quality","player_disengage_turn","player_hunting_stance","player_hunting_xp","player_body_parts","player_wounds","player_combat_log","player_infections","player_immunities","player_nutrition","player_diet_history","player_food_effects","player_bounties","player_crime_heat","player_stealth_mode","player_casing_property_id","player_trespass_property_id","player_toll_passes","discovered_tiles","discovered_settlements","visited_settlements","discovered_npcs","discovered_factions","discovered_sites","discovered_species","discovered_events","discovered_routes","learned_regions","population_reports","player_rumors","resource_depletion","realized_regions","next_uid","last_daily_minute","last_hourly_minute","last_monthly_minute","last_offline_wall_time","offline_policy","last_offline_minutes","last_offline_summary","ui_color","ui_unicode","ui_density","history_archive"]
        for key in scalar:
            if key in raw:
                setattr(s, key, raw[key])
        if "discovered_chunks" in raw or "discovered_format_version" in raw:
            # Reject corrupted/unknown compact data instead of forgetting cells.
            s.discovered_tiles = DiscoveryTiles.from_chunks(raw.get("discovered_chunks"), raw.get("discovered_format_version"))
            s.discovered_tiles.extend(raw.get("discovered_tiles", []))
        else:
            s.discovered_tiles = DiscoveryTiles(raw.get("discovered_tiles", []))
        s.player_crafting_log = deepcopy(raw.get("player_crafting_log", [])[-80:])
        s.player_crafting_hints = deepcopy(raw.get("player_crafting_hints", [])[-200:])
        # Active projects have already spent their input; retain their exact
        # choices and random identity without aliasing the caller's save data.
        for key in ("player_salvaging_xp", "player_salvage_perks", "player_salvage_respecs", "player_salvage_dossiers", "salvaging_attempts", "player_salvage_session", "player_salvage_log"):
            if key in raw:
                setattr(s, key, deepcopy(raw[key]))
        # Old saves disclosed identity on first speech. Preserve those already
        # established conversations; fresh saves require the explicit exchange.
        s.introduced_npcs = sorted(set(raw.get("introduced_npcs", s.discovered_npcs)))
        maps = {
            "structures":StructureInstance,"roofs":RoofState,"containers":ContainerState,"soils":SoilState,"ground_piles":GroundPile,"carcasses":CarcassState,"processing_jobs":ProcessingJobState,"prepared_meals":PreparedMealState,"crops":CropPlot,"creatures":CreatureState,"animal_signs":AnimalSignState,"animal_homes":AnimalHomeState,"cohorts":PopulationCohort,
            "npcs":NPCState,"households":HouseholdState,"household_deliveries":HouseholdDeliveryState,"workplace_logistics":WorkplaceLogisticsState,"workplace_shipments":WorkplaceShipmentState,"settlements":SettlementState,"factions":FactionState,"claim_monuments":ClaimMonumentState,"territory_control":TerritoryControlState,"caravans":CaravanState,"labor_reservations":LaborReservationState,"activity_reservations":ActivityReservationState,"physical_goods_transfers":PhysicalGoodsTransferState,"mining_trips":MiningTripState,"trade_routes":TradeRouteState,"route_infrastructure":RouteInfrastructureState,"border_posts":BorderPostState,"theft_records":TheftRecordState,"market_transactions":MarketTransactionState,"properties":PropertyState,"casing_intel":CasingIntelState,"door_security":DoorSecurityState,"physical_keys":PhysicalKeyState,"trespass_states":TrespassState,"security_incidents":SecurityIncidentState,"migration_cohorts":MigrationCohortState,"dungeon_sites":DungeonSiteState,"offices":OfficeState,"dynasties":DynastyState,"claims":ClaimState,"graves":GraveState,"fires":FireCell,"fluids":FluidCell,
            "diseases":DiseaseState,"infections":InfectionState,"magic_laws":MagicLaw,"magic_traditions":MagicTraditionState,"spells":SpellState,"rituals":RitualState,"arcane_contamination":ArcaneContaminationState,"myths":MythState,"cultures":CultureState,"religions":ReligionState,"libraries":LibraryState,"knowledge_schools":KnowledgeSchoolState,"religious_institutions":ReligiousInstitutionState,"artifacts":ArtifactState,"books":BookState,"metal_batches":MetalBatchState,
        }
        # New skills must appear on legacy saves even when the old save
        # serialized the entire skill dictionary before the skill existed.
        s.player_skills.setdefault("shield",0)
        s.player_skills.setdefault("stealth",0)
        s.player_skills.setdefault("salvaging",0)
        for key, typ in maps.items():
            values = raw.get(key, {})
            if key == "npcs":
                # Copy the row rather than adding a migration field to the
                # caller's raw save. Explicit v1/v2 pins survive later saves.
                values = {uid: {"portrait_version": 1, **row} for uid, row in values.items()}
            setattr(s, key, {k:typ(**v) for k,v in values.items()})
        s.history = [HistoricEvent(**v) for v in raw.get("history", [])]
        s.legacy = [LegacyCharacter(**v) for v in raw.get("legacy", [])]
        return s


def pos_key(x: int, y: int, z: int) -> str:
    return f"{x},{y},{z}"
