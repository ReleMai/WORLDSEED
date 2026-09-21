import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.ui.renderer import Renderer
from worldseed.ui.screens import ecology_screen, settlement_detail_screen
from worldseed.ui.startup import (
    _random_build, ATTRIBUTE_BASE, ATTRIBUTE_POINTS, ATTRIBUTE_MAX,
    SKILL_POINTS, SKILL_MAX, TALENT_POINTS, TALENT_DEFS, StartSelection,
)
from worldseed.ui.terminal import decode_windows_extended
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class RC6SandboxTests(unittest.TestCase):
    def make_sim(self, seed=b'rc6'):
        td=tempfile.TemporaryDirectory();reg=ContentRegistry.load(DATA_DIR)
        db=WorldDatabase.create(Path(td.name)/'world.db','RC6',seed.hex())
        world=World(WorldGenerator(seed,reg),reg,db)
        entities=EntityStore();pid=entities.spawn(preferred_id=1)
        entities.add(pid,Position(WorldPos(0,0,0)));entities.add(pid,Inventory({'core:copper_coin':200}));entities.add(pid,Vitals())
        sim=Simulation(world,entities,reg,0,LivingWorldState(),seed);sim._discover(WorldPos(0,0,0))
        return td,db,reg,world,entities,pid,sim

    def test_random_character_uses_exact_point_budgets(self):
        costs={key:cost for key,_,cost,_ in TALENT_DEFS}
        for _ in range(40):
            build=_random_build();attrs=build['attributes'];skills=build['skills'];talents=build['talents']
            self.assertEqual(sum(v-ATTRIBUTE_BASE for v in attrs.values()),ATTRIBUTE_POINTS)
            self.assertTrue(all(ATTRIBUTE_BASE <= v <= ATTRIBUTE_MAX for v in attrs.values()))
            self.assertEqual(sum(skills.values()),SKILL_POINTS)
            self.assertTrue(all(0 <= v <= SKILL_MAX for v in skills.values()))
            self.assertEqual(sum(costs[x] for x in talents),TALENT_POINTS)

    def test_new_character_build_persists_without_class_or_leads(self):
        from worldseed.app import _load_context
        build={'attributes':{'strength':8,'agility':6,'endurance':7,'intellect':8,'perception':6,'will':7},
               'skills':{'athletics':2,'survival':4,'foraging':2,'woodcutting':0,'mining':6,'hunting':0,'melee':2,'crafting':2,'medicine':0,'scholarship':2,'persuasion':0,'trading':2,'naturalism':2,'arcana':0},
               'talents':['stonewise','keen_senses','haggler','quick_study','field_medic']}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'custom.db';ctx=_load_context(StartSelection(path,True,'Custom',b'custom-build'.hex(),'Mara','custom',build),prepare_world=False)
            try:
                self.assertEqual(ctx.sim.state.player_origin,'custom')
                self.assertEqual(ctx.sim.state.player_attributes,build['attributes'])
                self.assertEqual(ctx.sim.state.player_skills,build['skills'])
                self.assertEqual(ctx.sim.state.player_talents,sorted(build['talents']))
                self.assertEqual(ctx.sim.state.player_rumors,[])
            finally:ctx.db.close()

    def test_windows_extended_left_is_never_escape(self):
        self.assertEqual(decode_windows_extended('K'),'LEFT')
        self.assertEqual(decode_windows_extended('M'),'RIGHT')
        self.assertNotEqual(decode_windows_extended('K'),'ESC')

    def test_camera_recenters_on_player_every_step(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b'camera-player-centered')
        try:
            r=Renderer(reg,use_color=False);r.render(world,e,sim,pid,100,30)
            self.assertEqual(r._camera,(0,0,0))
            e.get(pid,Position).value=WorldPos(1,0,0);r.render(world,e,sim,pid,100,30)
            self.assertEqual(r._camera,(1,0,0))
            e.get(pid,Position).value=WorldPos(100,-40,0);r.render(world,e,sim,pid,100,30)
            self.assertEqual(r._camera,(100,-40,0))
        finally:db.close();td.cleanup()

    def test_wildlife_counts_require_knowledge(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b'wildlife-knowledge')
        try:
            p=sim.player_pos;cx,cy=p.x//256,p.y//256
            local=[c for c in sim.state.cohorts.values() if c.region_x==cx and c.region_y==cy and c.z==0]
            self.assertTrue(local)
            cohort=local[0];sim.state.discovered_species=[cohort.species_id]
            sim.state.player_skills['naturalism']=0;sim.state.player_skills['survival']=0
            text=ecology_screen(sim)
            self.assertIn('signs observed',text)
            self.assertNotIn(f'roughly {cohort.count}',text)
            sim.state.population_reports[f'{cx},{cy}:{cohort.species_id}']=sim.clock.minute
            text=ecology_screen(sim)
            self.assertTrue(any(x in text for x in ('scarce','common','abundant')))
            sim.state.player_skills['naturalism']=8
            self.assertIn('roughly',ecology_screen(sim))
        finally:db.close();td.cleanup()

    def test_heard_of_town_does_not_reveal_market_or_population(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b'town-knowledge')
        try:
            town=next(iter(sim.state.settlements.values()));sim.state.discovered_settlements=[town.uid]
            sim.state.visited_settlements=[]
            text=settlement_detail_screen(sim,town.uid)
            self.assertIn('have not visited',text)
            self.assertNotIn('Population',text)
            self.assertNotIn('STOCKS',text)
        finally:db.close();td.cleanup()

    def test_trading_skill_and_haggler_change_actual_player_price(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b'player-prices')
        try:
            sim._ensure_nearby_world(WorldPos(700,0,0));town=next(iter(sim.state.settlements.values()));iid='core:wood';town.prices[iid]=10
            sim.state.player_skills['trading']=0;sim.state.player_skills['persuasion']=0;sim.state.player_talents=[]
            normal_buy=sim.player_trade_price(town.uid,iid,True);normal_sell=sim.player_trade_price(town.uid,iid,False)
            sim.state.player_skills['trading']=8;sim.state.player_skills['persuasion']=5;sim.state.player_talents=['haggler']
            self.assertLessEqual(sim.player_trade_price(town.uid,iid,True),normal_buy)
            self.assertGreaterEqual(sim.player_trade_price(town.uid,iid,False),normal_sell)
        finally:db.close();td.cleanup()


if __name__=='__main__':unittest.main()
