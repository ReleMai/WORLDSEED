"""Continuous furnishing proportions, safe upgrades and deterministic room sets."""
import unittest
from types import SimpleNamespace

from worldseed.systems.interior_furnishing import (
    furnish_plan, furniture_dimensions, furniture_visual, furnishing_catalog,
)
from worldseed.systems.interior_state import InteriorActor, InteriorFurniture, InteriorPlan, InteriorRect
from worldseed.systems.interior_templates import interior_profiles, rooms_for_profile
from worldseed.systems.interiors import exit_reachable, interior_path, position_clear


class Dev51FurnishingTests(unittest.TestCase):
    def plan(self, profile_id="core:cottage_front"):
        profile = next(p for p in interior_profiles() if p["id"] == profile_id)
        plan = InteriorPlan("interior:home", "home", "door", 2, 3, 0,
                            profile["width"], profile["height"], function="residence")
        plan.rooms, plan.walls, (plan.entry_x, plan.entry_y) = rooms_for_profile(
            plan.uid, profile, plan.width, plan.height)
        return plan

    def test_deterministic_idempotent_and_bounded(self):
        a, b = self.plan(), self.plan()
        count = furnish_plan(a)
        furnish_plan(b)
        self.assertGreaterEqual(count, 8)
        self.assertLessEqual(count, furnishing_catalog()["maximum_additions"])
        self.assertEqual(a.to_dict(), b.to_dict())
        before = a.to_dict()
        self.assertEqual(furnish_plan(a), 0)
        self.assertEqual(a.to_dict(), before)

    def test_all_profiles_have_safe_circulation_and_no_economic_duplicates(self):
        for profile in interior_profiles():
            with self.subTest(profile=profile["id"]):
                plan = self.plan(profile["id"])
                furnish_plan(plan)
                self.assertTrue(position_clear(plan, plan.entry_x, plan.entry_y))
                self.assertTrue(plan.furniture)
                for index, furniture in enumerate(plan.furniture):
                    self.assertFalse(furniture.source_uid)
                    self.assertNotIn("bed", furniture.piece_id)
                    self.assertFalse(any(furniture.rect.overlaps(other.rect)
                                         for other in plan.furniture[index + 1:]))
                    self.assertFalse(any(furniture.rect.overlaps(wall) for wall in plan.walls))
                    # An interactable approach exists on at least one edge.
                    approaches = [(furniture.x - 225, furniture.y + furniture.h // 2),
                                  (furniture.x + furniture.w + 225, furniture.y + furniture.h // 2),
                                  (furniture.x + furniture.w // 2, furniture.y - 225),
                                  (furniture.x + furniture.w // 2, furniture.y + furniture.h + 225)]
                    self.assertTrue(any(position_clear(plan, *point) and exit_reachable(plan, *point)
                                        for point in approaches), furniture.uid)
                for room in plan.rooms:
                    # The base grammar's doorway-side centre stays connected.
                    probes = [(room.rect.x + room.rect.w // 2, room.rect.y + room.rect.h - 400),
                              (room.rect.x + room.rect.w // 2, room.rect.y + room.rect.h // 2),
                              (room.rect.x + 400, room.rect.y + room.rect.h // 2)]
                    self.assertTrue(any(position_clear(plan, *p) and exit_reachable(plan, *p) for p in probes), room.name)

    def test_saved_fixtures_and_walls_are_not_moved(self):
        plan = self.plan()
        source = InteriorFurniture("source:bed", "core:single_bed_piece", 700, 800, 950, 1450,
                                   source_uid="source:bed")
        plan.furniture.append(source)
        original = source.x, source.y, source.w, source.h, source.source_uid
        walls = [(r.x, r.y, r.w, r.h) for r in plan.walls]
        furnish_plan(plan)
        self.assertEqual((source.x, source.y, source.w, source.h, source.source_uid), original)
        self.assertEqual([(r.x, r.y, r.w, r.h) for r in plan.walls], walls)

    def test_occupied_legacy_plan_and_stairs_remain_clear(self):
        plan = self.plan("core:house_gallery")
        actor = InteriorActor(plan.uid, 5500, 4000)
        # Stairs are an optional additive state field; pass a plain read model
        # here so this test does not depend on a particular connector class.
        stair = SimpleNamespace(rect=InteriorRect(7500, 1100, 1400, 1900))
        wrapper = SimpleNamespace(**{key: getattr(plan, key) for key in
                                  ("uid", "width", "height", "entry_x", "entry_y", "rooms", "walls", "furniture", "owner_uid", "function")},
                                  stairs=[stair])
        furnish_plan(wrapper, actors=[actor])
        for furniture in plan.furniture:
            self.assertFalse(furniture.rect.contains(actor.x, actor.y))
            self.assertFalse(furniture.rect.overlaps(stair.rect))
        self.assertTrue(exit_reachable(plan, actor.x, actor.y))

    def test_native_visual_canvas_separates_upright_height_from_collision(self):
        w, h = furniture_dimensions("core:wall_shelf_piece")
        art = furniture_visual("core:wall_shelf_piece")
        self.assertGreater(w, h)
        self.assertGreater(art["height_ratio"] * h, h)
        self.assertTrue(furniture_visual("core:woven_rug_piece")["flat"])

    def test_inn_and_market_have_compact_rear_rooms_and_service_gallery(self):
        for uid in ("core:inn_tavern", "core:market"):
            plan = self.plan(uid)
            self.assertTrue(plan.rooms[-1].uid.endswith(":gallery"))
            for room in plan.rooms[1:-1]:
                self.assertLess(max(room.rect.w, room.rect.h) / min(room.rect.w, room.rect.h), 2.4)
                self.assertIsNotNone(interior_path(plan, (plan.entry_x, plan.entry_y),
                                                  (room.rect.x + room.rect.w // 2,
                                                   room.rect.y + room.rect.h // 2)))
            furnish_plan(plan)
            populated = {room.uid for room in plan.rooms if any(room.rect.contains(
                f.x + f.w // 2, f.y + f.h // 2) for f in plan.furniture)}
            self.assertTrue({r.uid for r in plan.rooms[:-1]} <= populated)


if __name__ == "__main__":
    unittest.main()
