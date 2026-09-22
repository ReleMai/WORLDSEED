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
    description: str = ""; flavor: str = ""; category: str = "misc"
    calories: int = 0; protein: int = 0; carbs: int = 0; fat: int = 0; fiber: int = 0
    food_groups: tuple[str, ...] = (); tool_qualities: dict[str, int] = field(default_factory=dict)
    spoilage_hours: int = 0; utility_roles: tuple[str, ...] = (); range: int = 1
    ammo_item: str | None = None

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
        self.structures: dict[str, StructureDef] = {}; self.designs: dict[str, ComponentDesignDef] = {}
        self.species: dict[str, SpeciesDef] = {}; self.crops: dict[str, CropDef] = {}
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
            ("designs.json",self._load_designs),("species.json",self._load_species),("crops.json",self._load_crops),
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
            raw=dict(raw); raw["tags"]=_tuple(raw.get("tags")); raw["coverage"]=_tuple(raw.get("coverage")); raw["food_groups"]=_tuple(raw.get("food_groups")); raw["utility_roles"]=_tuple(raw.get("utility_roles")); raw["tool_qualities"]={str(k):int(v) for k,v in raw.get("tool_qualities",{}).items()}
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

    def _load_designs(self,path):
        for raw in self._json(path):
            obj=ComponentDesignDef(id=raw["id"],name=raw["name"],output_item=raw["output_item"],minutes=int(raw["minutes"]),station=raw.get("station"),knowledge=raw.get("knowledge"),primary_component=raw["primary_component"],components={k:{iid:dict(meta) for iid,meta in choices.items()} for k,choices in raw["components"].items()})
            if obj.id in self.designs: raise ValueError(f"Duplicate design id: {obj.id}")
            self.designs[obj.id]=obj

    def _load_species(self,path):
        for raw in self._json(path):
            obj=SpeciesDef(id=raw["id"],name=raw["name"],glyph=raw["glyph"],diet=raw["diet"],mass_kg=int(raw["mass_kg"]),max_hp=int(raw["max_hp"]),damage=int(raw["damage"]),aggression=int(raw["aggression"]),speed=int(raw["speed"]),reproduction=int(raw["reproduction"]),mortality=int(raw["mortality"]),carrying_capacity=int(raw["carrying_capacity"]),habitats=_tuple(raw.get("habitats")),drops=dict(raw.get("drops",{})),body=dict(raw.get("body",{})),description=raw.get("description",""),flavor=raw.get("flavor",""),min_temp=int(raw.get("min_temp",0)),max_temp=int(raw.get("max_temp",65535)),min_moisture=int(raw.get("min_moisture",0)),max_moisture=int(raw.get("max_moisture",65535)),group_min=int(raw.get("group_min",1)),group_max=int(raw.get("group_max",3)),attacks=tuple(dict(x) for x in raw.get("attacks",[])),carcass={str(k):int(v) for k,v in raw.get("carcass",{}).items()})
            if obj.id in self.species: raise ValueError(f"Duplicate species id: {obj.id}")
            self.species[obj.id]=obj

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
        namespaces=[self.items,self.materials,self.terrains,self.recipes,self.structures,self.designs,self.species,self.crops,self.settlement_processes,self.diseases,self.cooking_methods]
        for table in namespaces:
            for cid in table:
                if ":" not in cid: raise ValueError(f"Content id must be namespaced: {cid}")
        for item in self.items.values():
            if item.material and item.material not in self.materials: raise ValueError(f"Unknown material {item.material} for {item.id}")
            if item.mass_g<0 or item.volume_ml<0: raise ValueError(f"Negative physical property on {item.id}")
            if item.ammo_item and item.ammo_item not in self.items: raise ValueError(f"Unknown ammo item {item.ammo_item} for {item.id}")
        for terrain in self.terrains.values():
            if len(terrain.glyph)!=1 or len(terrain.ascii_glyph)!=1: raise ValueError(f"Terrain glyph must be one character: {terrain.id}")
            if terrain.gather_item and terrain.gather_item not in self.items: raise ValueError(f"Unknown gather item {terrain.gather_item} on {terrain.id}")
            if terrain.depleted_to and terrain.depleted_to not in self.terrains: raise ValueError(f"Unknown depleted terrain {terrain.depleted_to} on {terrain.id}")
        for feature in self.resources.values():
            for iid in feature.yields:
                if iid not in self.items: raise ValueError(f"Unknown resource yield {iid} in {feature.id}")
        for recipe in self.recipes.values():
            for iid in (*recipe.inputs.keys(),*recipe.outputs.keys(),*recipe.catalysts.keys()):
                if iid not in self.items: raise ValueError(f"Unknown recipe item {iid} in {recipe.id}")
            if recipe.station and recipe.station not in self.structures: raise ValueError(f"Unknown station {recipe.station} in {recipe.id}")
        for struct in self.structures.values():
            for iid in struct.cost:
                if iid not in self.items: raise ValueError(f"Unknown construction item {iid} in {struct.id}")
        for crop in self.crops.values():
            if crop.seed_item not in self.items or crop.harvest_item not in self.items: raise ValueError(f"Unknown crop item in {crop.id}")
        for sp in self.species.values():
            for iid in sp.carcass:
                if iid not in self.items: raise ValueError(f"Unknown carcass yield {iid} in {sp.id}")
            for attack in sp.attacks:
                if int(attack.get("damage",sp.damage))<0: raise ValueError(f"Invalid attack damage in {sp.id}")
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
