from __future__ import annotations
from dataclasses import asdict, dataclass, field
from worldseed.config import MINUTES_PER_ACTION, MOVE_MINUTES
from worldseed.content.registry import ContentRegistry
from worldseed.core.clock import GameClock
from worldseed.core.coords import WorldPos
from worldseed.core.events import GameEvent, GatheredEvent, MovedEvent
from worldseed.core.rng import hash_u64
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.sim.commands import *
from worldseed.systems.state import LivingWorldState, GroundPile, CropPlot, SoilState, pos_key
from worldseed.systems.history import HistorySystem
from worldseed.systems.ecology import EcologySystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.environment import EnvironmentSystem
from worldseed.systems.ai import NPCSystem
from worldseed.systems.factions import FactionSystem
from worldseed.systems.magic import MagicSystem
from worldseed.systems.combat import CombatSystem
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.building import BuildingSystem
from worldseed.systems.generation import ProceduralSocietyGenerator, MagicGenerator
from worldseed.systems.lod import LODSystem
from worldseed.systems.speciesgen import install_procedural_species
from worldseed.systems.knowledge import KnowledgeSystem
from worldseed.systems.law import LawSystem
from worldseed.systems.family import FamilySystem
from worldseed.systems.macrohistory import MacroHistorySystem
from worldseed.systems.artifacts import ArtifactSystem
from worldseed.systems.disasters import DisasterSystem
from worldseed.systems.settlements import SettlementLifecycleSystem
from worldseed.systems.legends import LegendSystem
from worldseed.systems.metallurgy import MetallurgySystem
from worldseed.systems.dungeons import DungeonSystem
from worldseed.systems.civics import CivicsSystem
from worldseed.systems.migration import MigrationSystem
from worldseed.systems.governance import GovernanceSystem
from worldseed.systems.institutions import InstitutionSystem
from worldseed.systems.disease import EpidemiologySystem
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.food import NutritionSystem, CookingSystem
from worldseed.systems.processing import ProcessingSystem
from worldseed.systems.fishing import FishingSystem
from worldseed.world.world import World
from worldseed.world.region_blocks import RegionBlockPlanner, entry_side

@dataclass(slots=True)
class TickResult:
    events:list[object]=field(default_factory=list)

class Simulation:
    def __init__(self,world:World,entities:EntityStore,registry:ContentRegistry,turn:int=0,state:LivingWorldState|None=None,world_seed:bytes=b"",resources_system:ResourceSystem|None=None)->None:
        self.world=world
        self.entities=entities
        self.registry=registry
        self.turn=turn
        self.log:list[GameEvent]=[]
        self.state=state or LivingWorldState()
        self.seed=world_seed or world.generator.world_seed
        # Runtime discovery index. Persisted state remains an ordered list for
        # stable saves, but membership checks and per-step updates use a set.
        self._discovered_tile_set=set(self.state.discovered_tiles)
        self._visible_tile_set=set()
        self._discovered_surface_chunks=set()
        self._discovered_surface_cells_by_chunk={}
        for token in self._discovered_tile_set:
            try:
                x,y,z=(int(v) for v in token.split(','))
            except (TypeError,ValueError,AttributeError):
                continue
            if z==0:
                ck=(x//32,y//32);self._discovered_surface_chunks.add(ck)
                self._discovered_surface_cells_by_chunk.setdefault(ck,set()).add((y%32)*32+(x%32))
        install_procedural_species(self.registry,self.seed)

        self.clock=GameClock(self.state.clock_minute)
        self.history=HistorySystem(self.state)
        self.lod=LODSystem(self.state)
        self.artifacts=ArtifactSystem(self.state,registry,self.seed)
        self.metallurgy=MetallurgySystem(self.state,registry,self.seed)
        self.dungeons=DungeonSystem(self.state,registry,self.seed,self.world,self.history)
        self.building=BuildingSystem(self.state,registry)
        self.crafting=CraftingSystem(self.state,registry,self.artifacts,self.metallurgy)
        # Discovery is simulation state, never a renderer side effect. Material
        # types already carried on load are reconciled here once.
        try:self.crafting.sync_discoveries(self.entities.get(self.player_id,Inventory))
        except Exception:pass
        self.resources=resources_system or ResourceSystem(self.state,registry,self.seed,self.world)
        self.fishing=FishingSystem(self.state,registry,self.seed,self.world)
        self.building.attach_resources(self.resources,self.seed)
        self.nutrition=NutritionSystem(self.state,registry)
        self.food=CookingSystem(self.state,registry,self.nutrition)
        self.processing=ProcessingSystem(self.state,registry,self.building)
        self.ecology=EcologySystem(self.state,registry,self.seed,self.world)
        self.economy=EconomySystem(self.state,registry,self.seed,self.history)
        self.environment=EnvironmentSystem(self.state,registry,self.seed,self.history,self.world)
        self.hunting=HuntingSystem(self.state,registry,self.seed,self.world,self.environment,self.resources,self.building)
        self.disease=EpidemiologySystem(self.state,registry,self.seed,self.history)
        self.npcs=NPCSystem(self.state,self.seed,self.history,self.world,self.building,self.lod)
        self.factions=FactionSystem(self.state,self.seed,self.history)
        self.civics=CivicsSystem(self.state,self.seed,self.history)
        self.migration=MigrationSystem(self.state,self.seed,self.history)
        self.governance=GovernanceSystem(self.state,self.seed,self.history)
        self.institutions=InstitutionSystem(self.state,self.seed,self.history)
        self.knowledge=KnowledgeSystem(self.state,self.seed,self.history)
        self.law=LawSystem(self.state,self.seed,self.history)
        self.family=FamilySystem(self.state,self.seed,self.history)
        self.macrohistory=MacroHistorySystem(self.state,self.seed)
        self.magic=MagicSystem(self.state,self.seed,self.history,self.environment)
        self.combat=CombatSystem(self.state,registry,self.seed,self.artifacts)
        self.disasters=DisasterSystem(self.state,self.seed,self.history)
        self.settlement_lifecycle=SettlementLifecycleSystem(self.state,self.seed,self.history)
        self.legends=LegendSystem(self.state,self.seed,self.history)
        self.region_planner=RegionBlockPlanner(world)
        self.society_gen=ProceduralSocietyGenerator(self.seed,registry,self.region_planner)
        # Runtime locality caches. Expensive region/ecology realization is tied
        # to crossing the corresponding spatial boundary, not to every one-cell
        # movement command. These are reconstruction-only and never persisted.
        self._nearby_region_key=None
        self._nearby_ecology_key=None
        self._nearby_dungeon_key=None
        if not self.state.magic_laws:
            self.state.magic_laws=MagicGenerator(self.seed).laws()
        start=self.player_pos if any(True for _ in entities.query(Position)) else WorldPos(0,0,0)
        self._ensure_nearby_world(start,force=True)
        self.magic.ensure_traditions()
        self.magic.ensure_rituals()
        # Reconstruct current visibility immediately on load. Persistent map
        # memory already exists, but current LOS depends on present weather/time.
        self._discover(start)

    @property
    def discovered_tiles_set(self)->set[str]:
        return self._discovered_tile_set

    @property
    def visible_tiles_set(self)->set[str]:
        return self._visible_tile_set

    @property
    def discovered_surface_chunks(self)->set[tuple[int,int]]:
        return self._discovered_surface_chunks

    @property
    def discovered_surface_cells_by_chunk(self)->dict[tuple[int,int],set[int]]:
        return self._discovered_surface_cells_by_chunk

    def is_discovered(self,pos:WorldPos)->bool:
        return pos_key(pos.x,pos.y,pos.z) in self._discovered_tile_set

    def _record_discovered_tiles(self,keys:set[str])->None:
        new=keys-self._discovered_tile_set
        if not new:return
        self._discovered_tile_set.update(new)
        for token in new:
            try:
                x,y,z=(int(v) for v in token.split(','))
            except (TypeError,ValueError,AttributeError):
                continue
            if z==0:
                ck=(x//32,y//32);self._discovered_surface_chunks.add(ck)
                self._discovered_surface_cells_by_chunk.setdefault(ck,set()).add((y%32)*32+(x%32))
        # Append deterministically; avoid sorting the entire potentially 120k
        # entry exploration history on every movement step.
        self.state.discovered_tiles.extend(sorted(new))
        if len(self.state.discovered_tiles)>120000:
            self.state.discovered_tiles=self.state.discovered_tiles[-120000:]
            self._discovered_tile_set=set(self.state.discovered_tiles)
            self._discovered_surface_chunks=set()
            self._discovered_surface_cells_by_chunk={}
            for token in self._discovered_tile_set:
                try:
                    x,y,z=(int(v) for v in token.split(','))
                except (TypeError,ValueError,AttributeError):
                    continue
                if z==0:
                    ck=(x//32,y//32);self._discovered_surface_chunks.add(ck)
                    self._discovered_surface_cells_by_chunk.setdefault(ck,set()).add((y%32)*32+(x%32))

    @property
    def player_id(self)->int:
        ids=list(self.entities.query(Position,Inventory,Vitals));return ids[0] if ids else list(self.entities.query(Position,Inventory))[0]
    @property
    def player_pos(self)->WorldPos:return self.entities.get(self.player_id,Position).value

    def player_attribute(self,key:str,default:int=5)->int:
        return int(self.state.player_attributes.get(key,default))

    def player_skill(self,key:str)->int:
        return int(self.state.player_skills.get(key,0))

    def has_talent(self,key:str)->bool:
        return key in self.state.player_talents

    def execute(self,command:object)->TickResult:
        result=TickResult();minutes=MINUTES_PER_ACTION
        if isinstance(command,MoveCommand):
            self._move(command,result);minutes=MOVE_MINUTES
        elif isinstance(command,VerticalMoveCommand):self._vertical(command,result)
        elif isinstance(command,GatherCommand):minutes=self._gather(command,result)
        elif isinstance(command,FishingCommand):minutes=self._fish(command,result)
        elif isinstance(command,ExcavateShaftCommand):minutes=self._excavate_shaft(command)
        elif isinstance(command,WaitCommand):minutes=max(MINUTES_PER_ACTION,command.minutes);self._message(f"You wait {minutes} minutes.")
        elif isinstance(command,CraftCommand):minutes=self._craft(command)
        elif isinstance(command,ComponentCraftCommand):minutes=self._component_craft(command)
        elif isinstance(command,ExperimentRecipeCommand):minutes=self._experiment_recipe(command)
        elif isinstance(command,DiscoveryPotCommand):minutes=self._discovery_pot(command)
        elif isinstance(command,BuildCommand):self._build(command)
        elif isinstance(command,DismantleCommand):self._dismantle(command)
        elif isinstance(command,PickupCommand):self._pickup(command)
        elif isinstance(command,DropCommand):self._drop(command)
        elif isinstance(command,EatCommand):self._eat(command)
        elif isinstance(command,EatMealCommand):self._eat_meal(command)
        elif isinstance(command,DrinkCommand):self._drink(command)
        elif isinstance(command,CookMealCommand):minutes=self._cook(command)
        elif isinstance(command,ProcessCarcassCommand):minutes=self._process_carcass(command)
        elif isinstance(command,StartProcessingCommand):minutes=self._start_processing(command)
        elif isinstance(command,RestCommand):minutes=self._rest(command)
        elif isinstance(command,RangedAttackCommand):minutes=self._ranged_attack(command)
        elif isinstance(command,ReadyWeaponCommand):minutes=self._ready_weapon(command)
        elif isinstance(command,ClearReadyWeaponCommand):minutes=self._clear_ready_weapon(command)
        elif isinstance(command,AimCommand):minutes=self._aim(command)
        elif isinstance(command,PlantCommand):self._plant(command)
        elif isinstance(command,HarvestCommand):self._harvest(command)
        elif isinstance(command,AttackCommand):self._attack(command);minutes=1
        elif isinstance(command,ExperimentMagicCommand):self._message(self.magic.experiment(command.source,command.form,self.entities.get(command.actor,Inventory),self.entities.get(command.actor,Vitals),self.clock.minute))
        elif isinstance(command,CastMagicCommand):
            pos=self.entities.get(command.actor,Position).value;tags=set(self.world.tile_at(pos).terrain.tags)
            msg,effects=self.magic.cast(command.law_uid,self.entities.get(command.actor,Vitals),pos,self.clock.minute,self.entities.get(command.actor,Inventory),tags);self._message(msg)
            if effects.get("form")=="project":self._magic_project(effects)
            elif effects.get("form")=="reveal":self._magic_reveal(effects)
            elif effects.get("form")=="shape":self._magic_shape(effects)
        elif isinstance(command,RitualCommand):
            pos=self.player_pos;near=self._near_shrine(pos);participants=1+sum(1 for n in self.state.npcs.values() if n.alive and n.z==pos.z and abs(n.x-pos.x)+abs(n.y-pos.y)<=6 and n.occupation=='priest')
            msg,effects,duration=self.magic.perform_ritual(command.ritual_uid,self.entities.get(command.actor,Inventory),self.entities.get(command.actor,Vitals),pos,self.clock.minute,near,participants);self._message(msg)
            if effects:self._apply_ritual_effects(effects,pos)
            minutes=max(MINUTES_PER_ACTION,duration or MINUTES_PER_ACTION)
        elif isinstance(command,BuyCommand):self._buy(command)
        elif isinstance(command,SellCommand):self._sell(command)
        elif isinstance(command,ReadBookCommand):self._read_book(command)
        elif isinstance(command,EquipCommand):self._equip(command)
        elif isinstance(command,UnequipCommand):self._unequip(command)
        elif isinstance(command,TreatWoundCommand):self._message(self.combat.treat_player_wound(command.wound_index,command.item_id,self.entities.get(command.actor,Inventory)))
        elif isinstance(command,StoreCommand):self._store(command)
        elif isinstance(command,TakeFromContainerCommand):self._take_container(command)
        elif isinstance(command,MoveContainerCommand):self._move_container(command)
        elif isinstance(command,DestroyContainerCommand):self._destroy_container(command)
        elif isinstance(command,FertilizeCommand):self._fertilize(command)
        elif isinstance(command,TalkCommand):self._talk(command)
        elif isinstance(command,TreatDiseaseCommand):self._message(self.disease.treat_player(self.entities.get(command.actor,Inventory),self.clock.minute,self.player_skill('medicine'),self.has_talent('field_medic')))
        else:raise TypeError(f"Unknown command: {type(command).__name__}")
        # Inventory-changing commands can reveal material families and simple
        # recipes. This runs on the authoritative command path only.
        try:self.crafting.sync_discoveries(self.entities.get(self.player_id,Inventory))
        except Exception:pass
        self.turn+=1;self._advance_time(minutes);self._post_action();return result

    def advance_offline(self, minutes:int, policy:str="safe") -> dict[str,int]:
        """Fast-forward an absent player's world by meaningful event boundaries.

        SAFE mode advances ecology/economy/crops/logistics while suppressing
        named-character mortality and full faction battle resolution. FULL mode
        runs the complete monthly social stack. OFF performs no progression.
        """
        policy=(policy or "safe").lower()
        if policy not in {"off","safe","full"}:policy="safe"
        if policy=="off" or minutes<=0:
            self.state.last_offline_minutes=0
            self.state.last_offline_summary={"boundaries":0,"days":0,"months":0,"arrivals":0}
            return dict(self.state.last_offline_summary)
        start=self.clock.minute
        end=start+max(0,int(minutes))
        boundaries=self.lod.event_boundaries(start,end)
        summary={"boundaries":len(boundaries),"days":0,"months":0,"arrivals":0,"environment_blocks":0}
        current=start
        # Group coincident boundary kinds so a month/day at midnight is only
        # advanced once while still executing all relevant systems.
        grouped:dict[int,set[str]]={}
        for minute,kind in boundaries:grouped.setdefault(minute,set()).add(kind)
        for minute in sorted(grouped):
            kinds=grouped[minute]
            if minute>current:
                # Environmental state is deliberately coarse offline.
                if "environment" in kinds:
                    self.environment.coarse_advance(current,minute);summary["environment_blocks"]+=1
                self.clock.minute=minute;self.state.clock_minute=minute;current=minute
            # Logistics are checked at every coarse environment boundary, not
            # only against arrivals that existed before the offline jump began.
            # Daily economy/migration updates may create new traveling actors
            # mid-fast-forward; processing them every six hours keeps arrival
            # causality bounded without replaying every missed minute.
            if "environment" in kinds or "arrival" in kinds:
                before_arrivals=sum(1 for c in self.state.caravans.values() if c.status=="traveling") + sum(1 for c in self.state.migration_cohorts.values() if c.status=="traveling")
                self.disease.transport_update(minute);self.economy.process_caravans(minute);self.migration.process(minute);self.disease.transport_update(minute)
                after_arrivals=sum(1 for c in self.state.caravans.values() if c.status=="traveling") + sum(1 for c in self.state.migration_cohorts.values() if c.status=="traveling")
                summary["arrivals"]+=max(0,before_arrivals-after_arrivals)
            if "daily" in kinds:
                self.ecology.daily_update();self.environment.daily_update(minute);self.disease.daily_update(minute,allow_named_mortality=(policy=="full"));self.resources.cleanup_regrown(minute)
                for settlement in self.state.settlements.values():self.institutions.ensure_settlement(settlement.uid)
                self.magic.ensure_traditions();self.magic.ensure_rituals();self.knowledge.bootstrap()
                self.economy.daily_update(minute);self.knowledge.daily_update(minute);self.law.daily_update(minute);self.nutrition.daily_update(minute)
                summary["days"]+=1
            if "monthly" in kinds:
                self.economy.monthly_update(minute);self.disasters.monthly_update(minute);self.civics.monthly_update(minute);self.institutions.monthly_update(minute);self.economy.update_prices();self.governance.monthly_update(minute);self.migration.monthly_update(minute);self.settlement_lifecycle.monthly_update(minute)
                if policy=="full":
                    self.factions.monthly_update(minute);self.family.monthly_update(minute)
                else:
                    # SAFE still advances diplomatic exhaustion/economic pressure
                    # through faction data, but does not resolve named casualties.
                    for faction in self.state.factions.values():
                        if faction.at_war:faction.war_exhaustion=min(100,faction.war_exhaustion+1)
                summary["months"]+=1
        if current<end:
            self.environment.coarse_advance(current,end)
            self.clock.minute=end;self.state.clock_minute=end
        self.disease.transport_update(end);self.economy.process_caravans(end);self.migration.process(end);self.disease.transport_update(end)
        self.state.offline_policy=policy
        self.state.last_offline_minutes=minutes
        self.state.last_offline_summary=dict(summary)
        # Player vitals intentionally do not advance while absent in SAFE mode.
        if policy=="full":self._update_vitals(minutes)
        return summary

    def _advance_time(self,minutes:int)->None:
        old=self.clock.minute;self.clock.advance(minutes);self.state.clock_minute=self.clock.minute
        old_hour=old//60;new_hour=self.clock.minute//60
        player=self.player_pos
        for hour in range(old_hour+1,new_hour+1):
            minute=hour*60;self.environment.hourly_update(minute);collapsed=self.building.hourly_update();self.npcs.hourly_update(minute,player);self.disease.transport_update(minute);self.economy.process_caravans(minute);self.migration.process(minute);self.disease.transport_update(minute);self.magic.hourly_update(minute);self.metallurgy.cool_hourly(minute,1);[self._message(m) for m in self.processing.complete_due(minute)]
            pf=self.world.generator.sample_fields(player);pw=self.environment.weather.at(minute,player.x,player.y);ambient=-25+(pf.temperature*65)//65535+int(pw.get("temp_delta",0));arc=self.state.arcane_contamination.get(pos_key(player.x,player.y,player.z));self.artifacts.tick_environment("player",ambient,arc.intensity if arc else 0)
            if collapsed:
                v=self.entities.try_get(self.player_id,Vitals)
                for cp in collapsed:
                    if cp==self.player_pos and v:v.hp=max(0,v.hp-12);v.pain=min(100,v.pain+20);self._message("An unsupported roof collapses onto you!")
                    elif abs(cp.x-player.x)+abs(cp.y-player.y)<=8 and cp.z==player.z:self._message("You hear a roof collapse nearby.")
        old_day=old//1440;new_day=self.clock.minute//1440
        for day in range(old_day+1,new_day+1):
            minute=day*1440;self.ecology.daily_update();self.fishing.daily_update();self.environment.daily_update(minute);self.disease.daily_update(minute);self.resources.cleanup_regrown(minute);[self.institutions.ensure_settlement(s.uid) for s in self.state.settlements.values()];self.magic.ensure_traditions();self.magic.ensure_rituals();self.knowledge.bootstrap();self.economy.daily_update(minute);self.knowledge.daily_update(minute);self.law.daily_update(minute);self.nutrition.daily_update(minute)
            if day%30==0:self.economy.monthly_update(minute);self.disasters.monthly_update(minute);self.civics.monthly_update(minute);self.institutions.monthly_update(minute);self.economy.update_prices();self.governance.monthly_update(minute);self.factions.monthly_update(minute);self.family.monthly_update(minute);self.migration.monthly_update(minute);self.settlement_lifecycle.monthly_update(minute)
        self._update_vitals(minutes)

    def _update_vitals(self,minutes:int)->None:
        v=self.entities.try_get(self.player_id,Vitals)
        if not v:return
        v.hunger=min(100,v.hunger+max(0,minutes//45));v.thirst=min(100,v.thirst+max(0,minutes//30));stam=max(1,minutes//10);stam += max(0,minutes//20) if self.state.player_food_effects.get("stamina",0)>self.clock.minute else 0;
        from worldseed.systems.swimming import exposure
        if exposure(self,self.player_pos).mode=='swimming':
            effort=max(1,(minutes+4)//5)*max(1,3-self.player_attribute('endurance')//6)
            deficit=max(0,effort-v.stamina);v.stamina=max(0,v.stamina-effort)
            if deficit:
                v.hp=max(0,v.hp-deficit*2)
                self._message('You are drowning from exhaustion! Move to shallows, shore or a bridge!')
        else:v.stamina=min(100,v.stamina+stam)
        hours=max(0,minutes//60)
        if hours:
            # Natural recovery is deliberately slow and depends on wound care.
            kept=[]
            for w in self.state.player_wounds:
                sev=max(0,int(w.get("severity",0)));w["age_hours"]=int(w.get("age_hours",0))+hours
                heal=hours*(2 if w.get("bandaged") else 1)
                if self.state.player_food_effects.get("recovery",0)>self.clock.minute:heal+=hours
                if w.get("fracture"):
                    if w.get("splinted") and int(w.get("age_hours",0))>=72:w["fracture"]=False;heal+=hours
                    elif not w.get("splinted"):heal=max(0,heal//3)
                w["severity"]=max(0,sev-heal)
                if int(w.get("severity",0))>0 or w.get("fracture") or int(w.get("bleeding",0))>0:kept.append(w)
            self.state.player_wounds=kept
            for part,hp in list(self.state.player_body_parts.items()):self.state.player_body_parts[part]=min(100,hp+hours)
            # Exposure uses the same deterministic climate field as world generation.
            pos=self.player_pos;fields=self.world.generator.sample_fields(pos);weather=self.environment.weather.at(self.clock.minute,pos.x,pos.y)
            ambient=-25+(fields.temperature*65)//65535+int(weather.get("temp_delta",0))
            insulation=sum(self.registry.items[iid].insulation for iid in self.state.player_equipment.values() if iid in self.registry.items)
            room=self.building.room_at(pos);env=self.building.environmental_bonuses(pos)
            shelter_bonus=(8 if room.get("sheltered") else 0)+int(env.get("shelter",0))//6
            warmth_bonus=int(env.get("warmth",0))//4
            resilience=min(6,self.player_attribute('endurance')//2+self.player_skill('survival')//3)
            if self.state.player_food_effects.get('cold_resist',0)>self.clock.minute:resilience+=3
            if ambient<5:
                cold=max(0,5-ambient-insulation-shelter_bonus-warmth_bonus-resilience);v.body_temp=max(0,v.body_temp-max(1,cold//8)*hours)
            elif ambient>32:
                heat=max(0,ambient-32-resilience);v.body_temp=min(100,v.body_temp+max(1,heat//7)*hours)
            else:
                if v.body_temp<50:v.body_temp=min(50,v.body_temp+hours)
                elif v.body_temp>50:v.body_temp=max(50,v.body_temp-hours)
        if v.hunger>=95:v.hp=max(0,v.hp-1)
        if v.thirst>=95:v.hp=max(0,v.hp-2)
        if v.blood<50:v.hp=max(0,v.hp-1)
        if v.body_temp<20 or v.body_temp>85:v.hp=max(0,v.hp-1)

    def _ensure_nearby_world(self,pos:WorldPos,force:bool=False)->None:
        """Realize coarse systems only when their spatial cell changes.

        RC9 called settlement generation, institution setup, economy repricing
        and ecology materialization after *every* movement step.  Those systems
        are spatially coarse, so rerunning them at 20-30 Hz was pure latency.
        """
        rx,ry=pos.x//512,pos.y//512
        region_key=(rx,ry)
        if force or region_key!=self._nearby_region_key:
            realized=set(self.state.realized_regions)
            for ax in range(rx-1,rx+2):
                for ay in range(ry-1,ry+2):realized.add(f"{ax},{ay}")
            self.state.realized_regions=sorted(realized)
            for ax in range(rx-1,rx+2):
                for ay in range(ry-1,ry+2):
                    # Persist the cheap strategic block before society is
                    # materialized. This gives terrain/roads/site selection one
                    # stable regional authority without spawning local content.
                    self.region_planner.plan(ax,ay,persist=True)
                    key=f"settlement:{ax}:{ay}"
                    if key not in self.state.settlements:
                        generated=self.society_gen.settlement_for_cell(ax,ay)
                        if generated:
                            s,npcs,c,r,f=generated;self.state.cultures.setdefault(c.uid,c);self.state.religions.setdefault(r.uid,r);self.state.factions.setdefault(f.uid,f);self.state.settlements[s.uid]=s
                            for npc in npcs:self.state.npcs[npc.uid]=npc
                            self.macrohistory.ensure_region(ax,ay,s.name,c.name)
                    elif key in self.state.settlements:
                        s=self.state.settlements[key]
                        if not any(n.alive and n.settlement_id==s.uid for n in self.state.npcs.values()):
                            for npc in self.society_gen.representatives_for_settlement(s):self.state.npcs[npc.uid]=npc
            for settlement in self.state.settlements.values():
                if abs(settlement.region_x-rx)<=1 and abs(settlement.region_y-ry)<=1:
                    self.civics.ensure_settlement(settlement.uid)
                    self.institutions.ensure_settlement(settlement.uid)
            self.magic.ensure_traditions();self.magic.ensure_rituals();self.economy.update_prices()
            self._nearby_region_key=region_key

        eco_key=(pos.x//256,pos.y//256,0 if pos.z>=0 else pos.z)
        if force or eco_key!=self._nearby_ecology_key:
            self.ecology.materialize_near(pos,0)
            self.ecology.dematerialize_far(pos)
            self._nearby_ecology_key=eco_key

        if pos.z<0:
            dungeon_key=(pos.x//32,pos.y//32,pos.z)
            if force or dungeon_key!=self._nearby_dungeon_key:
                self.dungeons.activate_at(pos,self.clock.minute)
                self._nearby_dungeon_key=dungeon_key
        else:
            self._nearby_dungeon_key=None

    def _post_action(self)->None:
        inv=self.entities.try_get(self.player_id,Inventory)
        if inv and self.state.player_readied_weapon and inv.count(self.state.player_readied_weapon)<=0:
            self.state.player_readied_weapon="";self.combat.clear_aim()
        self._ensure_nearby_world(self.player_pos)
        if self.turn % 32 == 0:self.ecology.dematerialize_far(self.player_pos)
        self.dungeons.update_cleared(self.clock.minute)
        self.combat.tick_wounds()
        v=self.entities.try_get(self.player_id,Vitals)
        if v:
            self.combat.tick_player_wounds(v)
            for did in self.disease.local_player_exposure(self.player_pos,self.clock.minute):
                ddef=self.registry.diseases.get(did);self._message(f"You may have been exposed to {ddef.name if ddef else did}.")
            for msg in self.disease.tick_player(self.clock.minute,v):self._message(msg)
        attackers=self.hunting.update_local_ai(self.player_pos,self.turn,self.clock.minute)
        v=self.entities.try_get(self.player_id,Vitals)
        if v:
            for uid in attackers:
                c=self.state.creatures.get(uid)
                if c:self._message(self.combat.creature_attack_player(c,v,self.turn))
            if v.hp<=0:
                killer=self.state.creatures.get(attackers[-1]) if attackers else None
                if killer:
                    self.legends.credit_kill(killer,self.clock.minute,"the player");self._handle_death(f"killed by {killer.name or self.registry.species[killer.species_id].name}")
                else:self._handle_death("died from wounds and exposure")
        self._discover(self.player_pos)

    def known_settlement_ids(self)->set[str]:return set(self.state.discovered_settlements)
    def visited_settlement_ids(self)->set[str]:return set(self.state.visited_settlements)
    def known_npc_ids(self)->set[str]:return set(self.state.discovered_npcs)
    def known_faction_ids(self)->set[str]:return set(self.state.discovered_factions)
    def known_site_ids(self)->set[str]:return set(self.state.discovered_sites)
    def known_species_ids(self)->set[str]:return set(self.state.discovered_species)
    def known_event_ids(self)->set[str]:return set(self.state.discovered_events)
    def known_creature_ids(self)->set[str]:
        """Named/notable creatures the character has actually learned about.

        Creature materialization is simulation state, not player knowledge.  An
        individual becomes name-known only when a learned historical event
        references it.  Merely existing in an active chunk must never leak its
        generated legend name into the UI.
        """
        learned=self.known_event_ids();out=set()
        for event in self.state.history:
            if event.uid in learned:
                out.update(uid for uid in event.subjects if uid in self.state.creatures)
        return out
    def known_settlements(self):return [s for uid,s in self.state.settlements.items() if uid in self.known_settlement_ids()]
    def known_npcs(self):return [n for uid,n in self.state.npcs.items() if uid in self.known_npc_ids()]
    def known_factions(self):return [f for uid,f in self.state.factions.items() if uid in self.known_faction_ids()]

    @staticmethod
    def _bresenham(a:WorldPos,b:WorldPos):
        x0,y0=a.x,a.y;x1,y1=b.x,b.y;dx=abs(x1-x0);dy=-abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1;err=dx+dy
        while True:
            yield WorldPos(x0,y0,a.z)
            if x0==x1 and y0==y1:break
            e2=2*err
            if e2>=dy:err+=dy;x0+=sx
            if e2<=dx:err+=dx;y0+=sy

    def _visible_from(self,origin:WorldPos,target:WorldPos,opaque_cache:dict[tuple[int,int,int],bool]|None=None)->bool:
        if origin.z!=target.z:return False
        line=list(self._bresenham(origin,target))
        for cell in line[1:-1]:
            key=(cell.x,cell.y,cell.z)
            blocked=None if opaque_cache is None else opaque_cache.get(key)
            if blocked is None:
                tile=self.world.tile_at(cell)
                blocked=bool(tile.terrain.blocks_sight or self.resources.blocks_sight(cell) or self.building.blocks_sight(cell))
                if opaque_cache is not None:opaque_cache[key]=blocked
            if blocked:return False
        return True

    def visibility_radius(self,pos:WorldPos)->int:
        """Current circular sight radius from ability, weather and available light."""
        perception=self.player_attribute('perception')
        survival=self.player_skill('survival')
        keen=2 if self.has_talent('keen_senses') else 0
        base=6+perception//2+survival//4+keen
        if pos.z!=0:
            return max(3,min(9,base-3))
        weather,lighting=self.environment.visual_conditions(self.clock.minute,pos)
        visibility=max(3,min(8,int(weather.get('visibility',8))))
        # Weather visibility scales range before illumination. Clear daylight is
        # close to full range; fog/storm and darkness contract it naturally.
        radius=base*visibility//8
        ambient=int(getattr(lighting,'ambient_light',65535))
        if ambient<11000:radius=radius*48//100
        elif ambient<22000:radius=radius*62//100
        elif ambient<36000:radius=radius*78//100
        elif ambient<50000:radius=radius*90//100
        if int(weather.get('fog',0))>=55:radius-=1
        return max(3,min(16,radius))

    def _discover(self,pos:WorldPos)->None:
        # Discovery is a real circular sight radius, not a rectangular reveal.
        # Conditions shrink/grow the circle before line-of-sight obstruction.
        radius=self.visibility_radius(pos)
        radius2=radius*radius
        newly=set();visible=set();opaque_cache={}
        for y in range(pos.y-radius,pos.y+radius+1):
            dy=y-pos.y
            for x in range(pos.x-radius,pos.x+radius+1):
                dx=x-pos.x
                if dx*dx+dy*dy>radius2:continue
                key=pos_key(x,y,pos.z);target=WorldPos(x,y,pos.z)
                if self._visible_from(pos,target,opaque_cache):
                    visible.add(key)
                    if key not in self._discovered_tile_set:newly.add(key)
        visible.add(pos_key(pos.x,pos.y,pos.z))
        self._visible_tile_set=visible
        self._record_discovered_tiles(newly)
        if newly and pos.z==0:
            positions=[]
            for token in newly:
                try:
                    x,y,z=(int(v) for v in token.split(','))
                except Exception:
                    continue
                positions.append(WorldPos(x,y,z))
            self.building.materialize_natural_containers(positions)
        settlements=set(self.state.discovered_settlements);factions=set(self.state.discovered_factions)
        npcs=set(self.state.discovered_npcs);sites=set(self.state.discovered_sites);species=set(self.state.discovered_species)
        if pos.z==0:
            for s in self.state.settlements.values():
                dist=abs(s.x-pos.x)+abs(s.y-pos.y)
                if dist<=10 and self._visible_from(pos,WorldPos(s.x,s.y,0),opaque_cache):
                    if s.uid not in settlements:self._message(f"You discover {s.name}.")
                    settlements.add(s.uid);factions.add(s.faction_id)
                    visited=set(self.state.visited_settlements);visited.add(s.uid);self.state.visited_settlements=sorted(visited)
        # An adjacent person remains a Stranger until you actually speak;
        # proximity alone is not knowledge of identity.
        for c in self.state.creatures.values():
            target=WorldPos(c.x,c.y,c.z)
            if c.hp>0 and c.z==pos.z and abs(c.x-pos.x)+abs(c.y-pos.y)<=10 and self._visible_from(pos,target,opaque_cache):species.add(c.species_id)
        for site in self.state.dungeon_sites.values():
            sx=site.chunk_x*32+16;sy=site.chunk_y*32+16;target=WorldPos(sx,sy,site.z)
            if site.z==pos.z and abs(sx-pos.x)+abs(sy-pos.y)<=12 and self._visible_from(pos,target,opaque_cache):sites.add(site.uid)
        # Very recent high-salience events in the current macro-region can be
        # witnessed directly. Older events require testimony, books or sites.
        events=set(self.state.discovered_events);prx,pry=pos.x//512,pos.y//512
        for ev in self.state.history:
            if (ev.region_x,ev.region_y)==(prx,pry) and ev.salience>=75 and self.clock.minute-ev.minute<=1440:
                events.add(ev.uid)
        self.state.discovered_settlements=sorted(settlements);self.state.discovered_factions=sorted(factions);self.state.discovered_npcs=sorted(npcs);self.state.discovered_sites=sorted(sites);self.state.discovered_species=sorted(species);self.state.discovered_events=sorted(events)

    def _talk(self,cmd:TalkCommand)->None:
        p=self.entities.get(cmd.actor,Position).value;target=p.moved(cmd.dx,cmd.dy)
        npc=next((n for n in self.state.npcs.values() if n.alive and (n.x,n.y,n.z)==(target.x,target.y,target.z)),None)
        if not npc:self._message("There is nobody there to speak with.");return
        known=set(self.state.discovered_npcs);first=npc.uid not in known;known.add(npc.uid);self.state.discovered_npcs=sorted(known)
        if npc.settlement_id:
            ss=set(self.state.discovered_settlements);ss.add(npc.settlement_id);self.state.discovered_settlements=sorted(ss)
        if npc.faction_id:
            ff=set(self.state.discovered_factions);ff.add(npc.faction_id);self.state.discovered_factions=sorted(ff)
        rel=npc.relationships.setdefault('player',{'affection':0,'trust':0,'fear':0,'respect':0,'familiarity':0})
        rel['familiarity']=min(100,int(rel.get('familiarity',0))+8);rel['trust']=min(100,int(rel.get('trust',0))+1)
        town=self.state.settlements.get(npc.settlement_id)
        if first:
            self._message(f"You meet {npc.name}, a {npc.occupation}" + (f" from {town.name}." if town else '.'))
            return
        familiarity=int(rel.get('familiarity',0))
        # Conversations reveal a bounded piece of world knowledge rather than
        # dumping the NPC's complete database into the UI.
        relatives=[uid for uid in ([npc.spouse_uid] if npc.spouse_uid else [])+list(npc.parents)+list(npc.children) if uid and uid in self.state.npcs and uid not in self.known_npc_ids()]
        if relatives and familiarity>=16:
            uid=relatives[hash_u64(self.seed,"talk-relative",npc.uid,familiarity)//8%len(relatives)];other=self.state.npcs[uid]
            known=set(self.state.discovered_npcs);known.add(uid);self.state.discovered_npcs=sorted(known)
            self._message(f"{npc.name} mentions {other.name}, someone in their family.");return
        routes=[r for r in self.state.trade_routes.values() if npc.settlement_id in (r.origin,r.destination)]
        unknown=[]
        for r in routes:
            uid=r.destination if r.origin==npc.settlement_id else r.origin
            if uid in self.state.settlements and uid not in self.known_settlement_ids():unknown.append(uid)
        if unknown and familiarity>=24:
            uid=unknown[hash_u64(self.seed,"talk-place",npc.uid,familiarity)//8%len(unknown)];other=self.state.settlements[uid]
            ss=set(self.state.discovered_settlements);ss.add(uid);self.state.discovered_settlements=sorted(ss)
            ff=set(self.state.discovered_factions);ff.add(other.faction_id);self.state.discovered_factions=sorted(ff)
            dx=other.x-npc.x;dy=other.y-npc.y;direction=("east" if abs(dx)>=abs(dy) and dx>0 else "west" if abs(dx)>=abs(dy) else "south" if dy>0 else "north")
            rumor=f"{npc.name} told you of {other.name}, roughly {direction} of here.";self.state.player_rumors.append(rumor);self._message(rumor);return
        # Occupation-specific information is learned through people, not from
        # omniscient menus. Hunters/herders can provide a regional wildlife
        # report; merchants can identify a trade road after you have spoken.
        if npc.occupation in {'hunter','herder','farmer'} and familiarity>=12:
            town=self.state.settlements.get(npc.settlement_id)
            if town:
                cx,cy=town.x//256,town.y//256
                options=[c for c in self.state.cohorts.values() if c.region_x==cx and c.region_y==cy and c.z==0 and c.count>0]
                options.sort(key=lambda c:(-c.count,c.species_id))
                for cohort in options:
                    report_key=f'{cx},{cy}:{cohort.species_id}'
                    if report_key not in self.state.population_reports:
                        self.state.population_reports[report_key]=self.clock.minute
                        species=self.registry.species.get(cohort.species_id);name=species.name if species else 'wildlife'
                        known=set(self.state.discovered_species);known.add(cohort.species_id);self.state.discovered_species=sorted(known)
                        self._message(f'{npc.name} describes recent signs of {name.lower()} in the surrounding country.');return
        if npc.occupation=='merchant' and familiarity>=12:
            routes=[r for r in self.state.trade_routes.values() if npc.settlement_id in (r.origin,r.destination) and r.uid not in self.state.discovered_routes]
            if routes:
                route=sorted(routes,key=lambda r:(r.danger,r.distance,r.uid))[0];self.state.discovered_routes=sorted(set(self.state.discovered_routes+[route.uid]))
                other_id=route.destination if route.origin==npc.settlement_id else route.origin;other=self.state.settlements.get(other_id)
                if other:
                    ss=set(self.state.discovered_settlements);ss.add(other.uid);self.state.discovered_settlements=sorted(ss)
                    self._message(f'{npc.name} tells you that traders travel between here and {other.name}.');return
        relevant=[ev for ev in self.state.history if ev.uid not in self.known_event_ids() and (npc.uid in ev.subjects or npc.settlement_id in ev.subjects or npc.faction_id in ev.subjects)]
        if relevant and familiarity>=16:
            ev=sorted(relevant,key=lambda e:(-e.salience,-e.minute,e.uid))[0];ee=set(self.state.discovered_events);ee.add(ev.uid);self.state.discovered_events=sorted(ee)
            self._message(f"{npc.name} tells you: {ev.summary}");return
        self._message(f"You speak with {npc.name}. They are focused on {npc.goal}.")

    def _move(self,cmd:MoveCommand,result:TickResult)->None:
        pc=self.entities.get(cmd.actor,Position);old=pc.value;new=old.moved(cmd.dx,cmd.dy)
        if self.dungeons.is_locked(new):
            ok,msg=self.dungeons.try_unlock(new,self.entities.get(cmd.actor,Inventory),self.clock.minute)
            self._message(msg)
            if not ok:return
        from worldseed.systems.swimming import exposure, stroke_cost, practice
        water=exposure(self,new); old_water=exposure(self,old)
        terrain=self.world.tile_at(new).terrain
        world_pass=self.world.is_passable(new) or 'water' in terrain.tags
        if self.resources.blocks_movement(new):
            self._message(f"{self.resources.description(new)} blocks your path. Harvest it from an adjacent tile.");return
        if not self.building.passable(new,world_pass) or (not self.environment.fluid_passable(new) and water.mode!='swimming'):
            self._message('Something solid blocks your path.');return
        v=self.entities.get(cmd.actor,Vitals)
        if water.mode=='swimming':
            cost=stroke_cost(self,new,cmd.dx,cmd.dy)
            if old_water.mode!='swimming' and v.stamina < max(20,cost+4):
                self._message('Too exhausted to enter swimming depth. Recover on shore first.');return
            # Never immobilize an exhausted swimmer: every stroke toward safety
            # remains possible, but unmet exertion damages health.
            deficit=max(0,cost-v.stamina)
            v.stamina=max(0,v.stamina-cost)
            if deficit:v.hp=max(0,v.hp-deficit)
            practice(self)
        elif water.mode=='wading':v.stamina=max(0,v.stamina-2)
        pc.value=new;result.events.append(MovedEvent(cmd.actor,old,new));fluid=self.environment.fluid_at(new)
        self.combat.clear_aim()
        self.hunting.note_player_noise(new,self.hunting.movement_noise(new),self.turn,self.clock.minute,"movement")
        trap_msg=self.dungeons.trigger_trap(new,self.entities.get(cmd.actor,Vitals),self.turn)
        if trap_msg:self._message(trap_msg)
        injury_cost=self.combat.leg_injury_penalty()
        if injury_cost:
            v=self.entities.try_get(cmd.actor,Vitals)
            if v:v.stamina=max(0,v.stamina-injury_cost)
        if water.mode=='swimming':
            self._message(f'You swim: {cost} stamina per stroke. '+('EXHAUSTED! Reach shore or a bridge!' if v.stamina<20 else 'Swimming + Endurance reduce effort.'))
        elif water.mode=='wading':
            self._message('You wade through the shallows.')
        else:
            side=entry_side(old.x,old.y,new.x,new.y) if new.z==0 else None
            if side:
                rx,ry=new.x//512,new.y//512
                plan=self.region_planner.plan(rx,ry,persist=True)
                label=plan.dominant_biome.replace('_',' ')
                self._message(f"You enter a {label} region from the {side}.")
            else:
                self._message(f"You move across {self.world.tile_at(new).terrain.name.lower()}.")
    def _vertical(self,cmd:VerticalMoveCommand,result:TickResult)->None:
        pc=self.entities.get(cmd.actor,Position);here=self.world.tile_at(pc.value)
        if "shaft" not in here.terrain.tags:
            self._message("There is no traversable shaft here.");return
        new=pc.value.moved(0,0,cmd.dz)
        if cmd.dz>0 and new.z>0:
            self._message("There is nothing above the surface.");return
        dest=self.world.tile_at(new)
        # A vertical connector must be reciprocal. This prevents old/random
        # cave-mouth logic from dropping the player into a solid wall.
        if "shaft" not in dest.terrain.tags:
            if self.world.generator.version<=2:
                # Legacy worlds generated cave mouths and underground shafts
                # independently.  Stabilize a traversed connector as a sparse
                # persistent delta instead of invalidating an old save.
                self.world.set_terrain(new,"core:cave_mouth" if new.z==0 else "core:shaft")
                dest=self.world.tile_at(new)
                self._message("You clear and stabilize the old natural passage.")
            else:
                self._message("The passage does not continue safely to that level.");return
        pc.value=new
        self._message("You climb toward the surface." if cmd.dz>0 else "You descend into the earth.")

    def _fish(self,cmd:FishingCommand,result:TickResult)->int:
        origin=self.entities.get(cmd.actor,Position).value
        target=origin.moved(cmd.dx,cmd.dy)
        distance=abs(cmd.dx)+abs(cmd.dy)
        inv=self.entities.get(cmd.actor,Inventory)
        available={method for method,_ in self.fishing.available_methods(inv,target,distance)}
        if cmd.method not in available:
            if not self.fishing.is_fishable(target):
                self._message("There is no fishable water at that target.");return MINUTES_PER_ACTION
            self._message(f"You cannot use {cmd.method} fishing there with your current gear and range.");return MINUTES_PER_ACTION
        before_skill=self.player_skill('fishing')
        ok,msg,minutes,details=self.fishing.attempt(
            target,inv,cmd.method,cmd.bait_id,self.clock.minute,
            self.player_skill('fishing'),self.player_attribute('perception'),self.player_skill('survival')
        )
        self._message(msg)
        after_skill=self.player_skill('fishing')
        if after_skill>before_skill:
            self._message(f"Fishing improves to {after_skill}. You read water and tackle more efficiently.")
        if ok and details.get('fish'):
            fish=self.registry.fish.get(details['fish'])
            if fish:
                result.events.append(GatheredEvent(cmd.actor,target,fish.item_id,int(details.get('count',1))))
        return max(MINUTES_PER_ACTION,minutes)

    def _gather(self,cmd:GatherCommand,result:TickResult)->int:
        origin=self.entities.get(cmd.actor,Position).value
        pos=origin.moved(cmd.dx,cmd.dy)
        if abs(cmd.dx)+abs(cmd.dy)>1:
            self._message("You can only harvest your tile or an adjacent tile.");return MINUTES_PER_ACTION
        inv=self.entities.get(cmd.actor,Inventory)
        ok,msg,minutes,outputs=self.resources.harvest(pos,inv,self.clock.minute)
        self._message(msg)
        if ok:
            tile=self.world.tile_at(pos)
            if "water_source" in tile.terrain.tags:self.environment.add_water(pos,200)
            for iid,amount in outputs.items():result.events.append(GatheredEvent(cmd.actor,pos,iid,amount))
        return max(MINUTES_PER_ACTION,minutes)
    def _excavate_shaft(self,cmd:ExcavateShaftCommand)->int:
        pos=self.entities.get(cmd.actor,Position).value;inv=self.entities.get(cmd.actor,Inventory)
        here=self.world.tile_at(pos)
        if 'shaft' in here.terrain.tags:
            self._message('A vertical passage already occupies this tile.');return MINUTES_PER_ACTION
        if pos.z==0 and (not here.terrain.passable or 'water' in here.terrain.tags):
            self._message('You cannot safely sink a shaft here.');return MINUTES_PER_ACTION
        if self.resources.blocks_movement(pos):
            self._message('Clear the tree or boulder from this tile before sinking a shaft.');return MINUTES_PER_ACTION
        if self.resources.tool_power(inv,'pick')<1:
            self._message('You need a pick or mining tool to sink a shaft.');return MINUTES_PER_ACTION
        if inv.count('core:wood')<2:
            self._message('You need 2 wood for laddering and temporary shaft supports.');return MINUTES_PER_ACTION
        below=pos.moved(0,0,-1);dest=self.world.tile_at(below)
        inv.remove('core:wood',2)
        # The excavated material is real output; ore-bearing rock yields ore,
        # ordinary strata yield stone. Aquifers are breached into local fluid.
        if dest.terrain.gather_item and dest.terrain.gather_amount>0:
            inv.add(dest.terrain.gather_item,max(1,dest.terrain.gather_amount))
        self.world.set_terrain(pos,'core:cave_mouth' if pos.z==0 else 'core:shaft')
        self.world.set_terrain(below,'core:shaft')
        if 'water_source' in dest.terrain.tags:
            self.environment.add_water(below,220)
            self._message('You sink a supported shaft and breach water-bearing rock below. Water begins entering the excavation.')
        else:
            self._message('You sink a supported vertical shaft to the level below.')
        return 180

    def _craft(self,cmd:CraftCommand)->int:
        pos=self.entities.get(cmd.actor,Position).value;bonus=self.building.environmental_bonuses(pos).get('work_bonus',0);skill=self.player_skill(self.registry.recipes.get(cmd.recipe_id).skill if cmd.recipe_id in self.registry.recipes else 'crafting');ok,msg,minutes=self.crafting.craft(cmd.recipe_id,self.entities.get(cmd.actor,Inventory),self.building.nearby_station_ids(pos),self.clock.minute,"player",skill,bonus);self._message(msg);return max(MINUTES_PER_ACTION,minutes if ok else MINUTES_PER_ACTION)
    def _component_craft(self,cmd:ComponentCraftCommand)->int:
        pos=self.entities.get(cmd.actor,Position).value;ok,msg,minutes=self.crafting.craft_design(cmd.design_id,cmd.choices,self.entities.get(cmd.actor,Inventory),self.building.nearby_station_ids(pos),self.clock.minute,"player");self._message(msg);return max(MINUTES_PER_ACTION,minutes if ok else MINUTES_PER_ACTION)
    def _experiment_recipe(self,cmd:ExperimentRecipeCommand)->int:
        ok,msg,minutes=self.crafting.experiment(cmd.recipe_id,self.entities.get(cmd.actor,Inventory));self._message(msg);return max(MINUTES_PER_ACTION,minutes if ok else MINUTES_PER_ACTION)
    def _discovery_pot(self,cmd:DiscoveryPotCommand)->int:
        ok,msg,minutes=self.crafting.combine_in_pot(cmd.items,self.entities.get(cmd.actor,Inventory),self.seed)
        self._message(msg)
        return max(MINUTES_PER_ACTION,minutes if ok else MINUTES_PER_ACTION)
    def _build(self,cmd:BuildCommand)->None:
        pos=self.entities.get(cmd.actor,Position).value.moved(cmd.dx,cmd.dy);ok,msg=self.building.place(cmd.structure_id,pos,self.entities.get(cmd.actor,Inventory));self._message(msg)
    def _dismantle(self,cmd:DismantleCommand)->None:
        pos=self.entities.get(cmd.actor,Position).value.moved(cmd.dx,cmd.dy);ok,msg=self.building.dismantle(pos,self.entities.get(cmd.actor,Inventory));self._message(msg)
    def _command_container(self,uid:str):
        if uid:
            c=next((row for row in self.state.containers.values() if row.uid==uid),None)
            if c and c.z==self.player_pos.z and abs(c.x-self.player_pos.x)+abs(c.y-self.player_pos.y)<=1:return c
            return None
        return self.building.nearby_container(self.player_pos)
    def _store(self,cmd:StoreCommand)->None:
        c=self._command_container(cmd.container_uid)
        if not c:self._message("There is no storage container within reach.");return
        ok,msg=self.building.store(c,self.entities.get(cmd.actor,Inventory),cmd.item_id,cmd.amount);self._message(msg)
    def _take_container(self,cmd:TakeFromContainerCommand)->None:
        c=self._command_container(cmd.container_uid)
        if not c:self._message("There is no storage container within reach.");return
        ok,msg=self.building.take(c,self.entities.get(cmd.actor,Inventory),cmd.item_id,cmd.amount);self._message(msg)
    def _move_container(self,cmd:MoveContainerCommand)->None:
        c=self._command_container(cmd.container_uid)
        if not c:self._message("That container is no longer within reach.");return
        dest=WorldPos(c.x+cmd.dx,c.y+cmd.dy,c.z)
        if abs(dest.x-self.player_pos.x)+abs(dest.y-self.player_pos.y)>2:
            self._message("You need to stay close while moving the container.");return
        if not self.world.is_passable(dest) or self.resources.blocks_movement(dest):
            self._message("The destination is blocked.");return
        ok,msg=self.building.move_container(c,dest);self._message(msg)
    def _destroy_container(self,cmd:DestroyContainerCommand)->None:
        c=self._command_container(cmd.container_uid)
        if not c:self._message("That container is no longer within reach.");return
        ok,msg=self.building.destroy_container(c);self._message(msg)
    def _fertilize(self,cmd:FertilizeCommand)->None:
        pos=self.player_pos;key=pos_key(pos.x,pos.y,pos.z);soil=self.state.soils.get(key);inv=self.entities.get(cmd.actor,Inventory)
        if not soil:self._message("This tile has no cultivated soil to fertilize.");return
        if not inv.remove("core:bone_meal",1):self._message("You need bone meal.");return
        soil.nitrogen=min(100,soil.nitrogen+15);soil.phosphorus=min(100,soil.phosphorus+30);soil.potassium=min(100,soil.potassium+10);soil.organic=min(100,soil.organic+5);soil.disease_pressure=max(0,soil.disease_pressure-4);self._message("You work bone meal into the soil.")
    def _pickup(self,cmd:PickupCommand)->None:
        origin=self.entities.get(cmd.actor,Position).value
        if abs(cmd.dx)+abs(cmd.dy)>1:
            self._message("You can only pick up items from your tile or an adjacent tile.");return
        pos=origin.moved(cmd.dx,cmd.dy);key=pos_key(pos.x,pos.y,pos.z);pile=self.state.ground_piles.get(key)
        if not pile or not pile.items:
            self._message("There is nothing there to pick up." if (cmd.dx or cmd.dy) else "There is nothing here to pick up.");return
        inv=self.entities.get(cmd.actor,Inventory)
        for iid,n in pile.items.items():inv.add(iid,n)
        self.state.ground_piles.pop(key,None);self._message("You pick up everything on the ground.")
    def _drop(self,cmd:DropCommand)->None:
        inv=self.entities.get(cmd.actor,Inventory)
        if not inv.remove(cmd.item_id,cmd.amount):self._message("You do not have enough of that item.");return
        pos=self.entities.get(cmd.actor,Position).value;key=pos_key(pos.x,pos.y,pos.z);pile=self.state.ground_piles.setdefault(key,GroundPile(pos.x,pos.y,pos.z,{}));pile.items[cmd.item_id]=pile.items.get(cmd.item_id,0)+cmd.amount;self._message("You drop the item.")
    def _eat(self,cmd:EatCommand)->None:
        inv=self.entities.get(cmd.actor,Inventory);item=self.registry.items.get(cmd.item_id);v=self.entities.get(cmd.actor,Vitals)
        if not item or item.nutrition<=0 or inv.count(cmd.item_id)<=0:self._message("You cannot eat that.");return
        inv.remove(cmd.item_id,1);self._message(self.nutrition.consume_item(cmd.item_id,v,self.clock.minute))

    def _eat_meal(self,cmd:EatMealCommand)->None:
        meal=self.state.prepared_meals.get(cmd.meal_uid);v=self.entities.get(cmd.actor,Vitals)
        if not meal or meal.owner!='player' or meal.portions<=0:self._message("That prepared meal is no longer available.");return
        self._message(self.nutrition.consume_meal(meal,v,self.clock.minute));meal.portions-=1
        if meal.portions<=0:self.state.prepared_meals.pop(meal.uid,None)

    def _water_available(self,pos:WorldPos)->bool:
        for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
            q=pos.moved(dx,dy);tile=self.world.tile_at(q);fluid=self.environment.fluid_at(q)
            if 'water' in tile.terrain.tags or (fluid and fluid.fluid=='water' and fluid.amount>10):return True
        return False

    def _drink(self,cmd:DrinkCommand)->None:
        pos=self.player_pos;v=self.entities.get(cmd.actor,Vitals);inv=self.entities.get(cmd.actor,Inventory)
        if inv.count('core:clean_water')>0:
            inv.remove('core:clean_water',1);v.thirst=max(0,v.thirst-55);self._message("You drink clean water.");return
        if not self._water_available(pos):self._message("There is no accessible water within reach.");return
        v.thirst=max(0,v.thirst-45);self._message("You drink from the nearby water source.")
        # Untreated water carries a small deterministic disease risk rather than being free perfect water.
        if (self.turn*37 + pos.x*11 + pos.y*17) % 100 < 8:
            did='core:flux' if 'core:flux' in self.registry.diseases else next(iter(self.registry.diseases),None)
            if did:
                try:self.disease.expose_player(did,self.clock.minute,'untreated water')
                except Exception:pass

    def _cook(self,cmd:CookMealCommand)->int:
        pos=self.player_pos;inv=self.entities.get(cmd.actor,Inventory);stations=self.building.nearby_station_ids(pos);water=self._water_available(pos) or inv.count('core:clean_water')>0
        ok,msg,minutes,_uid=self.food.cook(cmd.method_id,list(cmd.ingredients),inv,stations,water,self.clock.minute);self._message(msg);return max(MINUTES_PER_ACTION,minutes if ok else MINUTES_PER_ACTION)

    def _process_carcass(self,cmd:ProcessCarcassCommand)->int:
        inv=self.entities.get(cmd.actor,Inventory);ok,msg,minutes=self.processing.process_carcass(cmd.carcass_uid,cmd.action,inv,self.player_skill('hunting'),self.clock.minute);self._message(msg);return max(MINUTES_PER_ACTION,minutes if ok else MINUTES_PER_ACTION)

    def _start_processing(self,cmd:StartProcessingCommand)->int:
        ok,msg,minutes=self.processing.start_job(cmd.process_id,self.player_pos,self.entities.get(cmd.actor,Inventory),self.clock.minute);self._message(msg);return max(MINUTES_PER_ACTION,minutes if ok else MINUTES_PER_ACTION)

    def _rest(self,cmd:RestCommand)->int:
        from worldseed.systems.swimming import exposure
        if exposure(self,self.player_pos).mode=='swimming':
            self._message('You cannot rest while swimming. Reach shallows, shore or a bridge.');return MINUTES_PER_ACTION
        minutes=max(30,min(720,int(cmd.minutes)));v=self.entities.get(cmd.actor,Vitals);env=self.building.environmental_bonuses(self.player_pos);comfort=int(env.get('comfort',0));v.stamina=min(100,v.stamina+minutes//5+comfort//2);v.pain=max(0,v.pain-minutes//90-max(0,comfort//10));self._message(f"You rest for {minutes} minutes"+(" in relative comfort." if comfort else "."));return minutes

    def _ranged_attack(self,cmd:RangedAttackCommand)->int:
        c=self.state.creatures.get(cmd.target_uid)
        if not c or c.hp<=0:self.combat.clear_aim();self._message("That target is no longer there.");return 1
        p=self.player_pos;dist=abs(c.x-p.x)+abs(c.y-p.y);inv=self.entities.get(cmd.actor,Inventory);v=self.entities.get(cmd.actor,Vitals)
        weapon=self.combat.readied_weapon(inv)
        if not weapon or weapon.range<=1:self.combat.clear_aim();self._message("Ready a ranged or throwable weapon first.");return 1
        if dist>weapon.range:self._message(f"The target is beyond the useful range of your {weapon.name.lower()}.");return 1
        if weapon.ammo_item and inv.count(weapon.ammo_item)<=0:self._message(f"You have no {self.registry.items[weapon.ammo_item].name.lower()}.");return 1
        if c.z!=p.z or not self._visible_from(p,WorldPos(c.x,c.y,c.z)):self.combat.clear_aim();self._message("You do not have a clear shot.");return 1
        aim_quality=self.state.player_aim_quality if self.state.player_aim_target==c.uid else 0
        aim_zone=self.state.player_aim_zone if self.state.player_aim_target==c.uid else "center"
        cost=max(1,weapon.stamina_cost);stamina_before=v.stamina;v.stamina=max(0,v.stamina-cost)
        before_wounds=len(c.wounds);target_pos=WorldPos(c.x,c.y,c.z)
        msg=self.combat.ranged_attack_creature(c,inv,self.turn,dist,self.player_attribute('perception'),self.player_skill('hunting'),weapon.id,aim_zone,aim_quality,stamina_before)
        hit=len(c.wounds)>before_wounds if c.uid in self.state.creatures else True
        projectile_id=None
        if weapon.throwable:
            if inv.remove(weapon.id,1):
                projectile_id=weapon.id
                if inv.count(weapon.id)<=0:self.state.player_readied_weapon=""
        elif weapon.ammo_item and weapon.recovery_percent>0:
            roll=hash_u64(self.seed,"projectile-recovery",self.turn,weapon.id,c.uid,target_pos.x,target_pos.y)%100
            if roll<weapon.recovery_percent:projectile_id=weapon.ammo_item
        if projectile_id:
            key=pos_key(target_pos.x,target_pos.y,target_pos.z);pile=self.state.ground_piles.get(key)
            if pile is None:pile=GroundPile(target_pos.x,target_pos.y,target_pos.z,{});self.state.ground_piles[key]=pile
            pile.items[projectile_id]=pile.items.get(projectile_id,0)+1
        self.combat.clear_aim()
        if c.uid in self.state.creatures:self.hunting.notify_attack(c,p,self.turn,self.clock.minute,loudness=92,hit=hit)
        else:self.hunting.note_player_noise(p,92,self.turn,self.clock.minute,"weapon")
        self._message(msg);return 1

    def _ready_weapon(self,cmd:ReadyWeaponCommand)->int:
        self._message(self.combat.ready_weapon(cmd.item_id,self.entities.get(cmd.actor,Inventory)));return 1

    def _clear_ready_weapon(self,cmd:ClearReadyWeaponCommand)->int:
        self._message(self.combat.clear_ready_weapon());return 1

    def _aim(self,cmd:AimCommand)->int:
        c=self.state.creatures.get(cmd.target_uid)
        if not c or c.hp<=0:self.combat.clear_aim();self._message("That target is no longer there.");return 1
        p=self.player_pos;dist=abs(c.x-p.x)+abs(c.y-p.y)
        if c.z!=p.z or not self._visible_from(p,WorldPos(c.x,c.y,c.z)):self.combat.clear_aim();self._message("You cannot keep a clear aim on that target.");return 1
        v=self.entities.get(cmd.actor,Vitals)
        if v.stamina<=0:self._message("You are too exhausted to hold a steady aim.");return 1
        v.stamina=max(0,v.stamina-1)
        self._message(self.combat.aim_at(c,cmd.zone,self.player_attribute('perception'),self.player_skill('hunting'),dist));return 1
    def _plant(self,cmd:PlantCommand)->None:
        pos=self.entities.get(cmd.actor,Position).value;crop=self.registry.crops.get(cmd.crop_id);inv=self.entities.get(cmd.actor,Inventory)
        if not crop:self._message("Unknown crop.");return
        if self.world.tile_at(pos).terrain_id!="core:tilled_soil":self._message("The ground must be tilled first.");return
        key=pos_key(pos.x,pos.y,pos.z)
        if key in self.state.crops:self._message("Something is already planted here.");return
        if not inv.remove(crop.seed_item,1):self._message("You do not have the seed.");return
        soil=self.state.soils.get(key)
        disease=0 if not soil else min(70,soil.disease_pressure+(18 if soil.last_crop_id==cmd.crop_id else 0))
        self.state.crops[key]=CropPlot(cmd.crop_id,pos.x,pos.y,pos.z,self.clock.minute,disease=disease);self._message(f"You plant {crop.name}." + (" The soil shows signs of crop fatigue." if disease>=25 else ""))
    def _harvest(self,cmd:HarvestCommand)->None:
        pos=self.entities.get(cmd.actor,Position).value;key=pos_key(pos.x,pos.y,pos.z);plot=self.state.crops.get(key)
        if not plot or not plot.mature:self._message("There is no mature crop here.");return
        crop=self.registry.crops[plot.crop_id];span=max(1,crop.yield_max-crop.yield_min+1);base=crop.yield_min+(self.turn%span);soil=self.state.soils.get(key)
        nutrient=100 if not soil else min(soil.nitrogen,soil.phosphorus,soil.potassium);factor=max(20,min(120,(plot.health+nutrient+max(0,100-plot.disease))//3));amount=max(1,base*factor//100);inv=self.entities.get(cmd.actor,Inventory);inv.add(crop.harvest_item,amount);inv.add(crop.seed_item,max(1,amount//2))
        if soil:soil.last_crop_id=plot.crop_id;soil.disease_pressure=min(100,soil.disease_pressure+(12 if plot.disease else 5))
        self.state.crops.pop(key,None);self._message(f"You harvest {amount} {crop.name.lower()} (yield {factor}%).")
    def till(self)->None:
        pos=self.player_pos;tile=self.world.tile_at(pos);inv=self.entities.get(self.player_id,Inventory)
        if max((self.registry.items[i].quality('till') for i,n in inv.items.items() if n>0 and i in self.registry.items),default=0)<1:self._message('You need a digging stick, hoe, or other tilling tool.');return
        if "soil" not in tile.terrain.tags:self._message("This ground cannot be tilled.");return
        self.world.set_terrain(pos,"core:tilled_soil");key=pos_key(pos.x,pos.y,pos.z)
        if key not in self.state.soils:
            fert=self.world.generator.sample_fields(pos).fertility*100//65535
            self.state.soils[key]=SoilState(pos.x,pos.y,pos.z,max(25,fert),max(25,fert*4//5),max(25,fert*9//10),max(20,fert//2),0,"")
        self._message("You till the soil.")
    def irrigate(self)->None:
        key=pos_key(self.player_pos.x,self.player_pos.y,self.player_pos.z);plot=self.state.crops.get(key)
        if not plot:self._message("There is no crop here to irrigate.");return
        if not self._water_available(self.player_pos):self._message('You need accessible water nearby to irrigate by hand.');return
        plot.moisture=min(100,plot.moisture+35);self._message("You irrigate the crop.")
    def _attack(self,cmd:AttackCommand)->None:
        origin=self.player_pos;p=origin.moved(cmd.dx,cmd.dy);distance=abs(cmd.dx)+abs(cmd.dy)
        target=min((c for c in self.state.creatures.values() if c.z==p.z and c.x==p.x and c.y==p.y),key=lambda c:c.hp,default=None)
        if not target:self._message("There is nothing there to attack.");return
        inv=self.entities.get(cmd.actor,Inventory);v=self.entities.get(cmd.actor,Vitals);weapon=self.combat.readied_weapon(inv)
        if weapon and "ranged" in weapon.tags and not weapon.throwable:self._message(f"The {weapon.name.lower()} is not suited to melee. Ready a melee weapon or lower it to fight unarmed.");return
        reach=weapon.reach if weapon else 1
        if distance<1 or distance>reach:self._message("That target is beyond your current melee reach.");return
        stamina_before=v.stamina;cost=max(2,weapon.stamina_cost if weapon else 4);v.stamina=max(0,v.stamina-cost)
        before_wounds=len(target.wounds);self.combat.clear_aim()
        msg=self.combat.attack_creature(target,inv,self.turn,distance,stamina_before)
        if target.uid in self.state.creatures:self.hunting.notify_attack(target,origin,self.turn,self.clock.minute,loudness=42,hit=len(target.wounds)>before_wounds)
        self._message(msg)
    def _magic_project(self,effects:dict)->None:
        pos=self.player_pos;targets=[c for c in self.state.creatures.values() if c.z==pos.z and abs(c.x-pos.x)+abs(c.y-pos.y)<=4]
        if not targets:self._message("The projected force dissipates without a target.");return
        target=min(targets,key=lambda c:abs(c.x-pos.x)+abs(c.y-pos.y));target.hp-=effects["potency"]*6
        if target.hp<=0:self.state.creatures.pop(target.uid,None);self._message("Arcane force kills the creature.")


    def _equip(self,cmd:EquipCommand)->None:
        inv=self.entities.get(cmd.actor,Inventory);item=self.registry.items.get(cmd.item_id)
        if not item or not item.equip_slot:self._message("That item cannot be equipped.");return
        if inv.count(cmd.item_id)<=0:self._message("You are not carrying that item.");return
        old=self.state.player_equipment.get(item.equip_slot)
        if old:inv.add(old,1)
        self.state.player_equipped_artifacts.pop(item.equip_slot,None)
        artifact=None
        if "durable" in item.tags:artifact=self.artifacts.ensure_for_owner(cmd.item_id,"player",self.clock.minute,"legacy or market maker")
        inv.remove(cmd.item_id,1);self.state.player_equipment[item.equip_slot]=cmd.item_id
        if artifact:self.state.player_equipped_artifacts[item.equip_slot]=artifact.uid
        self._message(f"You equip {item.name.lower()} on your {item.equip_slot}." + (f" [{artifact.condition}% condition]" if artifact else ""))

    def _unequip(self,cmd:UnequipCommand)->None:
        iid=self.state.player_equipment.pop(cmd.slot,None);self.state.player_equipped_artifacts.pop(cmd.slot,None)
        if not iid:self._message("Nothing is equipped in that slot.");return
        self.entities.get(cmd.actor,Inventory).add(iid,1);self._message(f"You remove {self.registry.items[iid].name.lower()}.")

    def _read_book(self,cmd:ReadBookCommand)->None:
        inv=self.entities.get(cmd.actor,Inventory)
        if inv.count("core:book")<=0:self._message("You are not carrying a readable book.");return
        books=[b for b in self.state.books.values() if b.owner=="player"]
        if not books:self._message("The book contains nothing you can make sense of yet.");return
        unknown=[b for b in books if b.knowledge not in self.state.player_knowledge];book=(unknown or books)[0]
        language=book.language_id or book.culture_id or "core:trade_tongue";fluency=self.state.player_languages.get(language,0)
        if language!="core:trade_tongue" and fluency<70:
            gain=max(3,min(12,self.state.player_literacy//10));self.state.player_languages[language]=min(100,fluency+gain)
            if fluency<25:self._message(f"You recognize the script of {book.title}, but understand almost nothing. Repeated study improves your grasp of {language}.");return
            self._message(f"You decipher fragments of {book.title}; your comprehension of {language} improves to {self.state.player_languages[language]}%.")
            if self.state.player_languages[language]<70:return
        if self.state.player_literacy<35:self.state.player_literacy=min(100,self.state.player_literacy+2);self._message("The dense writing exceeds your present literacy, though the attempt teaches you something.");return
        if book.knowledge not in self.state.player_knowledge:self.state.player_knowledge.append(book.knowledge);self._message(f"You read {book.title} by {book.author} and learn {book.knowledge}.")
        else:self._message(f"You reread {book.title}; its knowledge is already familiar.")

    def player_trade_price(self, settlement_id:str, item_id:str, buy:bool)->int:
        base=self.economy.trade_price(settlement_id,item_id,buy)
        bargain=min(22,self.player_skill('trading')*2+(5 if self.has_talent('haggler') else 0)+self.player_skill('persuasion')//2)
        factor=(100-bargain) if buy else (100+bargain)
        return max(1,(base*factor)//100)

    def _buy(self,cmd:BuyCommand)->None:
        town=self.state.settlements.get(cmd.settlement_id);inv=self.entities.get(cmd.actor,Inventory)
        if not town or abs(town.x-self.player_pos.x)+abs(town.y-self.player_pos.y)>25:self._message("You are not close enough to that market.");return
        if town.stocks.get(cmd.item_id,0)<cmd.amount:self._message("The market cannot supply that quantity.");return
        unit=self.player_trade_price(town.uid,cmd.item_id,True);price=unit*cmd.amount
        if inv.count("core:copper_coin")<price:self._message(f"You need {price} copper coins.");return
        inv.remove("core:copper_coin",price);inv.add(cmd.item_id,cmd.amount);town.stocks[cmd.item_id]-=cmd.amount;town.wealth+=price
        for _ in range(cmd.amount):
            self.metallurgy.transfer_one(cmd.item_id,town.uid,"player",self.clock.minute)
            self.artifacts.transfer_one(cmd.item_id,town.uid,"player",self.clock.minute,"purchased")
        if cmd.item_id=="core:book":
            library=self.institutions.library_for_settlement(town.uid);owners={town.uid}|({library.uid} if library else set())
            for b in sorted(self.state.books.values(),key=lambda b:b.uid):
                if b.owner in owners:
                    if library and b.uid in library.book_uids:library.book_uids.remove(b.uid)
                    b.owner="player";break
        self.economy.update_prices();self._message(f"You buy {cmd.amount} {self.registry.items[cmd.item_id].name} for {price}c.")
    def _sell(self,cmd:SellCommand)->None:
        town=self.state.settlements.get(cmd.settlement_id);inv=self.entities.get(cmd.actor,Inventory)
        if not town or abs(town.x-self.player_pos.x)+abs(town.y-self.player_pos.y)>25:self._message("You are not close enough to that market.");return
        if inv.count(cmd.item_id)<cmd.amount:self._message("You do not have that quantity.");return
        unit=self.player_trade_price(town.uid,cmd.item_id,False);price=unit*cmd.amount
        if town.wealth<price:self._message("The market lacks enough coin to buy that.");return
        inv.remove(cmd.item_id,cmd.amount);inv.add("core:copper_coin",price);town.stocks[cmd.item_id]=town.stocks.get(cmd.item_id,0)+cmd.amount;town.wealth-=price
        for _ in range(cmd.amount):
            self.metallurgy.transfer_one(cmd.item_id,"player",town.uid,self.clock.minute)
            self.artifacts.transfer_one(cmd.item_id,"player",town.uid,self.clock.minute,"sold")
        if cmd.item_id=="core:book":
            library=self.institutions.library_for_settlement(town.uid)
            for b in sorted(self.state.books.values(),key=lambda b:b.uid):
                if b.owner=="player":
                    b.owner=library.uid if library else town.uid
                    if library and b.uid not in library.book_uids and len(library.book_uids)<library.capacity:library.book_uids.append(b.uid)
                    break
        self.economy.update_prices();self._message(f"You sell {cmd.amount} {self.registry.items[cmd.item_id].name} for {price}c.")


    def _magic_reveal(self,effects:dict)->None:
        p=self.player_pos;r=8+effects.get("potency",1)*4;keys=set()
        for y in range(p.y-r,p.y+r+1):
            for x in range(p.x-r,p.x+r+1):keys.add(pos_key(x,y,p.z))
        self._record_discovered_tiles(keys);self._message("Hidden terrain presses into your awareness.")
    def _magic_shape(self,effects:dict)->None:
        p=self.player_pos;source=effects.get("source")
        if source=="tide":self.environment.add_water(p,min(255,80+effects.get("potency",1)*25));self._message("Water gathers from the shaped law.")
        elif source=="ember":self.environment.ignite(p,50+effects.get("potency",1)*8);self._message("Flame takes hold in the world.")
        elif source=="bloom" and p.z==0:self.world.set_terrain(p,"core:grass");self._message("Life reclaims the ground.")
        elif source=="stone" and p.z<0:self.world.set_terrain(p,"core:cave_floor");self._message("Stone yields to your shaping.")
        else:self._message("The law bends, but finds little here to reshape.")

    def _handle_death(self,cause:str)->None:
        from worldseed.systems.state import LegacyCharacter
        pos=self.player_pos;inv=self.entities.get(self.player_id,Inventory);key=pos_key(pos.x,pos.y,pos.z);pile=self.state.ground_piles.setdefault(key,GroundPile(pos.x,pos.y,pos.z,{}))
        for iid,n in list(inv.items.items()):pile.items[iid]=pile.items.get(iid,0)+n
        for iid in list(self.state.player_equipment.values()):pile.items[iid]=pile.items.get(iid,0)+1
        self.state.player_equipment.clear();self.state.player_equipped_artifacts.clear();self.state.player_wounds.clear();self.state.player_body_parts={"head":100,"neck":100,"torso":100,"left_arm":100,"right_arm":100,"left_leg":100,"right_leg":100}
        for a in list(self.state.artifacts.values()):
            if a.owner=="player":self.artifacts.transfer_uid(a.uid,f"ground:{pos.x},{pos.y},{pos.z}",self.clock.minute,"lost with a dead bearer")
        inv.items.clear();name=f"Wanderer {len(self.state.legacy)+1}";self.state.legacy.append(LegacyCharacter(name,max(0,self.clock.minute-365*1440),self.clock.minute,cause,pos.x,pos.y,pos.z,[]));self.history.record("death",f"{name} died: {cause}.",self.clock.minute,pos.x//512,pos.y//512,[name],salience=70)
        v=self.entities.get(self.player_id,Vitals);v.hp=v.max_hp;v.hunger=0;v.thirst=0;v.stamina=100;v.pain=0;v.blood=100
        self.entities.get(self.player_id,Position).value=WorldPos(0,0,0);self._message("Your character dies. The world continues. A successor enters the same timeline.")
    def _message(self,message:str)->None:
        self.log.append(GameEvent(self.turn,message));
        if len(self.log)>150:del self.log[:-150]
