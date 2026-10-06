"""Semantic room slots conserve source fixtures and leave usable circulation."""
import unittest

from worldseed.core.rng import hash_u64
from worldseed.systems.interior_furnishing import (
    fixture_slot_candidates, furnish_plan, furnishing_catalog, furniture_base_piece,
    furniture_dimensions, furniture_visual, place_source_fixture, room_furnishing_style,
    slot_placement_clear, is_bed_piece,
)
from worldseed.systems.interior_state import (
    InteriorActor, InteriorFurniture, InteriorPlan, InteriorRect, InteriorRoom, InteriorStair,
)
from worldseed.systems.interiors import InteriorSystem, exit_reachable, position_clear


class FurnishingSlotTests(unittest.TestCase):
    def room_plan(self, name="Living room"):
        return InteriorPlan("interior:slots", "building:slots", "door:slots", 0, 0, 0,
                            14000, 14000, function="residence", entry_x=7000, entry_y=13200,
                            rooms=[InteriorRoom("room:slots", name, InteriorRect(250, 250, 13500, 13500))])

    def test_role_catalog_is_explicit_finite_and_keeps_24_prop_budget(self):
        catalog = furnishing_catalog()
        self.assertEqual(catalog["version"], 2)
        self.assertEqual(catalog["maximum_additions"], 24)
        self.assertTrue(catalog["fixture_roles"])
        plan = self.room_plan("Workshop")
        candidates = list(fixture_slot_candidates(plan, "core:forge_piece"))
        self.assertLessEqual(len(candidates), len(catalog["fixture_anchors"]))
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertTrue(all(slot in catalog["fixture_anchors"] for _, slot, _, _ in candidates))

    def test_bed_and_workstation_select_semantic_room_and_wall_slot(self):
        plan = self.room_plan()
        plan.width = 26000
        plan.rooms = [InteriorRoom("room:living", "Living room", InteriorRect(250, 250, 8500, 12000)),
                      InteriorRoom("room:work", "Forge room", InteriorRect(8750, 250, 8500, 12000)),
                      InteriorRoom("room:bed", "Bedroom", InteriorRect(17250, 250, 8500, 12000))]
        bed = place_source_fixture(plan, "core:single_bed_piece", "source:bed", source_uid="source:bed")
        forge = place_source_fixture(plan, "core:forge_piece", "source:forge", source_uid="source:forge")
        self.assertIsNotNone(bed)
        self.assertIsNotNone(forge)
        self.assertTrue(plan.rooms[2].rect.contains(bed.x, bed.y))
        self.assertTrue(plan.rooms[1].rect.contains(forge.x, forge.y))
        self.assertEqual(bed.y, plan.rooms[2].rect.y + 425)
        self.assertEqual(forge.y, plan.rooms[1].rect.y + 425)
        self.assertEqual((bed.uid, bed.source_uid), ("source:bed", "source:bed"))
        self.assertEqual((forge.uid, forge.source_uid), ("source:forge", "source:forge"))
        plan.furniture.append(bed)
        before = plan.to_dict()
        self.assertIsNone(place_source_fixture(plan, "core:single_bed_piece", "source:bed"))
        self.assertEqual(plan.to_dict(), before)

    def test_chairs_have_actual_table_or_desk_cluster_not_arbitrary_coordinates(self):
        plan = self.room_plan()
        furnish_plan(plan)
        table = next(f for f in plan.furniture if furniture_base_piece(f.piece_id) == "core:large_table_piece")
        seats = [f for f in plan.furniture if furniture_base_piece(f.piece_id) == "core:chair_piece"]
        self.assertEqual(len(seats), 2)
        south = next(f for f in seats if f.uid.endswith(":chair"))
        west = next(f for f in seats if f.uid.endswith(":chair_side"))
        self.assertEqual(south.y, table.y + table.h + 450)
        self.assertEqual(south.x + south.w // 2, table.x + table.w // 2)
        self.assertEqual(west.x + west.w + 450, table.x)
        self.assertEqual(west.y + west.h // 2, table.y + table.h // 2)
        for furniture in plan.furniture:
            self.assertIsNotNone(InteriorSystem.fixture_use_position(plan, furniture))

    def test_empty_storeroom_never_receives_unattached_chairs_or_tables(self):
        plan = self.room_plan("Storeroom")
        furnish_plan(plan)
        bases = {furniture_base_piece(f.piece_id) for f in plan.furniture}
        self.assertIn("core:wall_shelf_piece", bases)
        self.assertNotIn("core:large_table_piece", bases)
        self.assertNotIn("core:chair_piece", bases)
        self.assertNotIn("core:stool_piece", bases)
        self.assertEqual(room_furnishing_style(plan.rooms[0], plan), "store")

    def test_bedside_carpet_is_flat_nonblocking_and_aligned_with_actual_bed(self):
        plan = self.room_plan("Bedroom")
        bed = place_source_fixture(plan, "core:single_bed_piece", "source:bed", source_uid="source:bed")
        plan.furniture.append(bed)
        furnish_plan(plan)
        runner = next(f for f in plan.furniture if f.piece_id == "core:bedside_runner_piece")
        self.assertEqual(runner.x, bed.x + bed.w + 450)
        # The taller runner shares the bed's head edge rather than clipping
        # the wall to force a centre alignment.
        self.assertEqual(runner.y, bed.y)
        self.assertFalse(runner.solid)
        self.assertTrue(furniture_visual(runner.piece_id)["flat"])
        self.assertTrue(position_clear(plan, runner.x + runner.w // 2, runner.y + runner.h // 2))
        self.assertFalse(runner.source_uid)
        self.assertEqual(furniture_dimensions(runner.piece_id), (950, 2300))
        self.assertFalse(is_bed_piece(runner.piece_id))
        self.assertTrue(is_bed_piece("core:linen_cot_bed_piece"))
        self.assertTrue(is_bed_piece("core:canopy_bed_piece"))
        self.assertFalse(is_bed_piece("mod:bedroom_decoration"))

    def test_room_order_and_unrelated_rng_calls_cannot_change_slot_assignments(self):
        a = self.room_plan()
        a.rooms = [InteriorRoom("room:a", "Living room", InteriorRect(250, 250, 6000, 12000)),
                   InteriorRoom("room:b", "Bedroom", InteriorRect(7000, 250, 6750, 12000))]
        b = InteriorPlan.from_dict(a.to_dict())
        b.rooms.reverse()
        furnish_plan(a)
        hash_u64(b"unrelated-test-domain", "unrelated-consumer", 8934)
        furnish_plan(b)
        self.assertEqual([f.__dict__ if hasattr(f, "__dict__") else (f.uid, f.piece_id, f.x, f.y, f.w, f.h)
                          for f in a.furniture],
                         [f.__dict__ if hasattr(f, "__dict__") else (f.uid, f.piece_id, f.x, f.y, f.w, f.h)
                          for f in b.furniture])
        self.assertEqual(list(fixture_slot_candidates(a, "core:house_chest_piece")),
                         list(fixture_slot_candidates(b, "core:house_chest_piece")))

    def test_saved_geometry_and_actor_stair_escape_are_preserved(self):
        plan = self.room_plan()
        source = InteriorFurniture("source:saved", "core:house_chest_piece", 2400, 750, 1150, 750,
                                   source_uid="source:saved")
        plan.furniture.append(source)
        plan.stairs.append(InteriorStair("stairs:saved", 8500, 9500, 1400, 1900, "interior:up", 4000, 5000))
        actor = InteriorActor(plan.uid, 9000, 12200)
        original = source.x, source.y, source.w, source.h, source.source_uid
        furnish_plan(plan, actors=[actor])
        self.assertEqual((source.x, source.y, source.w, source.h, source.source_uid), original)
        self.assertTrue(position_clear(plan, actor.x, actor.y))
        self.assertTrue(exit_reachable(plan, actor.x, actor.y))
        self.assertTrue(position_clear(plan, plan.entry_x, plan.entry_y))
        for f in plan.furniture[1:]:
            self.assertFalse(f.rect.overlaps(plan.stairs[0].rect))
            self.assertFalse(f.rect.contains(actor.x, actor.y))

    def test_unusable_blocked_wall_slot_is_rejected_without_mutation(self):
        plan = self.room_plan()
        blocked = InteriorFurniture("candidate", "core:cupboard_piece", 1000, 1000, 1500, 800)
        plan.walls.extend([InteriorRect(750, 750, 250, 1300), InteriorRect(2500, 750, 250, 1300),
                           InteriorRect(750, 750, 2000, 250), InteriorRect(750, 1800, 2000, 250)])
        before = plan.to_dict()
        self.assertFalse(slot_placement_clear(plan, blocked))
        self.assertEqual(plan.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
