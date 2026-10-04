import unittest
from types import SimpleNamespace

from worldseed.systems.interior_state import InteriorPlan, InteriorActor, InteriorFurniture, InteriorRect
from worldseed.systems.interior_templates import interior_profiles, profile_for, rooms_for_profile
from worldseed.systems.interiors import build_interior, exit_reachable, interior_path, move_actor, position_clear
from worldseed.world.regional_plan import StructurePlanState, StructurePiecePlan
from tests import test_interiors


class BuildingInteriorProfileTests(unittest.TestCase):
    def structure(self, function="residence", form="cottage", uid="house:profile"):
        return StructurePlanState(uid, "settlement:plan", "core:house", function,
                                  footprint=[(x, y) for y in range(5) for x in range(5)],
                                  entrance=(2, 4), enclosed=True, building_form=form)

    def door(self, uid="house:profile"):
        return SimpleNamespace(uid=uid + ":door", property_id=uid, x=2, y=4, z=0, owner_uid="owner")

    def test_all_existing_enclosed_functions_have_specialized_profiles(self):
        expected = {"residence", "inn", "barracks", "outskirt_camp", "smithy", "workshop", "mill", "fishery", "bakery", "butcher", "weavery", "tannery", "pottery", "brewery", "mason_yard", "barn", "market", "clinic", "watchhouse", "shrine", "archive", "school"}
        actual = {f for p in interior_profiles() for f in p["functions"] if f != "*"}
        self.assertEqual(actual, expected)
        for function in expected:
            plan = build_interior(self.structure(function), self.door())
            self.assertEqual(plan.version, 3)
            self.assertNotEqual(plan.layout_id, "core:generic_enclosed")
            self.assertTrue(position_clear(plan, plan.entry_x, plan.entry_y))

    def test_six_house_forms_have_different_floorplans(self):
        layouts = set()
        profiles = [p for p in interior_profiles() if "residence" in p["functions"]]
        self.assertEqual(len(profiles), 6)
        for profile in profiles:
            plan = build_interior(self.structure(form=profile["forms"][0]), self.door())
            layouts.add((plan.layout_id, tuple((r.name, r.rect.x, r.rect.y, r.rect.w, r.rect.h) for r in plan.rooms)))
        self.assertEqual(len(layouts), 6)

    def test_every_profile_has_continuously_connected_rooms(self):
        for profile in interior_profiles():
            with self.subTest(profile=profile["id"]):
                plan = InteriorPlan("interior:connected", "connected", "door", 0, 0, 0, profile["width"], profile["height"])
                plan.rooms, plan.walls, (plan.entry_x, plan.entry_y) = rooms_for_profile(plan.uid, profile, plan.width, plan.height)
                for room in plan.rooms:
                    x, y = room.rect.x + room.rect.w // 2, room.rect.y + room.rect.h // 2
                    self.assertTrue(exit_reachable(plan, x, y), room.name)
                    path = interior_path(plan, (plan.entry_x, plan.entry_y), (x, y))
                    self.assertIsNotNone(path)

    def test_fixture_ids_are_not_minted_and_generation_order_is_stable(self):
        structure = self.structure("smithy")
        pieces = [StructurePiecePlan("forge:original", structure.uid, "core:forge_piece", 1, 1, role="fixture"), StructurePiecePlan("chest:original", structure.uid, "core:house_chest_piece", 3, 3, role="fixture")]
        plan = build_interior(structure, self.door(), pieces=pieces)
        self.assertEqual({f.uid for f in plan.furniture}, {p.uid for p in pieces})
        self.assertEqual({f.source_uid for f in plan.furniture}, {p.uid for p in pieces})
        self.assertEqual(plan.to_dict(), build_interior(structure, self.door(), pieces=list(reversed(pieces))).to_dict())

    def test_layout_identity_does_not_depend_on_other_buildings(self):
        structure = self.structure(form="modded_form")
        before = profile_for(structure)["id"]
        profile_for(self.structure(uid="unrelated:building"))
        self.assertEqual(profile_for(structure)["id"], before)

    def test_unknown_enclosed_function_uses_valid_fallback(self):
        plan = build_interior(self.structure("mod:observatory"), self.door())
        self.assertEqual(plan.layout_id, "core:generic_enclosed")
        self.assertTrue(exit_reachable(plan, plan.rooms[1].rect.x + 1500, plan.rooms[1].rect.y + 1500))

    def test_saved_v1_defaults_do_not_request_a_new_template(self):
        payload = InteriorPlan("interior:old", "old", "door", 3, 4, 0, 9000, 9000).to_dict()
        payload.pop("layout_id")
        old = InteriorPlan.from_dict(payload)
        self.assertEqual(old.version, 1)
        self.assertEqual(old.layout_id, "")
        self.assertEqual((old.width, old.height), (9000, 9000))

    def test_furniture_cannot_be_used_through_a_partition(self):
        from worldseed.systems.interiors import InteriorSystem
        plan = InteriorPlan("interior:wall", "wall", "door", 0, 0, 0, 6000, 6000,
                            walls=[InteriorRect(2900, 0, 180, 6000)])
        furniture = InteriorFurniture("bed", "core:single_bed_piece", 3200, 2000, 950, 1450)
        actor = InteriorActor(plan.uid, 2600, 2500)
        self.assertFalse(InteriorSystem._furniture_reachable(plan, actor, furniture, 1500))

    def test_source_fixture_load_does_not_add_new_economic_stations(self):
        structure = self.structure("workshop")
        pieces = [StructurePiecePlan("fixture:" + str(i), structure.uid, "core:carpenter_bench_piece", i, i, role="fixture") for i in range(12)]
        plan = build_interior(structure, self.door(), pieces=pieces)
        self.assertEqual({f.uid for f in plan.furniture}, {p.uid for p in pieces})
        self.assertEqual(len(plan.furniture), len(pieces))
        for room in plan.rooms:
            self.assertTrue(exit_reachable(plan, room.rect.x + room.rect.w // 2, room.rect.y + room.rect.h - 400))

    def test_live_workshop_entry_and_legacy_plan_preservation(self):
        test_interiors.InteriorPortalTests.setUpClass()
        sim, house, door = test_interiors.InteriorPortalTests().fixture()
        house.function = "smithy"
        door.locked = False
        original_stocks = {uid: dict(t.stocks) for uid, t in sim.state.settlements.items()}
        self.assertIn("You enter", sim.interiors.enter(door.uid))
        new = sim.interiors.current_plan()
        self.assertEqual(new.layout_id, "core:smithy")
        new.version = 1
        new.layout_id = ""
        new.furniture[0].x += 127
        before = new.to_dict()
        self.assertIs(sim.interiors._prepare(door), new)
        self.assertEqual(new.to_dict(), before)
        self.assertEqual(original_stocks, {uid: dict(t.stocks) for uid, t in sim.state.settlements.items()})
        house.destroyed = True
        self.assertIsNone(sim.interiors._prepare(door))


if __name__ == "__main__":
    unittest.main()
