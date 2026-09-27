import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")

import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR, SETTLEMENT_PLAN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.building import BuildingSystem
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.generation import specialize_occupation
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.professions import SettlementProfessionSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.state import LivingWorldState
from worldseed.systems.workshops import WORKSHOP_PROFILES, STATION_PIECE_ALIASES, recipes_for_station, profile_dict
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class Cache:
    def load_generated_settlement_plan(self,*_): return None
    def store_generated_settlement_plan(self,*_): pass
    def commit_generated(self): pass


class Env:
    open_water=False
    slope=4
    flood_risk=3
    wetness=42
    soil_fertility=78
    farmland=84
    resources=SimpleNamespace(stone=80,timber=72,freshwater=66)
    resource_opportunity=73


class WorkshopExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def _city(self):
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b"workshop-expansion"),
            delta_source=Cache(),registry=self.registry,
            settlement_plan_version=SETTLEMENT_PLAN_VERSION,
            environment_at=lambda pos:Env(),
            is_passable=lambda pos:True,
        )
        region=RegionBlockPlan(
            uid="workshop-city-region",region_x=0,region_y=0,version=1,
            dominant_biome="grassland",biome_mix={"grassland":25},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(220,220),settlement_score=92,
            settlement_archetype="mining",control_potential="settled",
            roads=(
                RegionRoadExit("north",220,"road"),RegionRoadExit("east",220,"road"),
                RegionRoadExit("south",220,"road"),RegionRoadExit("west",220,"road"),
            ),
        )
        planner=SettlementSkeletonPlanner(world)
        skeleton=planner.plan(region,"settlement:workshop-city",300,persist=False)
        return world,region,planner,skeleton

    def test_every_workshop_profile_has_station_and_player_recipe(self):
        self.assertEqual(SETTLEMENT_PLAN_VERSION,7)
        self.assertGreaterEqual(len(WORKSHOP_PROFILES),12)
        for station_id,profile in WORKSHOP_PROFILES.items():
            self.assertIn(station_id,self.registry.structures,station_id)
            self.assertIn("station",self.registry.structures[station_id].tags,station_id)
            recipes=recipes_for_station(self.registry,station_id)
            self.assertTrue(recipes,station_id)
            self.assertTrue(profile.purpose.strip(),station_id)
            self.assertTrue(profile.action_label.strip(),station_id)
        for piece_id,station_id in STATION_PIECE_ALIASES.items():
            self.assertIn(piece_id,self.registry.settlement_pieces,piece_id)
            self.assertIn(station_id,self.registry.structures,station_id)

    def test_city_generates_specialist_workshops_with_passable_clutter(self):
        _,_,_,skeleton=self._city()
        functions={s.function for s in skeleton.structures}
        expected={
            "smithy","bakery","butcher","weavery","tannery",
            "pottery","brewery","mason_yard","mill","clinic",
        }
        self.assertTrue(expected.issubset(functions),functions)
        role_for={
            "smithy":"smith","bakery":"baker","butcher":"butcher","weavery":"weaver",
            "tannery":"tanner","pottery":"potter","brewery":"brewer",
            "mason_yard":"mason","mill":"miller","clinic":"healer",
        }
        by_structure={}
        for p in skeleton.pieces:by_structure.setdefault(p.structure_plan_id,[]).append(p)
        for structure in skeleton.structures:
            if structure.function not in role_for:continue
            self.assertEqual(structure.workplace_role,role_for[structure.function])
            pieces=by_structure[structure.uid]
            self.assertTrue(any(p.role=="fixture" for p in pieces),structure.function)
            decor=[p for p in pieces if p.role=="tile_decor"]
            self.assertTrue(decor,structure.function)
            for p in decor:
                self.assertTrue(self.registry.settlement_pieces[p.piece_id].passable,p.piece_id)

        homes=[s for s in skeleton.structures if s.function=="residence"]
        self.assertTrue(homes)
        for home in homes[:5]:
            decor=[p for p in by_structure[home.uid] if p.role=="tile_decor"]
            self.assertGreaterEqual(len(decor),2,home.uid)
            self.assertTrue(all(self.registry.settlement_pieces[p.piece_id].passable for p in decor))

    def test_generated_mill_is_a_real_player_usable_station(self):
        world,region,planner,skeleton=self._city()
        mill=next(s for s in skeleton.structures if s.function=="mill")
        placements=[p for p in skeleton.pieces if p.structure_plan_id==mill.uid]
        mill_piece=next(p for p in placements if p.piece_id=="core:millstone_piece")

        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:region)
        planner._cache["settlement:workshop-city"]=skeleton
        physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,planner)
        town=SimpleNamespace(
            uid="settlement:workshop-city",region_x=0,region_y=0,population=300,
            culture_id="",faction_id="",
        )
        physical.sync([town],(0,0),radius=0)
        state=LivingWorldState(player_crafting_discovery_enabled=False)
        building=BuildingSystem(state,self.registry)
        building.attach_settlement_physicalization(physical)
        stations=building.nearby_station_ids(WorldPos(mill_piece.x,mill_piece.y,0),radius=0)
        self.assertIn("core:millstone",stations)

        craft=CraftingSystem(state,self.registry)
        inv=Inventory({"core:wheat":2})
        ok,why=craft.can_craft("core:mill_flour",inv,stations)
        self.assertTrue(ok,why)
        ok,msg,_=craft.craft("core:mill_flour",inv,stations)
        self.assertTrue(ok,msg)
        self.assertEqual(inv.count("core:flour"),2)

    def test_specializations_and_exact_processes_cover_new_trades(self):
        expected={"miller","baker","butcher","fisher","weaver","tanner","brewer","potter","mason"}
        seen=set()
        for base in ("farmer","hunter","carpenter"):
            for i in range(600):
                seen.add(specialize_occupation(base,"settlement:test",i))
        self.assertTrue(expected.issubset(seen),seen)
        process_expected={
            "miller":"core:grain_milling","baker":"core:bread_baking",
            "butcher":"core:butcher_portions","fisher":"core:fish_smoking",
            "weaver":"core:cloth_weaving","tanner":"core:leather_tanning",
            "brewer":"core:small_ale_brewing","potter":"core:pottery_work",
            "mason":"core:masonry_work",
        }
        for occupation,pid in process_expected.items():
            self.assertIn(pid,SettlementProfessionSystem.PROCESS_IDS[occupation])
            self.assertEqual(self.registry.settlement_processes[pid].occupation,occupation)


@unittest.skipUnless(PygameTerminal.available(),"requires pygame-ce")
class WorkshopPygameUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def setUp(self):
        self.term=PygameTerminal(1280,800);self.term.enter();self.term.pg.event.clear()

    def tearDown(self):
        self.term.restore()

    def test_each_workshop_profile_renders_station_specific_action_ui(self):
        recipe_meta={
            "name":"Test Process","ready":True,"missing":[],
            "inputs":[{"name":"Wood","id":"core:wood","have":2,"need":1}],
            "outputs":[{"name":"Stone","id":"core:stone","qty":1}],
            "minutes":30,"skill":"crafting","difficulty":1,"description":"A test process.",
        }
        for station_id,profile in WORKSHOP_PROFILES.items():
            recipes=recipes_for_station(self.registry,station_id)
            self.assertTrue(recipes,station_id)
            rid=recipes[0].id
            data={
                "recipes":{rid:{**recipe_meta,"name":recipes[0].name}},
                "profile":profile_dict(profile),
                "stations":[{**profile_dict(profile),"short_title":profile.title}],
                "station_id":station_id,"locked_count":0,
            }
            self.term.present_feature_menu(
                "workshop_station",profile.title,[MenuRow(rid,recipes[0].name)],0,data=data
            )
            tokens={token for _,token in self.term._pointer_targets}
            self.assertIn("UI_ACTION:workshop_craft",tokens,station_id)
            self.assertIn(f"UI_ACTION:workshop:{station_id}",tokens,station_id)
            self.assertIn("UI_ACTION:tab:workshops",tokens,station_id)
            self.assertEqual(self.term._floating_panel_id,"crafting")


if __name__=="__main__":
    unittest.main()
