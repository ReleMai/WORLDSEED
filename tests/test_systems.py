import tempfile,unittest
from dataclasses import asdict
from pathlib import Path
from worldseed.config import DATA_DIR, ENGINE_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory,Position,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import CraftCommand,BuildCommand,MoveCommand,WaitCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState,StructureInstance,pos_key,FireCell,FluidCell
from worldseed.ui.renderer import Renderer
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World

class SystemTests(unittest.TestCase):
    def setUp(self):
        self.reg=ContentRegistry.load(DATA_DIR);self.td=tempfile.TemporaryDirectory();self.seed=b'systems';self.db=WorldDatabase.create(Path(self.td.name)/'s.db','s',self.seed.hex());self.world=World(WorldGenerator(self.seed,self.reg),self.reg,self.db);self.e=EntityStore();self.pid=self.e.spawn(preferred_id=1);self.e.add(self.pid,Position(WorldPos(0,0,0)));self.e.add(self.pid,Inventory({'core:stone':20,'core:wood':20,'core:fiber':10,'core:iron_ore':4,'core:coal':6,'core:iron_bloom':2,'core:hide':2}));self.e.add(self.pid,Vitals());self.sim=Simulation(self.world,self.e,self.reg,0,LivingWorldState(),self.seed)
    def tearDown(self):self.db.close();self.td.cleanup()
    def test_shortage_raises_price(self):
        if not self.sim.state.settlements:self.skipTest('seed generated no settlement')
        s=next(iter(self.sim.state.settlements.values()));s.stocks['core:iron_ore']=100;self.sim.economy.update_prices();cheap=s.prices['core:iron_ore'];s.stocks['core:iron_ore']=1;self.sim.economy.update_prices();self.assertGreater(s.prices['core:iron_ore'],cheap)
    def test_artifact_created_by_weapon_craft(self):
        # weapon recipe does not need a station for this direct unit check; make forge nearby and provide knowledge.
        p=self.sim.player_pos;self.sim.state.player_knowledge.append('tech:smelting');self.sim.state.structures[pos_key(p.x+1,p.y,p.z)]=StructureInstance('core:forge',p.x+1,p.y,p.z)
        self.sim.execute(CraftCommand(self.pid,'core:iron_sword'));self.assertTrue(self.sim.state.artifacts);a=next(iter(self.sim.state.artifacts.values()));self.assertEqual(a.base_item,'core:iron_sword');self.assertGreaterEqual(a.quality,20)
    def test_fire_damages_flammable_structure(self):
        p=self.sim.player_pos;k=pos_key(p.x,p.y,p.z);self.sim.state.structures[k]=StructureInstance('core:wood_wall',p.x,p.y,p.z,condition=20);self.sim.state.fires[k]=FireCell(p.x,p.y,p.z,100,100);self.sim.environment.hourly_update(60);self.assertLess(self.sim.state.structures[k].condition,20);self.sim.environment.hourly_update(120);self.assertNotIn(k,self.sim.state.structures)
    def test_deep_fluid_not_passable(self):
        p=self.sim.player_pos.moved(1,0);self.sim.state.fluids[pos_key(p.x,p.y,p.z)]=FluidCell(p.x,p.y,p.z,'water',240);self.assertFalse(self.sim.environment.fluid_passable(p))
    def test_renderer_is_observational(self):
        before=self.sim.state.to_dict();Renderer(self.reg,use_color=False).render(self.world,self.e,self.sim,self.pid,100,30);after=self.sim.state.to_dict();self.assertEqual(before,after)
    def test_underground_cohorts_exist(self):
        self.sim.ecology.materialize_near(WorldPos(0,0,-2));self.assertTrue(any(c.z==-2 for c in self.sim.state.cohorts.values()));self.assertTrue(any(self.reg.species[c.species_id].habitats==('underground',) or 'underground' in self.reg.species[c.species_id].habitats for c in self.sim.state.cohorts.values() if c.z==-2 and c.count>0))
    def test_save_migration_v1_to_current(self):
        self.db.set_meta('save_schema',1);self.db.connection.commit();path=self.db.path;self.db.close();db2=WorldDatabase.open(path);self.assertEqual(db2.get_meta('save_schema'),3);db2.close();self.db=WorldDatabase.open(path)
    def test_save_migration_v2_to_current(self):
        self.db.set_meta('save_schema',2);self.db.set_meta('engine_version','0.90.0-alpha');self.db.connection.commit();path=self.db.path;self.db.close();db2=WorldDatabase.open(path);self.assertEqual(db2.get_meta('save_schema'),3);self.assertEqual(db2.get_meta('engine_version'),ENGINE_VERSION);db2.close();self.db=WorldDatabase.open(path)
