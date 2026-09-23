import tempfile
import unittest
from pathlib import Path

from worldseed.app import _find_spawn
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import GatherCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class PersistenceTests(unittest.TestCase):
    def test_gather_save_reload(self):
        registry = ContentRegistry.load(DATA_DIR)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.db"
            seed_hex = b"persistence-seed".hex()
            db = WorldDatabase.create(path, "Test", seed_hex)
            gen = WorldGenerator(bytes.fromhex(seed_hex), registry)
            world = World(gen, registry, db)
            entities = EntityStore()
            player = entities.spawn(preferred_id=1)
            entities.add(player, Inventory({'core:stone_axe':1,'core:iron_pick':1}))
            entities.add(player, Vitals())
            state=LivingWorldState()
            self.addCleanup(db.close)
            entities.add(player,Position(WorldPos(0,0,0)))
            # Find a deterministic surface feature. Resource depletion, not the
            # underlying biome terrain, is the persistent harvest delta.
            probe_sim = Simulation(world,entities,registry,0,state,bytes.fromhex(seed_hex))
            center=_find_spawn(world,'wanderer',probe_sim.resources)
            target = None
            for y in range(center.y-60, center.y+61):
                for x in range(center.x-60, center.x+61):
                    pos=WorldPos(x,y,0)
                    if target is None:
                        entities.add(player, Position(pos)) if entities.try_get(player,Position) is None else setattr(entities.get(player,Position),'value',pos)
                        if probe_sim is None:probe_sim=Simulation(world,entities,registry,0,state,bytes.fromhex(seed_hex))
                        fv=probe_sim.resources.feature_at(pos)
                        if fv and fv.stage=='mature':target=pos;break
                if target:break
            self.assertIsNotNone(target)
            entities.get(player,Position).value=target
            sim=probe_sim
            before=world.tile_at(target).terrain_id
            sim.execute(GatherCommand(player))
            after=world.tile_at(target).terrain_id
            self.assertEqual(before,after,'surface harvesting must not replace ground/biome terrain')
            self.assertIn(f'{target.x},{target.y},{target.z}',sim.state.resource_depletion)
            inv=entities.get(player,Inventory)
            db.save_state(turn=sim.turn,tile_deltas=world.drain_dirty_tiles(),player_id=player,position=target,inventory=inv.items,vitals={},sim_state=sim.state.to_dict())
            db.close()

            db2=WorldDatabase.open(path)
            world2=World(WorldGenerator(bytes.fromhex(seed_hex),registry,version=int(db2.get_meta('worldgen_version'))),registry,db2)
            state2=LivingWorldState.from_dict(db2.load_sim_state())
            entities2=EntityStore();p2=entities2.spawn(preferred_id=1);entities2.add(p2,Position(target));entities2.add(p2,Inventory(db2.load_component(1,'Inventory')['items']));entities2.add(p2,Vitals())
            sim2=Simulation(world2,entities2,registry,int(db2.get_meta('turn')),state2,bytes.fromhex(seed_hex))
            self.assertEqual(world2.tile_at(target).terrain_id,before)
            self.assertNotEqual(sim2.resources.feature_at(target).stage,'mature')
            self.assertTrue(entities2.get(p2,Inventory).items)
            db2.close()

