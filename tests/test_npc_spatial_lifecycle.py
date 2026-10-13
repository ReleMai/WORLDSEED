"""Non-AI actor transitions immediately refresh the transient NPC locator."""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.disease import EpidemiologySystem
from worldseed.systems.family import FamilySystem
from worldseed.systems.interior_state import InteriorActor, InteriorPlan
from worldseed.systems.interiors import InteriorSystem
from worldseed.systems.migration import MigrationSystem
from worldseed.systems.state import (
    LivingWorldState, MigrationCohortState, NPCState, SettlementState,
)


def person(uid, x=0, y=0, *, age=30, town="town:origin"):
    return NPCState(uid, uid, age, "farmer", [], x, y, 0, town, "")


def town(uid, x=0, y=0):
    return SettlementState(uid, uid, x // 512, y // 512, x, y, 20, "", "", "")


class NPCSpatialLifecycleTests(unittest.TestCase):
    def test_ai_property_binding_refreshes_every_repositioned_resident(self):
        from tests.test_settlement_population_bindings import SettlementPopulationBindingTests

        SettlementPopulationBindingTests.setUpClass()
        state, home, physical, binder = SettlementPopulationBindingTests()._fixture()
        index = NPCSystem(state, b"lifecycle", Mock())
        binder.npc_index = index._index_npc
        index.settlement_population = binder
        original_positions = {uid: (npc.x, npc.y, npc.z) for uid, npc in state.npcs.items()}
        first = next(iter(state.npcs.values()))
        index._assign_property(first, home)
        # No subsequent AI execution or index rebuild repairs these reads.
        moved = [npc for uid, npc in state.npcs.items()
                 if original_positions[uid] != (npc.x, npc.y, npc.z)]
        self.assertGreater(len(moved), 1)
        self.assertTrue(any(npc is not first for npc in moved))
        for npc in moved:
            current = WorldPos(npc.x, npc.y, npc.z)
            self.assertIn(npc, index.nearby_npcs(current, 0))
            self.assertIn(npc, index.indexed_npcs_in_rect(npc.x, npc.y, npc.x, npc.y, npc.z))
            old = WorldPos(*original_positions[npc.uid])
            self.assertNotIn(npc, index.nearby_npcs(old, 0))
        expected_levels = {0: len(state.npcs)}
        self.assertEqual(index._npc_spatial_level_counts, expected_levels)

    def test_birth_registers_child_before_another_ai_decision(self):
        state = LivingWorldState()
        home = town("town:origin", 200, 201)
        left, right = person("parent:a"), person("parent:b")
        left.spouse_uid, right.spouse_uid = right.uid, left.uid
        state.settlements[home.uid] = home
        state.npcs = {left.uid: left, right.uid: right}
        index = NPCSystem(state, b"lifecycle", Mock())
        family = FamilySystem(state, b"lifecycle", Mock())
        family.npc_index = index._index_npc
        with patch("worldseed.systems.family.hash_u64", return_value=0):
            family.monthly_update(30 * 1440)
        children = [npc for npc in state.npcs.values() if npc.age == 0]
        self.assertEqual(len(children), 1)
        self.assertEqual(index.nearby_npcs(WorldPos(home.x, home.y), 8), tuple(children))
        self.assertEqual(left.children, [children[0].uid])
        self.assertEqual(home.population, 21)

    def test_family_death_removes_bucket_membership_immediately(self):
        state = LivingWorldState()
        elder = person("npc:elder", 33, 34, age=110)
        state.npcs[elder.uid] = elder
        index = NPCSystem(state, b"lifecycle", Mock())
        family = FamilySystem(state, b"lifecycle", Mock())
        family.npc_index = index._index_npc
        with patch("worldseed.systems.family.hash_u64", return_value=0):
            family._mortality(30 * 1440)
        self.assertFalse(elder.alive)
        self.assertNotIn(elder.uid, index._npc_spatial_positions)
        self.assertEqual(index.nearby_npcs(WorldPos(33, 34), 0), ())

    def test_named_disease_death_removes_bucket_membership_immediately(self):
        state = LivingWorldState()
        home = town("town:origin", 33, 34)
        resident = person("npc:infected", 33, 34)
        state.npcs[resident.uid] = resident
        state.settlements[home.uid] = home
        index = NPCSystem(state, b"lifecycle", Mock())
        disease = EpidemiologySystem(state, SimpleNamespace(diseases={}), b"lifecycle", Mock())
        disease.npc_index = index._index_npc
        disease._death_npc(resident, home, SimpleNamespace(name="Fever"), 1440)
        self.assertFalse(resident.alive)
        self.assertNotIn(resident.uid, index._npc_spatial_positions)
        self.assertEqual(index.nearby_npcs(WorldPos(33, 34), 0), ())
        self.assertEqual(home.population, 19)
        self.assertIn("grave:" + resident.uid, state.graves)
        disease._death_npc(resident, home, SimpleNamespace(name="Fever"), 1440)
        self.assertEqual(home.population, 19)

    def test_migration_moves_locator_and_clears_previous_plan(self):
        state = LivingWorldState()
        origin, destination = town("town:origin"), town("town:destination", 512, 520)
        migrant = person("npc:migrant", 3, 4)
        migrant.tasks = [{"kind": "move", "x": 4, "y": 4}]
        migrant.home_id = "old:home"
        state.npcs[migrant.uid] = migrant
        state.settlements = {origin.uid: origin, destination.uid: destination}
        cohort = MigrationCohortState("migration:test", origin.uid, destination.uid,
                                      3, "hardship", 0, 120, "traveling", 20,
                                      [migrant.uid])
        state.migration_cohorts[cohort.uid] = cohort
        index = NPCSystem(state, b"lifecycle", Mock())
        migration = MigrationSystem(state, b"lifecycle", Mock())
        migration.npc_index = index._index_npc
        migration.process(120)
        self.assertEqual(index.nearby_npcs(WorldPos(3, 4), 0), ())
        self.assertEqual(index.nearby_npcs(WorldPos(512, 520), 0), (migrant,))
        self.assertEqual(migrant.settlement_id, destination.uid)
        self.assertEqual(migrant.tasks, [])
        self.assertEqual(migrant.home_id, "")
        self.assertEqual(cohort.status, "arrived")

    def test_interior_exit_reindexes_new_outdoor_landing(self):
        state = LivingWorldState()
        resident = person("npc:resident", 15, 0)
        state.npcs[resident.uid] = resident
        state.interior_actors[resident.uid] = InteriorActor("interior:home", 1000, 1000)
        index = NPCSystem(state, b"lifecycle", Mock())
        system = InteriorSystem(SimpleNamespace(state=state, npcs=index))
        resident.x, resident.y = 16, 0
        system._remove_actor(resident.uid)
        self.assertNotIn(resident.uid, state.interior_actors)
        self.assertEqual(index.nearby_npcs(WorldPos(16, 0), 0), (resident,))
        self.assertEqual(index.nearby_npcs(WorldPos(15, 0), 0), ())

    def test_interior_entry_reindexes_exterior_portal_anchor(self):
        state = LivingWorldState()
        resident = person("npc:resident", 15, 0)
        resident.home_id = "house:test"
        state.npcs[resident.uid] = resident
        index = NPCSystem(state, b"lifecycle", Mock())
        door = SimpleNamespace(uid="door:test", role="entrance", property_id=resident.home_id,
                               x=16, y=0, z=0)
        security = SimpleNamespace(door_by_id=lambda uid: door, blocks_actor=lambda *args: False)
        sim = SimpleNamespace(state=state, npcs=index, property_security=security,
                              clock=SimpleNamespace(minute=600))
        system = InteriorSystem(sim)
        plan = InteriorPlan("interior:home", resident.home_id, door.uid, 16, 0, 0,
                            9000, 9000, function="residence")
        system._prepare = lambda unused: plan
        system._npc_entry_point = lambda unused: (1000, 1000)
        self.assertTrue(system.enter_npc(resident, door.uid))
        self.assertEqual((resident.x, resident.y), (16, 0))
        self.assertIn(resident.uid, state.interior_actors)
        self.assertEqual(index._npc_spatial_positions[resident.uid], (1, 0, 0))

    def test_standalone_systems_keep_callbacks_optional(self):
        state = LivingWorldState()
        resident = person("npc:resident")
        state.npcs[resident.uid] = resident
        family = FamilySystem(state, b"lifecycle", Mock())
        migration = MigrationSystem(state, b"lifecycle", Mock())
        self.assertIsNone(family.npc_index)
        self.assertIsNone(migration.npc_index)
        family.monthly_update(30 * 1440)
        migration.process(120)
        system = InteriorSystem(SimpleNamespace(state=state))
        system._put_actor(resident.uid, InteriorActor("interior:home", 1000, 1000))
        system._remove_actor(resident.uid)
        self.assertNotIn(resident.uid, state.interior_actors)


if __name__ == "__main__":
    unittest.main()
