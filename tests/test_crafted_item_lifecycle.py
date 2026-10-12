"""Crafted instance metadata follows physical goods and ends with spent materials."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path

from tests import test_interior_engine
from tests.test_salvaging import sample_registry
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position
from worldseed.persistence.validation import validate_sim_state
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import DropCommand, PickupCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.artifacts import ArtifactSystem, transfer_inventory_metadata
from worldseed.systems.building import BuildingSystem
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.crafting_quality import retire_consumed_artifacts
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.state import ContainerState, LivingWorldState, StructureInstance, pos_key


class CraftedItemLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.registry = ContentRegistry.load(DATA_DIR)

    def make(self, iid='core:iron_sword', registry=None):
        registry = registry or self.registry
        state = LivingWorldState()
        artifacts = ArtifactSystem(state, registry, b'crafted-lifecycle')
        item = registry.items[iid]
        artifact = artifacts.create(iid, 'maker', 10, quality_hint=80,
            components_override={'body': {'material': item.material or 'core:wood', 'quality': 80, 'condition': 100},
                                 'crafting': {'quality_version': 1, 'material_quality': 70,
                                              'source': 'recovered', 'recipe_id': 'test:recipe',
                                              'ingredients': [{'id': 'core:wood', 'name': 'Wood', 'qty': 2,
                                                               'quality': 70, 'mass_g': 100, 'source': 'recovered',
                                                               'material': 'core:wood'}]}})
        return state, artifacts, artifact

    def test_marked_payload_roundtrip_and_validation_are_observational(self):
        state, artifacts, artifact = self.make()
        artifacts.wear(artifact.base_item, 'player', 1, 12)
        raw = state.to_dict(); before = deepcopy(raw)
        self.assertEqual(validate_sim_state(raw), [])
        restored = LivingWorldState.from_dict(raw)
        self.assertEqual(restored.artifacts[artifact.uid].components, artifact.components)
        self.assertEqual(raw, before)
        legacy = deepcopy(raw); legacy['artifacts'][artifact.uid]['components'].pop('crafting')
        legacy['artifacts'][artifact.uid]['quality'] = 120
        self.assertEqual(validate_sim_state(legacy), [])

    def test_sqlite_roundtrip_and_save_tool_accept_quality_and_reject_corruption(self):
        state, artifacts, artifact = self.make()
        artifacts.wear(artifact.base_item, 'player', 1, 12)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'crafted-quality.db'
            database = WorldDatabase.create(path, 'Crafted quality fixture', b'crafted-lifecycle'.hex())
            try:
                database.save_state(turn=1, tile_deltas={}, player_id=1, position=WorldPos(0, 0, 0),
                                    inventory={artifact.base_item: 1}, sim_state=state.to_dict())
                restored = LivingWorldState.from_dict(database.load_sim_state())
                self.assertEqual(restored.artifacts[artifact.uid].components, artifact.components)
                self.assertEqual(database.verify(), [])
            finally:
                database.close()
            tool = Path(__file__).resolve().parents[1] / 'tools' / 'verify_save.py'
            checked = subprocess.run([sys.executable, str(tool), str(path)], capture_output=True,
                                     text=True, timeout=15)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn('Save integrity: OK', checked.stdout)
            corrupt = state.to_dict()
            corrupt['artifacts'][artifact.uid]['components']['crafting']['wear_remainder'] = 999
            database = WorldDatabase.open(path)
            try:
                database.save_state(turn=1, tile_deltas={}, player_id=1, position=WorldPos(0, 0, 0),
                                    inventory={artifact.base_item: 1}, sim_state=corrupt)
                self.assertTrue(any('wear remainder' in issue for issue in database.verify()))
            finally:
                database.close()

    def test_corrupt_marker_grade_wear_and_provenance_are_rejected(self):
        state, _, artifact = self.make(); raw = state.to_dict()
        corruptions = [('quality', True), ('quality', 101), ('quality_version', 2),
                       ('quality_version', True), ('material_quality', -1), ('source', []),
                       ('recipe_id', 'unqualified'), ('wear_remainder', 130),
                       ('wear_remainder', -1), ('ingredients', {}), ('ingredients', [{}])]
        for field, value in corruptions:
            with self.subTest(field=field, value=value):
                damaged = deepcopy(raw); row = damaged['artifacts'][artifact.uid]
                target = row if field == 'quality' else row['components']['crafting']
                target[field] = value
                self.assertTrue(validate_sim_state(damaged))
        damaged = deepcopy(raw)
        damaged['artifacts'][artifact.uid]['components']['body']['condition'] = 101
        self.assertTrue(validate_sim_state(damaged))

    def test_retirement_bounds_components_and_preserves_spent_gear_history(self):
        state, _, gear = self.make()
        for minute in range(100):
            system = ArtifactSystem(state, self.registry, b'bounded-components')
            part = system.create('core:wood', 'maker', minute, quality_hint=70,
                                 components_override={'crafting': {'quality_version': 1}})
            retire_consumed_artifacts(state, self.registry, {'core:wood': 1}, minute=minute)
            self.assertNotIn(part.uid, state.artifacts)
        self.assertEqual(len(state.artifacts), 1)
        retire_consumed_artifacts(state, self.registry, {gear.base_item: 1}, minute=110, reason='Salvaged')
        self.assertEqual(gear.owner, 'consumed')
        self.assertIn('Salvaged', gear.history[-1])
        self.assertEqual(gear.provenance[-1]['to'], 'consumed')
        self.assertIsNone(ArtifactSystem(state, self.registry, b'').best_owned(gear.base_item))

    def test_salvage_reserves_and_retires_the_spent_instance_once(self):
        registry = sample_registry()
        state, artifacts, component = self.make('test:damaged_box', registry)
        inv = Inventory({'test:damaged_box': 2})
        salvage = SalvagingSystem(state, registry)
        self.assertTrue(salvage.begin(component.base_item, inv, b'lifecycle', 30)[0])
        self.assertNotIn(component.uid, state.artifacts)
        before = state.to_dict(), dict(inv.items)
        self.assertFalse(salvage.begin(component.base_item, inv, b'lifecycle', 31)[0])
        self.assertEqual((state.to_dict(), inv.items), before)
        self.assertIsNone(artifacts.best_owned(component.base_item))

    def test_experiment_and_component_design_retire_inputs(self):
        state, artifacts, stone = self.make('core:stone')
        state.player_crafting_discovery_enabled = True
        crafting = CraftingSystem(state, self.registry, artifacts)
        inv = Inventory({'core:stone': 1})
        self.assertTrue(crafting.combine_in_pot(('core:stone',), inv, b'lifecycle-pot', 40)[0])
        self.assertNotIn(stone.uid, state.artifacts)
        state, artifacts, wood = self.make('core:wood')
        state.player_knowledge += ['tech:smelting', 'tech:steelmaking']
        crafting = CraftingSystem(state, self.registry, artifacts)
        inv = Inventory({'core:iron_bloom': 1, 'core:wood': 1, 'core:hide': 1})
        ok, message, _ = crafting.craft_design('core:modular_sword',
            {'blade': 'core:iron_bloom', 'grip': 'core:wood', 'wrapping': 'core:hide'}, inv, {'core:forge'}, 50)
        self.assertTrue(ok, message)
        self.assertNotIn(wood.uid, state.artifacts)
        self.assertEqual(inv.count('core:crafted_sword'), 1)

    def test_ground_drop_and_pickup_move_exact_uid_and_do_not_reuse_its_quality(self):
        state, artifacts, artifact = self.make()
        inv = Inventory({artifact.base_item: 1}); pos = WorldPos(2, 3, 0)
        sim = SimpleNamespace(state=state, registry=self.registry, clock=SimpleNamespace(minute=20),
            entities=SimpleNamespace(get=lambda actor, kind: SimpleNamespace(value=pos) if kind is Position else inv),
            _message=lambda message: None)
        Simulation._drop(sim, DropCommand(1, artifact.base_item))
        self.assertEqual(artifact.owner, 'ground:2,3,0')
        inv.add(artifact.base_item, 1)
        self.assertIsNone(artifacts.best_owned(artifact.base_item))
        Simulation._pickup(sim, PickupCommand(1))
        self.assertEqual(artifact.owner, 'player')
        self.assertEqual(inv.count(artifact.base_item), 2)
        self.assertEqual(len(state.artifacts), 1)
        self.assertEqual(artifact.quality, 80)

    def test_indoor_drop_pickup_preserves_instance_and_pile_owner(self):
        sim, plan = test_interior_engine.InteriorEngineTests.prepared_simulation(self)
        artifact = sim.artifacts.create('core:iron_sword', 'maker', 0, quality_hint=80,
            components_override={'body': {'material': 'core:iron', 'quality': 80, 'condition': 100},
                                 'crafting': {'quality_version': 1}})
        inv = sim.entities.get(sim.player_id, Inventory); inv.add(artifact.base_item, 1)
        sim.execute(DropCommand(sim.player_id, artifact.base_item))
        self.assertEqual(artifact.owner, f'{plan.uid}:pile:{plan.piles[0].uid}')
        self.assertIsNone(sim.artifacts.best_owned(artifact.base_item))
        # Successor/death piles use the same owner contract as ordinary drops.
        sim.execute(PickupCommand(sim.player_id))
        self.assertEqual(artifact.owner, 'player')
        self.assertEqual(inv.count(artifact.base_item), 1)
        self.assertEqual(plan.piles, [])

    def test_container_store_take_move_and_spills_keep_exact_instances(self):
        for action in ('take', 'dismantle', 'destroy'):
            with self.subTest(action=action):
                state, artifacts, artifact = self.make(); inv = Inventory({artifact.base_item: 1})
                building = BuildingSystem(state, self.registry)
                container = ContainerState('cache:quality', 1, 2, 0, 'player', 100000, 100000, {},
                                           kind='natural' if action == 'destroy' else 'built', movable=True)
                state.containers[pos_key(1, 2, 0)] = container
                self.assertTrue(building.store(container, inv, artifact.base_item)[0])
                self.assertEqual(artifact.owner, 'container:cache:quality')
                self.assertIsNone(artifacts.best_owned(artifact.base_item))
                if action == 'take':
                    self.assertTrue(building.move_container(container, WorldPos(2, 2, 0))[0])
                    self.assertEqual(artifact.owner, 'container:cache:quality')
                    self.assertTrue(building.take(container, inv, artifact.base_item)[0])
                    self.assertEqual(artifact.owner, 'player')
                else:
                    if action == 'dismantle':
                        state.structures[pos_key(1, 2, 0)] = StructureInstance('core:wood_chest', 1, 2, 0)
                        self.assertTrue(building.dismantle(WorldPos(1, 2, 0), inv)[0])
                    else: self.assertTrue(building.destroy_container(container)[0])
                    self.assertEqual(artifact.owner, 'ground:1,2,0')
                    self.assertEqual(state.ground_piles[pos_key(1, 2, 0)].items[artifact.base_item], 1)
                self.assertEqual(len(state.artifacts), 1)

    def test_physical_transfer_preserves_only_existing_metal_batches(self):
        from worldseed.systems.metallurgy import MetallurgySystem
        state = LivingWorldState(); metallurgy = MetallurgySystem(state, self.registry, b'lifecycle-metal')
        batch = metallurgy._create_batch('core:iron_bloom', 'player', 'core:iron', 2000, 25, 3, 80, 75, 1, ['test'])
        transfer_inventory_metadata(state, self.registry, {'core:iron_bloom': 2}, 'player', 'ground:0,0,0', 10, 'Dropped')
        self.assertEqual(batch.owner, 'ground:0,0,0')
        transfer_inventory_metadata(state, self.registry, {'core:iron_bloom': 2}, 'ground:0,0,0', 'player', 11, 'Picked up')
        self.assertEqual(batch.owner, 'player')
        self.assertEqual(len(state.metal_batches), 1)


if __name__ == '__main__': unittest.main()
