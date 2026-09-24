from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class MoveCommand: actor:int; dx:int; dy:int
@dataclass(frozen=True,slots=True)
class VerticalMoveCommand: actor:int; dz:int
@dataclass(frozen=True,slots=True)
class GatherCommand: actor:int; dx:int=0; dy:int=0
@dataclass(frozen=True,slots=True)
class FishingCommand: actor:int; dx:int=0; dy:int=0; method:str="hand"; bait_id:str=""

@dataclass(frozen=True,slots=True)
class ExcavateShaftCommand: actor:int
@dataclass(frozen=True,slots=True)
class WaitCommand: actor:int; minutes:int=10
@dataclass(frozen=True,slots=True)
class CraftCommand: actor:int; recipe_id:str
@dataclass(frozen=True,slots=True)
class DiscoveryPotCommand: actor:int; items:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ComponentCraftCommand: actor:int; design_id:str; choices:dict[str,str]
@dataclass(frozen=True,slots=True)
class ExperimentRecipeCommand: actor:int; recipe_id:str
@dataclass(frozen=True,slots=True)
class BuildCommand: actor:int; structure_id:str; dx:int=0; dy:int=0
@dataclass(frozen=True,slots=True)
class DismantleCommand: actor:int; dx:int=0; dy:int=0
@dataclass(frozen=True,slots=True)
class PickupCommand: actor:int; dx:int=0; dy:int=0
@dataclass(frozen=True,slots=True)
class DropCommand: actor:int; item_id:str; amount:int=1
@dataclass(frozen=True,slots=True)
class EatCommand: actor:int; item_id:str

@dataclass(frozen=True,slots=True)
class DrinkCommand: actor:int
@dataclass(frozen=True,slots=True)
class CookMealCommand: actor:int; method_id:str; ingredients:tuple[str,...]
@dataclass(frozen=True,slots=True)
class EatMealCommand: actor:int; meal_uid:str
@dataclass(frozen=True,slots=True)
class ProcessCarcassCommand: actor:int; carcass_uid:str; action:str
@dataclass(frozen=True,slots=True)
class StartProcessingCommand: actor:int; process_id:str
@dataclass(frozen=True,slots=True)
class RestCommand: actor:int; minutes:int=120
@dataclass(frozen=True,slots=True)
class RangedAttackCommand: actor:int; target_uid:str
@dataclass(frozen=True,slots=True)
class ReadyWeaponCommand: actor:int; item_id:str
@dataclass(frozen=True,slots=True)
class ClearReadyWeaponCommand: actor:int
@dataclass(frozen=True,slots=True)
class AimCommand: actor:int; target_uid:str; zone:str="center"
@dataclass(frozen=True,slots=True)
class GuardCommand: actor:int
@dataclass(frozen=True,slots=True)
class DodgeCommand: actor:int
@dataclass(frozen=True,slots=True)
class ParryCommand: actor:int
@dataclass(frozen=True,slots=True)
class BraceCommand: actor:int
@dataclass(frozen=True,slots=True)
class ShieldBashCommand: actor:int; dx:int=0; dy:int=0
@dataclass(frozen=True,slots=True)
class DisengageCommand: actor:int; dx:int=0; dy:int=0
@dataclass(frozen=True,slots=True)
class ArenaSpawnItemCommand: actor:int; item_id:str; amount:int=1
@dataclass(frozen=True,slots=True)
class ArenaSpawnCreatureCommand: actor:int; species_id:str; dx:int=1; dy:int=0
@dataclass(frozen=True,slots=True)
class ArenaSetStatCommand: actor:int; stat_type:str; key:str; value:int
@dataclass(frozen=True,slots=True)
class ArenaInjuryCommand: actor:int; preset:str
@dataclass(frozen=True,slots=True)
class ArenaPresetCommand: actor:int; preset:str
@dataclass(frozen=True,slots=True)
class ArenaClearCommand: actor:int; heal:bool=True
@dataclass(frozen=True,slots=True)
class ArenaIncomingHitCommand: actor:int; attack_kind:str="melee"; damage_type:str="blunt"; damage:int=10; source_dx:int=1; source_dy:int=0; part:str="torso"; defense_mode:str=""

@dataclass(frozen=True,slots=True)
class PlantCommand: actor:int; crop_id:str
@dataclass(frozen=True,slots=True)
class HarvestCommand: actor:int
@dataclass(frozen=True,slots=True)
class AttackCommand: actor:int; dx:int=0; dy:int=0; mode:str="standard"
@dataclass(frozen=True,slots=True)
class ExperimentMagicCommand: actor:int; source:str; form:str
@dataclass(frozen=True,slots=True)
class CastMagicCommand: actor:int; law_uid:str
@dataclass(frozen=True,slots=True)
class RitualCommand: actor:int; ritual_uid:str
@dataclass(frozen=True,slots=True)
class BuyCommand: actor:int; settlement_id:str; item_id:str; amount:int=1
@dataclass(frozen=True,slots=True)
class SellCommand: actor:int; settlement_id:str; item_id:str; amount:int=1
@dataclass(frozen=True,slots=True)
class ReadBookCommand: actor:int

@dataclass(frozen=True,slots=True)
class EquipCommand: actor:int; item_id:str
@dataclass(frozen=True,slots=True)
class UnequipCommand: actor:int; slot:str
@dataclass(frozen=True,slots=True)
class TreatWoundCommand: actor:int; wound_index:int; item_id:str
@dataclass(frozen=True,slots=True)
class StoreCommand: actor:int; item_id:str; amount:int=1; container_uid:str=""
@dataclass(frozen=True,slots=True)
class TakeFromContainerCommand: actor:int; item_id:str; amount:int=1; container_uid:str=""
@dataclass(frozen=True,slots=True)
class MoveContainerCommand: actor:int; container_uid:str; dx:int; dy:int
@dataclass(frozen=True,slots=True)
class DestroyContainerCommand: actor:int; container_uid:str
@dataclass(frozen=True,slots=True)
class FertilizeCommand: actor:int

@dataclass(frozen=True,slots=True)
class TalkCommand: actor:int; dx:int=0; dy:int=0

@dataclass(frozen=True,slots=True)
class TreatDiseaseCommand: actor:int
