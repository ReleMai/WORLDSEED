import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.settlement_population import SettlementPopulationBinder
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class SettlementPopulationBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def _fixture(self):
        class Cache:
            def load_generated_settlement_plan(self, *_):
                return None
            def store_generated_settlement_plan(self, *_):
                pass
            def commit_generated(self):
                pass

        env = SimpleNamespace(
            open_water=False,
            slope=5,
            flood_risk=4,
            wetness=40,
            soil_fertility=76,
            farmland=82,
            resources=SimpleNamespace(stone=80, timber=58, freshwater=55),
            resource_opportunity=66,
        )
        world = SimpleNamespace(
            generator=SimpleNamespace(world_seed=b"population-binding-test"),
            delta_source=Cache(),
            registry=self.registry,
            environment_at=lambda pos: env,
        )
        region = RegionBlockPlan(
            uid="binding-region",
            region_x=0,
            region_y=0,
            version=1,
            dominant_biome="grassland",
            biome_mix={"grassland": 25},
            mean_elevation=1,
            mean_moisture=1,
            mean_temperature=1,
            relief=1,
            settlement_present=True,
            settlement_anchor=(180, 180),
            settlement_score=85,
            settlement_archetype="mining",
            control_potential="settled",
            roads=(
                RegionRoadExit("north", 180, "road"),
                RegionRoadExit("east", 180, "road"),
            ),
        )
        region_planner = SimpleNamespace(plan=lambda rx, ry, persist=True: region)
        skeleton_planner = SettlementSkeletonPlanner(world)
        physical = SettlementPhysicalizationSystem(
            world, self.registry, region_planner, skeleton_planner
        )
        settlement = SettlementState(
            uid="settlement:binding",
            name="Binding Test",
            region_x=0,
            region_y=0,
            x=180,
            y=180,
            population=95,
            culture_id="culture:test",
            religion_id="religion:test",
            faction_id="faction:test",
        )
        state = LivingWorldState()
        state.settlements[settlement.uid] = settlement
        occupations = ("smith", "miner", "farmer", "herder", "carpenter", "guard")
        for i, occupation in enumerate(occupations):
            npc = NPCState(
                uid=f"npc:binding:{i}",
                name=f"NPC {i}",
                age=30 + i,
                occupation=occupation,
                traits=["patient", "kind"],
                x=180,
                y=180,
                z=0,
                settlement_id=settlement.uid,
                faction_id=settlement.faction_id,
            )
            state.npcs[npc.uid] = npc
        first = state.npcs["npc:binding:0"]
        first.home_id = f"{settlement.uid}:house:0"
        first.workplace_id = f"{settlement.uid}:smith:0"
        physical.sync([settlement], (0, 0), radius=0)
        binder = SettlementPopulationBinder(
            state, self.registry, world.generator.world_seed, physical
        )
        return state, settlement, physical, binder

    def test_representatives_bind_to_real_homes_rooms_beds_and_parcels(self):
        state, settlement, physical, binder = self._fixture()
        stats = binder.bind_settlement(settlement)
        skeleton = physical.skeleton_for(settlement.uid)
        self.assertEqual(stats.npcs, 6)
        self.assertEqual(stats.homeless, 0)
        self.assertEqual(stats.homes_bound, 6)
        self.assertEqual(len({n.home_id for n in state.npcs.values()}), 6)

        structures = {row.uid: row for row in skeleton.structures}
        rooms = {row.uid: row for row in skeleton.rooms}
        pieces = {row.uid: row for row in skeleton.pieces}
        parcels = {row.uid: row for row in skeleton.parcels}
        for npc in state.npcs.values():
            self.assertIn(npc.home_id, structures)
            self.assertEqual(structures[npc.home_id].function, "residence")
            self.assertIn(npc.home_room_id, rooms)
            self.assertEqual(rooms[npc.home_room_id].structure_plan_id, npc.home_id)
            self.assertIn(npc.bed_fixture_id, pieces)
            bed = self.registry.settlement_pieces[pieces[npc.bed_fixture_id].piece_id]
            self.assertIn("bed", bed.tags)
            self.assertIn(npc.property_id, parcels)
            self.assertIn(npc.home_id, parcels[npc.property_id].structure_ids)
            self.assertIn((npc.x, npc.y), set(rooms[npc.home_room_id].cells))
            self.assertTrue(physical.passable(WorldPos(npc.x, npc.y, 0), True))
            self.assertEqual(settlement.property_owners[npc.home_id], npc.uid)

    def test_work_bindings_match_existing_physical_workplaces(self):
        state, settlement, physical, binder = self._fixture()
        stats = binder.bind_settlement(settlement)
        skeleton = physical.skeleton_for(settlement.uid)
        structures = {row.uid: row for row in skeleton.structures}
        rooms = {row.uid: row for row in skeleton.rooms}
        by_occ = {npc.occupation: npc for npc in state.npcs.values()}

        for occupation in ("smith", "miner"):
            npc = by_occ[occupation]
            self.assertTrue(npc.workplace_id)
            self.assertEqual(structures[npc.workplace_id].function, "smithy")
            self.assertIn(npc.work_room_id, rooms)
            self.assertEqual(rooms[npc.work_room_id].structure_plan_id, npc.workplace_id)
        for occupation in ("farmer", "herder"):
            npc = by_occ[occupation]
            self.assertTrue(npc.workplace_id)
            self.assertIn(structures[npc.workplace_id].function, {"mill", "barn"})
        self.assertGreaterEqual(stats.workplaces_bound, 4)

    def test_binding_is_idempotent_and_does_not_teleport_valid_residents(self):
        state, settlement, physical, binder = self._fixture()
        first = binder.bind_settlement(settlement)
        snapshot = {
            npc.uid: (
                npc.home_id,
                npc.home_room_id,
                npc.bed_fixture_id,
                npc.workplace_id,
                npc.work_room_id,
                npc.property_id,
                npc.x,
                npc.y,
            )
            for npc in state.npcs.values()
        }
        second = binder.bind_settlement(settlement)
        after = {
            npc.uid: (
                npc.home_id,
                npc.home_room_id,
                npc.bed_fixture_id,
                npc.workplace_id,
                npc.work_room_id,
                npc.property_id,
                npc.x,
                npc.y,
            )
            for npc in state.npcs.values()
        }
        self.assertEqual(snapshot, after)
        self.assertGreater(first.repositioned, 0)
        self.assertEqual(second.repositioned, 0)

    def test_npc_ai_uses_bound_home_and_workplace_destinations(self):
        state, settlement, physical, binder = self._fixture()
        binder.bind_settlement(settlement)
        npc = next(row for row in state.npcs.values() if row.occupation == "smith")
        ai = NPCSystem(
            state,
            b"population-binding-test",
            SimpleNamespace(),
            world=None,
            building=None,
            lod=None,
        )
        ai.attach_settlement_population(physical, binder)

        npc.hunger = npc.thirst = npc.rest = 0
        npc.goal_score = 0
        npc.tasks = []
        ai._choose_goal_and_plan(npc, settlement, 600)
        self.assertEqual(npc.goal, "work")
        work = physical.destination_for(npc.workplace_id, npc.work_room_id)
        self.assertEqual((npc.tasks[0]["x"], npc.tasks[0]["y"]), (work.x, work.y))

        npc.rest = 100
        npc.goal_score = 0
        npc.tasks = []
        ai._choose_goal_and_plan(npc, settlement, 660)
        self.assertEqual(npc.goal, "rest")
        home = physical.destination_for(npc.home_id, npc.home_room_id)
        self.assertEqual((npc.tasks[0]["x"], npc.tasks[0]["y"]), (home.x, home.y))


if __name__ == "__main__":
    unittest.main()
