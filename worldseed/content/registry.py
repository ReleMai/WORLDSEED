from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


def _tuple(raw) -> tuple[str, ...]:
    return tuple(raw or [])


@dataclass(frozen=True, slots=True)
class TerrainDef:
    id: str; name: str; glyph: str; ascii_glyph: str; ansi_color: int; passable: bool
    gather_item: str | None = None; gather_amount: int = 0; depleted_to: str | None = None
    tags: tuple[str, ...] = (); blocks_sight: bool = False


@dataclass(frozen=True, slots=True)
class ResourceFeatureDef:
    id: str; name: str; glyph: str; ascii_glyph: str; ansi_color: int; tags: tuple[str, ...]
    required_tool_tag: str | None; required_tool_power: int; minutes: int; regrow_days: int
    yields: dict[str, tuple[int, int]]; blocks_movement: bool = False; blocks_sight: bool = False
    description: str = ""; flavor: str = ""; terrains: tuple[str, ...] = ()
    min_temp: int = 0; max_temp: int = 65535; min_moisture: int = 0; max_moisture: int = 65535
    seasons: tuple[str, ...] = (); density: int = 100; patch_scale: int = 1
    container_structure_id: str | None = None
    container_capacity_mass_g: int = 0
    container_capacity_volume_ml: int = 0
    container_loot: dict[str, tuple[int, int]] = field(default_factory=dict)
    container_salvage: dict[str, tuple[int, int]] = field(default_factory=dict)
    container_movable: bool = False


@dataclass(frozen=True, slots=True)
class MaterialDef:
    id: str; name: str; density: int; hardness: int; toughness: int; edge: int
    corrosion: int; flammability: int; value: int


@dataclass(frozen=True, slots=True)
class ItemDef:
    id: str; name: str; material: str | None = None; mass_g: int = 0; volume_ml: int = 0
    nutrition: int = 0; hydration: int = 0; tool_power: int = 0; weapon_damage: int = 0
    damage_type: str = "blunt"; tags: tuple[str, ...] = (); base_value: int = 1
    equip_slot: str | None = None; armor: int = 0; coverage: tuple[str, ...] = (); insulation: int = 0
    description: str = ""; flavor: str = ""; category: str = "misc"; subcategory: str = ""
    calories: int = 0; protein: int = 0; carbs: int = 0; fat: int = 0; fiber: int = 0
    food_groups: tuple[str, ...] = (); tool_qualities: dict[str, int] = field(default_factory=dict)
    spoilage_hours: int = 0; utility_roles: tuple[str, ...] = (); range: int = 1
    ammo_item: str | None = None; weapon_class: str = ""; reach: int = 1; accuracy: int = 0
    stamina_cost: int = 5; throwable: bool = False; recovery_percent: int = 0; two_handed: bool = False
    shield_type: str = ""; shield_melee_coverage: int = 0; shield_ranged_coverage: int = 0
    shield_block: int = 0; shield_stability: int = 0; shield_stamina_cost: int = 0
    shield_body_coverage: dict[str, int] = field(default_factory=dict)

    def quality(self, key: str) -> int:
        if key in self.tool_qualities:
            return int(self.tool_qualities[key])
        # Backward-compatible bridge for RC6 items.
        if key == "mine" and "pick" in self.tags: return int(self.tool_power)
        if key == "chop" and "axe" in self.tags: return int(self.tool_power)
        if key == "cut" and self.damage_type == "cut": return max(1, int(self.weapon_damage)//4)
        return 0


@dataclass(frozen=True, slots=True)
class RecipeDef:
    id: str; name: str; inputs: dict[str, int]; outputs: dict[str, int]; minutes: int
    station: str | None = None; knowledge: str | None = None; catalysts: dict[str, int] = field(default_factory=dict)
    process: str | None = None; description: str = ""; category: str = "general"
    skill: str = "crafting"; difficulty: int = 0; tool_qualities: dict[str, int] = field(default_factory=dict)
    discovery_items: tuple[str, ...] = (); discovery_mode: str = ""


@dataclass(frozen=True, slots=True)
class StructureDef:
    id: str; name: str; glyph: str; passable: bool; blocks_sight: bool; cost: dict[str, int]
    tags: tuple[str, ...] = (); capacity_mass_g: int = 0; capacity_volume_ml: int = 0
    support_strength: int = 0; load: int = 0; description: str = ""; uses: tuple[str, ...] = ()
    comfort: int = 0; work_bonus: int = 0; warmth: int = 0; shelter: int = 0


@dataclass(frozen=True, slots=True)
class SettlementPieceDef:
    id: str; name: str; category: str; layer: str; glyph: str
    tags: tuple[str, ...] = (); room_tags: tuple[str, ...] = (); settlement_roles: tuple[str, ...] = ()
    material: str = ""; passable: bool = True; blocks_sight: bool = False; enclosure_role: str = ""
    workplace_role: str = ""; interior_allowed: bool = True; exterior_allowed: bool = True
    road_access_required: bool = False; support_strength: int = 0; comfort: int = 0; work_bonus: int = 0
    materialization_family: str = ""


@dataclass(frozen=True, slots=True)
class ComponentDesignDef:
    id: str; name: str; output_item: str; minutes: int; station: str | None; knowledge: str | None
    primary_component: str; components: dict[str, dict[str, dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class SpeciesDef:
    id: str; name: str; glyph: str; diet: str; mass_kg: int; max_hp: int; damage: int
    aggression: int; speed: int; reproduction: int; mortality: int; carrying_capacity: int
    habitats: tuple[str, ...]; drops: dict[str, int]; body: dict[str, int]
    description: str = ""; flavor: str = ""; min_temp: int = 0; max_temp: int = 65535
    min_moisture: int = 0; max_moisture: int = 65535; group_min: int = 1; group_max: int = 3
    attacks: tuple[dict[str, Any], ...] = (); carcass: dict[str, int] = field(default_factory=dict)
    vision: int = 8; hearing: int = 8; scent: int = 6; flee_threshold: int = 55
    defensive_aggression: int = 20; stamina: int = 100; trackability: int = 50; herd_response: int = 50
    combat_style: str = "generic"; charge_range: int = 0; charge_power: int = 0
    display_range: int = 0; pack_coordination: int = 0; herd_cohesion: int = 0



@dataclass(frozen=True, slots=True)
class FishDef:
    id: str; name: str; item_id: str; habitats: tuple[str, ...]
    min_weight_g: int; max_weight_g: int; rarity: int; fight: int
    min_temp: int = 0; max_temp: int = 65535
    structures: tuple[str, ...] = (); methods: tuple[str, ...] = ("hand","spear","rod","net")
    bait_affinity: dict[str, int] = field(default_factory=dict)
    schooling: int = 1; quality_base: int = 50
    description: str = ""

@dataclass(frozen=True, slots=True)
class DiseaseDef:
    id: str; name: str; transmissions: tuple[str, ...]; incubation_hours: int; illness_hours: int
    contagiousness: int; severity: int; mortality_permille: int; immunity_days: int
    environmental_survival_hours: int; symptoms: tuple[str, ...] = (); season_bias: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SettlementProcessDef:
    id: str; name: str; occupation: str; workers: int; inputs: dict[str, int]; outputs: dict[str, int]
    priority_good: str; knowledge: str | None = None


@dataclass(frozen=True, slots=True)
class CropDef:
    id: str; name: str; seed_item: str; harvest_item: str; growth_hours: int; min_temp: int; max_temp: int
    water_use: int; yield_min: int; yield_max: int; seasons: tuple[str, ...]
    nitrogen: int = 3; phosphorus: int = 2; potassium: int = 2; disease_family: str = "general"
    description: str = ""


@dataclass(frozen=True, slots=True)
class CookingMethodDef:
    id: str; name: str; station: str; cookware: str | None; min_ingredients: int; max_ingredients: int
    allowed_tags: tuple[str, ...]; minutes: int; satiety_percent: int = 120; hydration_bonus: int = 0
    description: str = ""; effect: str = ""; requires_water: bool = False


class ContentRegistry:
    def __init__(self) -> None:
        self.terrains: dict[str, TerrainDef] = {}; self.resources: dict[str, ResourceFeatureDef] = {}
        self.items: dict[str, ItemDef] = {}; self.materials: dict[str, MaterialDef] = {}; self.recipes: dict[str, RecipeDef] = {}
        self.structures: dict[str, StructureDef] = {}; self.settlement_pieces: dict[str, SettlementPieceDef] = {}
        self.designs: dict[str, ComponentDesignDef] = {}
        self.species: dict[str, SpeciesDef] = {}; self.fish: dict[str, FishDef] = {}; self.crops: dict[str, CropDef] = {}
        self.settlement_processes: dict[str, SettlementProcessDef] = {}; self.diseases: dict[str, DiseaseDef] = {}
        self.cooking_methods: dict[str, CookingMethodDef] = {}
        self.terrain_ids: list[str] = []; self._terrain_index: dict[str, int] = {}

    @classmethod
    def load(cls, data_dir: Path, extra_data_dirs: list[Path] | None = None) -> "ContentRegistry":
        reg=cls(); reg._load_data_dir(data_dir, required=True)
        for extra in extra_data_dirs or []: reg._load_data_dir(extra, required=False)
        reg._validate(); return reg

    def _load_data_dir(self, data_dir: Path, required: bool=False) -> None:
        loaders=[
            ("materials.json",self._load_materials),("items.json",self._load_items),("terrain.json",self._load_terrain),
            ("resources.json",self._load_resources),("recipes.json",self._load_recipes),("structures.json",self._load_structures),
            ("settlement_pieces.json",self._load_settlement_pieces),("designs.json",self._load_designs),("species.json",self._load_species),("fish.json",self._load_fish),("crops.json",self._load_crops),
            ("settlement_processes.json",self._load_settlement_processes),("diseases.json",self._load_diseases),
            ("cooking_methods.json",self._load_cooking_methods),]
        for filename,loader in loaders:
            path=data_dir/filename
            if path.exists(): loader(path)
            elif required and filename != "cooking_methods.json": raise FileNotFoundError(path)

    @staticmethod
    def _json(path:Path): return json.loads(path.read_text(encoding="utf-8"))

    def _load_materials(self,path):
        for raw in self._json(path):
            obj=MaterialDef(**raw)
            if obj.id in self.materials: raise ValueError(f"Duplicate material id: {obj.id}")
            self.materials[obj.id]=obj

    def _load_items(self,path):
        for raw in self._json(path):
            raw=dict(raw)
            # Presentation metadata is authored beside the item for maintainability,
            # but is not simulation state.
            raw.pop("asset", None)
            raw["tags"]=_tuple(raw.get("tags")); raw["coverage"]=_tuple(raw.get("coverage")); raw["food_groups"]=_tuple(raw.get("food_groups")); raw["utility_roles"]=_tuple(raw.get("utility_roles")); raw["tool_qualities"]={str(k):int(v) for k,v in raw.get("tool_qualities",{}).items()}
            obj=ItemDef(**raw)
            if obj.id in self.items: raise ValueError(f"Duplicate item id: {obj.id}")
            self.items[obj.id]=obj

    def _load_terrain(self,path):
        for raw in self._json(path):
            obj=TerrainDef(id=raw["id"],name=raw["name"],glyph=raw["glyph"],ascii_glyph=raw.get("ascii_glyph",raw["glyph"]),ansi_color=int(raw.get("ansi_color",37)),passable=bool(raw["passable"]),gather_item=raw.get("gather_item"),gather_amount=int(raw.get("gather_amount",0)),depleted_to=raw.get("depleted_to"),tags=_tuple(raw.get("tags")),blocks_sight=bool(raw.get("blocks_sight",False)))
            if obj.id in self.terrains: raise ValueError(f"Duplicate terrain id: {obj.id}")
            self._terrain_index[obj.id]=len(self.terrain_ids); self.terrain_ids.append(obj.id); self.terrains[obj.id]=obj

    def _load_resources(self,path):
        for raw in self._json(path):
            obj=ResourceFeatureDef(id=raw["id"],name=raw["name"],glyph=raw["glyph"],ascii_glyph=raw.get("ascii_glyph",raw["glyph"]),ansi_color=int(raw.get("ansi_color",37)),tags=_tuple(raw.get("tags")),required_tool_tag=raw.get("required_tool_tag"),required_tool_power=int(raw.get("required_tool_power",0)),minutes=int(raw.get("minutes",10)),regrow_days=int(raw.get("regrow_days",0)),yields={iid:(int(v[0]),int(v[1])) for iid,v in raw.get("yields",{}).items()},blocks_movement=bool(raw.get("blocks_movement",False)),blocks_sight=bool(raw.get("blocks_sight",False)),description=raw.get("description",""),flavor=raw.get("flavor",""),terrains=_tuple(raw.get("terrains")),min_temp=int(raw.get("min_temp",0)),max_temp=int(raw.get("max_temp",65535)),min_moisture=int(raw.get("min_moisture",0)),max_moisture=int(raw.get("max_moisture",65535)),seasons=_tuple(raw.get("seasons")),density=int(raw.get("density",100)),patch_scale=max(1,int(raw.get("patch_scale",1))),container_structure_id=raw.get("container_structure_id"),container_capacity_mass_g=int(raw.get("container_capacity_mass_g",0)),container_capacity_volume_ml=int(raw.get("container_capacity_volume_ml",0)),container_loot={iid:(int(v[0]),int(v[1])) for iid,v in raw.get("container_loot",{}).items()},container_salvage={iid:(int(v[0]),int(v[1])) for iid,v in raw.get("container_salvage",{}).items()},container_movable=bool(raw.get("container_movable",False)))
            if obj.id in self.resources: raise ValueError(f"Duplicate resource id: {obj.id}")
            self.resources[obj.id]=obj

    def _load_recipes(self,path):
        for raw in self._json(path):
            obj=RecipeDef(id=raw["id"],name=raw["name"],inputs=dict(raw.get("inputs",{})),outputs=dict(raw.get("outputs",{})),minutes=int(raw["minutes"]),station=raw.get("station"),knowledge=raw.get("knowledge"),catalysts=dict(raw.get("catalysts",{})),process=raw.get("process"),description=raw.get("description",""),category=raw.get("category","general"),skill=raw.get("skill","crafting"),difficulty=int(raw.get("difficulty",0)),tool_qualities={str(k):int(v) for k,v in raw.get("tool_qualities",{}).items()},discovery_items=_tuple(raw.get("discovery_items")),discovery_mode=str(raw.get("discovery_mode", "")))
            if obj.id in self.recipes: raise ValueError(f"Duplicate recipe id: {obj.id}")
            self.recipes[obj.id]=obj

    def _load_structures(self,path):
        for raw in self._json(path):
            obj=StructureDef(id=raw["id"],name=raw["name"],glyph=raw["glyph"],passable=bool(raw["passable"]),blocks_sight=bool(raw["blocks_sight"]),cost=dict(raw.get("cost",{})),tags=_tuple(raw.get("tags")),capacity_mass_g=int(raw.get("capacity_mass_g",0)),capacity_volume_ml=int(raw.get("capacity_volume_ml",0)),support_strength=int(raw.get("support_strength",0)),load=int(raw.get("load",0)),description=raw.get("description",""),uses=_tuple(raw.get("uses")),comfort=int(raw.get("comfort",0)),work_bonus=int(raw.get("work_bonus",0)),warmth=int(raw.get("warmth",0)),shelter=int(raw.get("shelter",0)))
            if obj.id in self.structures: raise ValueError(f"Duplicate structure id: {obj.id}")
            self.structures[obj.id]=obj

    def _load_settlement_pieces(self,path):
        for raw in self._json(path):
            obj=SettlementPieceDef(
                id=str(raw["id"]), name=str(raw["name"]), category=str(raw["category"]), layer=str(raw.get("layer","structure")),
                glyph=str(raw.get("glyph","?")), tags=_tuple(raw.get("tags")), room_tags=_tuple(raw.get("room_tags")),
                settlement_roles=_tuple(raw.get("settlement_roles")), material=str(raw.get("material","")),
                passable=bool(raw.get("passable",True)), blocks_sight=bool(raw.get("blocks_sight",False)),
                enclosure_role=str(raw.get("enclosure_role","")), workplace_role=str(raw.get("workplace_role","")),
                interior_allowed=bool(raw.get("interior_allowed",True)), exterior_allowed=bool(raw.get("exterior_allowed",True)),
                road_access_required=bool(raw.get("road_access_required",False)), support_strength=int(raw.get("support_strength",0)),
                comfort=int(raw.get("comfort",0)), work_bonus=int(raw.get("work_bonus",0)),
                materialization_family=str(raw.get("materialization_family",raw.get("category",""))),
            )
            if obj.id in self.settlement_pieces: raise ValueError(f"Duplicate settlement piece id: {obj.id}")
            self.settlement_pieces[obj.id]=obj

    def _load_designs(self,path):
        for raw in self._json(path):
            obj=ComponentDesignDef(id=raw["id"],name=raw["name"],output_item=raw["output_item"],minutes=int(raw["minutes"]),station=raw.get("station"),knowledge=raw.get("knowledge"),primary_component=raw["primary_component"],components={k:{iid:dict(meta) for iid,meta in choices.items()} for k,choices in raw["components"].items()})
            if obj.id in self.designs: raise ValueError(f"Duplicate design id: {obj.id}")
            self.designs[obj.id]=obj

    def _load_species(self,path):
        for raw in self._json(path):
            obj=SpeciesDef(id=raw["id"],name=raw["name"],glyph=raw["glyph"],diet=raw["diet"],mass_kg=int(raw["mass_kg"]),max_hp=int(raw["max_hp"]),damage=int(raw["damage"]),aggression=int(raw["aggression"]),speed=int(raw["speed"]),reproduction=int(raw["reproduction"]),mortality=int(raw["mortality"]),carrying_capacity=int(raw["carrying_capacity"]),habitats=_tuple(raw.get("habitats")),drops=dict(raw.get("drops",{})),body=dict(raw.get("body",{})),description=raw.get("description",""),flavor=raw.get("flavor",""),min_temp=int(raw.get("min_temp",0)),max_temp=int(raw.get("max_temp",65535)),min_moisture=int(raw.get("min_moisture",0)),max_moisture=int(raw.get("max_moisture",65535)),group_min=int(raw.get("group_min",1)),group_max=int(raw.get("group_max",3)),attacks=tuple(dict(x) for x in raw.get("attacks",[])),carcass={str(k):int(v) for k,v in raw.get("carcass",{}).items()},vision=max(1,int(raw.get("vision",8))),hearing=max(1,int(raw.get("hearing",8))),scent=max(0,int(raw.get("scent",6))),flee_threshold=max(1,min(100,int(raw.get("flee_threshold",55)))),defensive_aggression=max(0,min(100,int(raw.get("defensive_aggression",raw.get("aggression",20))))),stamina=max(20,int(raw.get("stamina",100))),trackability=max(0,min(100,int(raw.get("trackability",50)))),herd_response=max(0,min(100,int(raw.get("herd_response",50)))),combat_style=str(raw.get("combat_style","generic")),charge_range=max(0,min(12,int(raw.get("charge_range",0)))),charge_power=max(0,min(100,int(raw.get("charge_power",0)))),display_range=max(0,min(12,int(raw.get("display_range",0)))),pack_coordination=max(0,min(100,int(raw.get("pack_coordination",0)))),herd_cohesion=max(0,min(100,int(raw.get("herd_cohesion",raw.get("herd_response",0))))))
            if obj.id in self.species: raise ValueError(f"Duplicate species id: {obj.id}")
            self.species[obj.id]=obj

    def _load_fish(self,path):
        for raw in self._json(path):
            obj=FishDef(
                id=raw["id"], name=raw["name"], item_id=raw["item_id"],
                habitats=_tuple(raw.get("habitats")),
                min_weight_g=int(raw["min_weight_g"]), max_weight_g=int(raw["max_weight_g"]),
                rarity=int(raw.get("rarity",50)), fight=int(raw.get("fight",20)),
                min_temp=int(raw.get("min_temp",0)), max_temp=int(raw.get("max_temp",65535)),
                structures=_tuple(raw.get("structures")), methods=_tuple(raw.get("methods") or ("hand","spear","rod","net")),
                bait_affinity={str(k):int(v) for k,v in raw.get("bait_affinity",{}).items()},
                schooling=max(1,int(raw.get("schooling",1))), quality_base=int(raw.get("quality_base",50)),
                description=raw.get("description",""),
            )
            if obj.id in self.fish: raise ValueError(f"Duplicate fish id: {obj.id}")
            self.fish[obj.id]=obj

    def _load_diseases(self,path):
        for raw in self._json(path):
            raw=dict(raw); raw["transmissions"]=_tuple(raw.get("transmissions")); raw["symptoms"]=_tuple(raw.get("symptoms")); raw["season_bias"]=_tuple(raw.get("season_bias")); obj=DiseaseDef(**raw)
            if obj.id in self.diseases: raise ValueError(f"Duplicate disease id: {obj.id}")
            self.diseases[obj.id]=obj

    def _load_crops(self,path):
        for raw in self._json(path):
            obj=CropDef(id=raw["id"],name=raw["name"],seed_item=raw["seed_item"],harvest_item=raw["harvest_item"],growth_hours=int(raw["growth_hours"]),min_temp=int(raw["min_temp"]),max_temp=int(raw["max_temp"]),water_use=int(raw["water_use"]),yield_min=int(raw["yield_min"]),yield_max=int(raw["yield_max"]),seasons=_tuple(raw.get("seasons")),nitrogen=int(raw.get("nitrogen",3)),phosphorus=int(raw.get("phosphorus",2)),potassium=int(raw.get("potassium",2)),disease_family=raw.get("disease_family","general"),description=raw.get("description",""))
            if obj.id in self.crops: raise ValueError(f"Duplicate crop id: {obj.id}")
            self.crops[obj.id]=obj

    def _load_settlement_processes(self,path):
        for raw in self._json(path):
            obj=SettlementProcessDef(id=raw["id"],name=raw["name"],occupation=raw["occupation"],workers=int(raw["workers"]),inputs=dict(raw.get("inputs",{})),outputs=dict(raw.get("outputs",{})),priority_good=raw["priority_good"],knowledge=raw.get("knowledge"))
            if obj.id in self.settlement_processes: raise ValueError(f"Duplicate settlement process id: {obj.id}")
            self.settlement_processes[obj.id]=obj

    def _load_cooking_methods(self,path):
        for raw in self._json(path):
            obj=CookingMethodDef(id=raw["id"],name=raw["name"],station=raw["station"],cookware=raw.get("cookware"),min_ingredients=int(raw.get("min_ingredients",1)),max_ingredients=int(raw.get("max_ingredients",4)),allowed_tags=_tuple(raw.get("allowed_tags")),minutes=int(raw.get("minutes",20)),satiety_percent=int(raw.get("satiety_percent",120)),hydration_bonus=int(raw.get("hydration_bonus",0)),description=raw.get("description",""),effect=raw.get("effect",""),requires_water=bool(raw.get("requires_water",False)))
            if obj.id in self.cooking_methods: raise ValueError(f"Duplicate cooking method id: {obj.id}")
            self.cooking_methods[obj.id]=obj

    def _validate(self)->None:
        namespaces=[self.items,self.materials,self.terrains,self.recipes,self.structures,self.settlement_pieces,self.designs,self.species,self.fish,self.crops,self.settlement_processes,self.diseases,self.cooking_methods]
        for table in namespaces:
            for cid in table:
                if ":" not in cid: raise ValueError(f"Content id must be namespaced: {cid}")
        for item in self.items.values():
            if item.material and item.material not in self.materials: raise ValueError(f"Unknown material {item.material} for {item.id}")
            if item.mass_g<0 or item.volume_ml<0: raise ValueError(f"Negative physical property on {item.id}")
            if item.ammo_item and item.ammo_item not in self.items: raise ValueError(f"Unknown ammo item {item.ammo_item} for {item.id}")
            if item.weapon_damage>0 and (item.range<1 or item.reach<1 or item.stamina_cost<0 or not -40<=item.accuracy<=40 or not 0<=item.recovery_percent<=100):
                raise ValueError(f"Invalid weapon handling metadata on {item.id}")
            shield_values=(item.shield_melee_coverage,item.shield_ranged_coverage,item.shield_stability)
            if any(not 0<=int(v)<=100 for v in shield_values) or item.shield_block<0 or item.shield_stamina_cost<0 or any(not 0<=int(v)<=100 for v in item.shield_body_coverage.values()):
                raise ValueError(f"Invalid shield metadata on {item.id}")
            if "shield" in item.tags and (item.equip_slot!="offhand" or not item.shield_type or max(item.shield_melee_coverage,item.shield_ranged_coverage)<=0):
                raise ValueError(f"Shield {item.id} requires offhand slot and coverage metadata")
        for terrain in self.terrains.values():
            if len(terrain.glyph)!=1 or len(terrain.ascii_glyph)!=1: raise ValueError(f"Terrain glyph must be one character: {terrain.id}")
            if terrain.gather_item and terrain.gather_item not in self.items: raise ValueError(f"Unknown gather item {terrain.gather_item} on {terrain.id}")
            if terrain.depleted_to and terrain.depleted_to not in self.terrains: raise ValueError(f"Unknown depleted terrain {terrain.depleted_to} on {terrain.id}")
        for feature in self.resources.values():
            for iid in feature.yields:
                if iid not in self.items: raise ValueError(f"Unknown resource yield {iid} in {feature.id}")
            if feature.container_structure_id and feature.container_structure_id not in self.structures:
                raise ValueError(f"Unknown container structure {feature.container_structure_id} in {feature.id}")
            for iid in (*feature.container_loot.keys(),*feature.container_salvage.keys()):
                if iid not in self.items: raise ValueError(f"Unknown container item {iid} in {feature.id}")
            if "natural_container" in feature.tags and not feature.container_structure_id:
                raise ValueError(f"Natural container {feature.id} requires container_structure_id")
            if feature.container_structure_id and (feature.container_capacity_mass_g<0 or feature.container_capacity_volume_ml<0):
                raise ValueError(f"Invalid container capacity in {feature.id}")
        for recipe in self.recipes.values():
            for iid in (*recipe.inputs.keys(),*recipe.outputs.keys(),*recipe.catalysts.keys()):
                if iid not in self.items: raise ValueError(f"Unknown recipe item {iid} in {recipe.id}")
            if recipe.station and recipe.station not in self.structures: raise ValueError(f"Unknown station {recipe.station} in {recipe.id}")
        for struct in self.structures.values():
            for iid in struct.cost:
                if iid not in self.items: raise ValueError(f"Unknown construction item {iid} in {struct.id}")
        allowed_piece_categories={"wall","floor","opening","furniture","workshop","road","agriculture","mine","decoration","civic"}
        allowed_piece_layers={"structure","ground","overlay"}
        allowed_enclosure_roles={"","wall","door","opening","floor","partition"}
        for piece in self.settlement_pieces.values():
            if len(piece.glyph)!=1: raise ValueError(f"Settlement piece glyph must be one character: {piece.id}")
            if piece.category not in allowed_piece_categories: raise ValueError(f"Unknown settlement piece category {piece.category} on {piece.id}")
            if piece.layer not in allowed_piece_layers: raise ValueError(f"Unknown settlement piece layer {piece.layer} on {piece.id}")
            if piece.enclosure_role not in allowed_enclosure_roles: raise ValueError(f"Unknown enclosure role {piece.enclosure_role} on {piece.id}")
            if piece.support_strength<0 or piece.comfort<0 or piece.work_bonus<0: raise ValueError(f"Negative settlement piece property on {piece.id}")
        for crop in self.crops.values():
            if crop.seed_item not in self.items or crop.harvest_item not in self.items: raise ValueError(f"Unknown crop item in {crop.id}")
        for sp in self.species.values():
            for iid in sp.carcass:
                if iid not in self.items: raise ValueError(f"Unknown carcass yield {iid} in {sp.id}")
            for attack in sp.attacks:
                if int(attack.get("damage",sp.damage))<0: raise ValueError(f"Invalid attack damage in {sp.id}")
            if min(sp.vision,sp.hearing,sp.stamina)<=0 or not 0<=sp.scent<=100 or not 1<=sp.flee_threshold<=100 or not 0<=sp.defensive_aggression<=100 or not 0<=sp.trackability<=100 or not 0<=sp.herd_response<=100:
                raise ValueError(f"Invalid hunting behavior parameters in {sp.id}")
            if sp.combat_style not in {"generic","prey","herd_prey","charger","territorial_charger","pack_predator","solitary_predator"} or not 0<=sp.charge_range<=12 or not 0<=sp.charge_power<=100 or not 0<=sp.display_range<=12 or not 0<=sp.pack_coordination<=100 or not 0<=sp.herd_cohesion<=100:
                raise ValueError(f"Invalid tactical animal behavior parameters in {sp.id}")
        for fish in self.fish.values():
            if fish.item_id not in self.items: raise ValueError(f"Unknown fish item {fish.item_id} in {fish.id}")
            if fish.min_weight_g<=0 or fish.max_weight_g<fish.min_weight_g: raise ValueError(f"Invalid fish weight range in {fish.id}")
            if not fish.habitats: raise ValueError(f"Fish {fish.id} requires at least one habitat")
            for bait_id in fish.bait_affinity:
                if bait_id not in self.items: raise ValueError(f"Unknown bait {bait_id} in {fish.id}")
            if any(method not in {"hand","spear","rod","net"} for method in fish.methods):
                raise ValueError(f"Unknown fishing method in {fish.id}")
        for method in self.cooking_methods.values():
            if method.station not in self.structures: raise ValueError(f"Unknown cooking station {method.station} in {method.id}")
            if method.cookware and method.cookware not in self.items: raise ValueError(f"Unknown cookware {method.cookware} in {method.id}")
        for proc in self.settlement_processes.values():
            for iid in (*proc.inputs.keys(),*proc.outputs.keys()):
                if iid not in self.items: raise ValueError(f"Unknown settlement-process item {iid} in {proc.id}")
        for disease in self.diseases.values():
            if disease.incubation_hours<0 or disease.illness_hours<=0: raise ValueError(f"Invalid disease duration in {disease.id}")

    def terrain_index(self,terrain_id:str)->int:return self._terrain_index[terrain_id]
    def terrain_id(self,index:int)->str:return self.terrain_ids[index]
    def terrain(self,terrain_id:str)->TerrainDef:return self.terrains[terrain_id]
