from types import SimpleNamespace
import unittest

from worldseed.systems.route_planner import RegionalRoutePlan, RoutePlanner
from worldseed.systems.ai import NPCSystem
from worldseed.persistence.validation import validate_sim_state
from worldseed.systems.state import ClaimMonumentState, FactionState, LivingWorldState, NPCState, SettlementState
from worldseed.systems.territory import TerritorySystem, monument_effective_control
from worldseed.ui.screens import faction_detail_screen, faction_screen


class StubWorld:
    def __init__(self, seed=b"territory-tests"):
        self.generator = SimpleNamespace(world_seed=seed)
        self.delta_source = SimpleNamespace()
        self.routegen_version = 3

    def is_passable(self, _pos):
        return True


class StubRegionPlanner:
    def plan(self, rx, ry, persist=True):
        return SimpleNamespace(
            route_value=82, crossing_value=48 + (abs(rx) % 3) * 8,
            defensibility=55 + (abs(ry) % 3) * 7, waters=(object(),),
            control_potential="crossroads", settlement_present=False,
            dominant_biome="grassland",
        )


def town(uid, rx, ry, faction):
    return SettlementState(
        uid=uid, name=uid, region_x=rx, region_y=ry,
        x=rx * 512 + 256, y=ry * 512 + 256, population=160,
        culture_id=f"culture:{faction}", religion_id="religion:test",
        faction_id=faction,
    )


class TerritoryClaimTests(unittest.TestCase):
    def make_state(self):
        state = LivingWorldState()
        state.factions["faction:a"] = FactionState("faction:a", "River League", "culture:a", prominence=75)
        state.factions["faction:b"] = FactionState("faction:b", "Iron March", "culture:b", prominence=70)
        a = town("settlement:a", 0, 0, "faction:a")
        b = town("settlement:b", 6, 0, "faction:b")
        state.settlements = {a.uid: a, b.uid: b}
        return state

    def plans(self):
        return [RegionalRoutePlan(
            "route:test", 3, "settlement:a", "settlement:b",
            region_path=[(x, 0) for x in range(7)], route_class="road",
        )]

    def test_generated_sites_are_deterministic_spaced_and_order_independent(self):
        world = StubWorld()
        first = TerritorySystem(world, self.make_state(), StubRegionPlanner())
        second = TerritorySystem(world, self.make_state(), StubRegionPlanner())
        rows_a = first.prepare_sites(self.plans())
        rows_b = second.prepare_sites(list(reversed(self.plans())))
        fingerprint_a = [(m.uid, m.region_x, m.region_y, m.x, m.y, m.monument_type) for m in rows_a]
        fingerprint_b = [(m.uid, m.region_x, m.region_y, m.x, m.y, m.monument_type) for m in rows_b]
        self.assertEqual(fingerprint_a, fingerprint_b)
        self.assertGreater(len(rows_a), 1)
        for i, left in enumerate(rows_a):
            for right in rows_a[i + 1:]:
                self.assertGreaterEqual(max(abs(left.region_x-right.region_x), abs(left.region_y-right.region_y)), 2)

    def test_capture_requires_sustained_presence_and_round_trips(self):
        state = self.make_state()
        territory = TerritorySystem(StubWorld(), state, StubRegionPlanner())
        monument = territory.prepare_sites(self.plans())[0]
        for day in range(4):
            territory.record_presence(monument.uid, "faction:a", 40)
            territory.daily_update((day + 1) * 1440)
            self.assertEqual(monument.controller_faction_id, "")
        territory.record_presence(monument.uid, "faction:a", 40)
        territory.daily_update(5 * 1440)
        self.assertEqual(monument.controller_faction_id, "faction:a")
        self.assertGreater(monument.supply_level, 0)
        restored = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.claim_monuments[monument.uid], monument)
        self.assertEqual(validate_sim_state(restored.to_dict()), [])
        broken = restored.to_dict()
        broken["claim_monuments"][monument.uid]["controller_faction_id"] = "faction:missing"
        self.assertIn(
            f"orphan claim monument controller: {monument.uid}->faction:missing",
            validate_sim_state(broken),
        )

    def test_monument_power_feeds_route_cost_control_and_damage_removes_it(self):
        state = self.make_state()
        world = StubWorld()
        region_planner = StubRegionPlanner()
        territory = TerritorySystem(world, state, region_planner)
        monument = territory.prepare_sites(self.plans())[0]
        monument.controller_faction_id = "faction:a"
        monument.supply_level = 100
        monument.garrison_strength = 100
        planner = RoutePlanner(world, state, region_planner, version=3)
        planner.attach_territory(territory)
        planner._active_plans = {self.plans()[0].uid: self.plans()[0]}
        planner.refresh_territory_control()
        token = f"{monument.region_x},{monument.region_y}"
        powered = state.factions["faction:a"].influence_regions[token]
        self.assertGreater(monument_effective_control(monument), 0)
        self.assertEqual(state.territory_control[token].controller_faction_id, "faction:a")
        territory.damage(monument.uid, 100, 10, "sabotage")
        planner.refresh_territory_control()
        self.assertEqual(monument_effective_control(monument), 0)
        self.assertLessEqual(state.factions["faction:a"].influence_regions.get(token, 0), powered)

    def test_guard_physically_travels_then_contributes_capture_presence(self):
        state = self.make_state()
        town_a = state.settlements["settlement:a"]
        monument = ClaimMonumentState("monument:near", "claim_stone", 0, 0, 1, 0, 90, 36, 1)
        state.claim_monuments[monument.uid] = monument
        guard = NPCState(
            "npc:guard", "Mara", 31, "guard", [], 0, 0, 0,
            settlement_id=town_a.uid, faction_id="faction:a", home_id="home", workplace_id="watch",
        )
        state.npcs[guard.uid] = guard
        territory = TerritorySystem(StubWorld(), state, StubRegionPlanner())
        ai = NPCSystem(state, b"guard-territory", SimpleNamespace(record=lambda *args, **kwargs: None))
        ai.attach_territory(territory)
        ai.attach_route_planner(SimpleNamespace(
            territory_target_for_settlement=lambda _uid: monument,
            patrol_destination_for_settlement=lambda _uid: None,
        ))
        ai.generate_plan(guard, town_a, 0, "guard")
        self.assertEqual(guard.tasks[-1]["action"], "territory_guard")
        ai.tick_update(5, SimpleNamespace(x=0, y=0, z=0))
        self.assertEqual((guard.x, guard.y), (1, 0))
        ai.decision_update(60, SimpleNamespace(x=0, y=0, z=0))
        territory.daily_update(1440)
        self.assertGreater(monument.capture_progress, 0)

    def test_faction_ui_is_observational_and_hides_undiscovered_monuments(self):
        state = self.make_state()
        known = ClaimMonumentState(
            "monument:known", "watch_monument", 1, 0, 600, 200, 110, 52, 2,
            controller_faction_id="faction:a", supply_level=70, garrison_strength=25,
        )
        hidden = ClaimMonumentState(
            "monument:hidden", "regional_stronghold", 2, 0, 1100, 200, 190, 90, 4,
            controller_faction_id="faction:a", supply_level=90, garrison_strength=80,
        )
        state.claim_monuments = {known.uid: known, hidden.uid: hidden}
        state.discovered_factions = ["faction:a"]
        state.discovered_sites = [known.uid]
        sim = SimpleNamespace(
            state=state,
            known_faction_ids=lambda: {"faction:a"},
            known_npc_ids=lambda: set(),
            known_site_ids=lambda: {known.uid},
            known_factions=lambda: [state.factions["faction:a"]],
            known_settlements=lambda: [],
            known_npcs=lambda: [],
        )
        before = state.to_dict()
        summary = faction_screen(sim)
        detail = faction_detail_screen(sim, "faction:a")
        self.assertIn("known claim monuments: 1", summary)
        self.assertIn("watch monument", detail)
        self.assertNotIn("regional stronghold", detail)
        self.assertEqual(state.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
