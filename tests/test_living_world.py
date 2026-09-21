import tempfile,unittest
from pathlib import Path
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey,WorldPos
from worldseed.entities.components import Inventory,Position,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import WaitCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.generation import ProceduralSocietyGenerator,MagicGenerator
from worldseed.systems.speciesgen import install_procedural_species
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World

class LivingWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.reg=ContentRegistry.load(DATA_DIR)
    def make_sim(self,seed=b'living'):
        td=tempfile.TemporaryDirectory();db=WorldDatabase.create(Path(td.name)/'x.db','x',seed.hex());world=World(WorldGenerator(seed,self.reg),self.reg,db);e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,0)));e.add(pid,Inventory({'core:coal':2,'core:stone':2}));e.add(pid,Vitals());return td,db,world,e,pid,Simulation(world,e,self.reg,0,LivingWorldState(),seed)
    def test_society_generation_deterministic(self):
        a=ProceduralSocietyGenerator(b'x',self.reg).settlement_for_cell(2,-3);b=ProceduralSocietyGenerator(b'x',self.reg).settlement_for_cell(2,-3);self.assertEqual(repr(a),repr(b))
    def test_magic_laws_deterministic(self):
        a=MagicGenerator(b'x').laws();b=MagicGenerator(b'x').laws();self.assertEqual(a,b);self.assertGreater(len(a),0)
    def test_procedural_species_stable(self):
        r1=ContentRegistry.load(DATA_DIR);r2=ContentRegistry.load(DATA_DIR);ids1=install_procedural_species(r1,b'x');ids2=install_procedural_species(r2,b'x');self.assertEqual(ids1,ids2);self.assertEqual([r1.species[x] for x in ids1],[r2.species[x] for x in ids2])
    def test_dungeon_overlay_deterministic(self):
        g=WorldGenerator(b'dungeon',self.reg);key=next(ChunkKey(x,y,-1) for x in range(-20,21) for y in range(-20,21) if g.sites.has_site(ChunkKey(x,y,-1)));a=g.generate_chunk(key).terrain.tolist();b=g.generate_chunk(key).terrain.tolist();self.assertEqual(a,b);self.assertIn(self.reg.terrain_index('core:relic_cache'),a)
    def test_long_advance_invariants(self):
        td,db,world,e,pid,sim=self.make_sim();sim.execute(WaitCommand(pid,90*1440));self.assertTrue(all(c.count>=0 for c in sim.state.cohorts.values()));self.assertTrue(all(s.population>=0 for s in sim.state.settlements.values()));self.assertTrue(all(v>=0 for s in sim.state.settlements.values() for v in s.stocks.values()));db.close();td.cleanup()
    def test_sim_state_roundtrip(self):
        td,db,world,e,pid,sim=self.make_sim();sim.execute(WaitCommand(pid,3*1440));p=e.get(pid,Position).value;db.save_state(turn=sim.turn,tile_deltas=world.drain_dirty_tiles(),player_id=pid,position=p,inventory=e.get(pid,Inventory).items,vitals=e.get(pid,Vitals).__dict__ if hasattr(e.get(pid,Vitals),'__dict__') else {'hp':100,'max_hp':100,'hunger':0,'thirst':0,'stamina':100,'body_temp':50,'pain':0,'blood':100},sim_state=sim.state.to_dict());raw=db.load_sim_state();restored=LivingWorldState.from_dict(raw);self.assertEqual(restored.clock_minute,sim.state.clock_minute);self.assertEqual(set(restored.settlements),set(sim.state.settlements));db.close();td.cleanup()
