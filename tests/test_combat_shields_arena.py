import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.combat import CombatSystem
from worldseed.systems.processing import ProcessingSystem
from worldseed.systems.projectiles import ProjectileSystem
from worldseed.systems.resources import FeatureView
from worldseed.systems.state import CarcassState, CreatureState, LivingWorldState
from worldseed.systems.test_arena import TestArenaSystem
from worldseed.ui.startup import SKILL_DEFS


class _Terrain:
    def __init__(self, blocked=False):
        self.passable = not blocked
        self.blocks_sight = blocked
        self.tags = ("soil",)
        self.name = "Wall" if blocked else "Grass"


class _Tile:
    def __init__(self, blocked=False):
        self.terrain_id = "core:rock" if blocked else "core:grass"
        self.terrain = _Terrain(blocked)


class _World:
    def __init__(self, blocked=None):
        self.blocked = set(blocked or ())

    def tile_at(self, pos):
        return _Tile((pos.x, pos.y, pos.z) in self.blocked)

    def is_passable(self, pos):
        return (pos.x, pos.y, pos.z) not in self.blocked


class _Resources:
    def __init__(self, feature_id="", at=None):
        self.feature_id = feature_id
        self.at = set(at or ())

    def blocks_movement(self, pos):
        return False

    def feature_at(self, pos):
        if self.feature_id and (pos.x, pos.y, pos.z) in self.at:
            return FeatureView(self.feature_id)
        return None


class _Building:
    def structure_at(self, pos):
        return None

    def passable(self, pos, world_passable=True):
        return world_passable

    def blocks_sight(self, pos):
        return False


class CombatShieldArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = ContentRegistry.load(DATA_DIR)

    def combat(self, shield_id=""):
        state = LivingWorldState()
        if shield_id:
            state.player_equipment["offhand"] = shield_id
        state.player_facing_dx = 1
        state.player_facing_dy = 0
        return state, CombatSystem(state, self.reg, b"shield-tests")

    def test_six_shields_are_distinct_craftable_offhand_profiles(self):
        ids = (
            "core:rawhide_buckler",
            "core:wicker_shield",
            "core:wood_round_shield",
            "core:hide_kite_shield",
            "core:iron_heater_shield",
            "core:steel_tower_shield",
        )
        types = set()
        profiles = set()
        for iid in ids:
            item = self.reg.items[iid]
            self.assertIn("shield", item.tags)
            self.assertEqual(item.equip_slot, "offhand")
            self.assertIn(iid, self.reg.recipes)
            self.assertTrue(item.shield_type)
            self.assertGreater(item.shield_melee_coverage, 0)
            self.assertGreater(item.shield_ranged_coverage, 0)
            self.assertGreater(item.shield_block, 0)
            self.assertTrue(item.shield_body_coverage)
            types.add(item.shield_type)
            profiles.add((item.shield_melee_coverage, item.shield_ranged_coverage, item.shield_block, item.shield_stability))
        self.assertEqual(len(types), 6)
        self.assertEqual(len(profiles), 6)

    def test_shield_coverage_respects_front_side_rear_orientation(self):
        state, combat = self.combat("core:wood_round_shield")
        state.player_skills["shield"] = 4
        front = combat.shield_coverage_chance("torso", "melee", 100, 1, 0)
        side = combat.shield_coverage_chance("torso", "melee", 100, 0, 1)
        rear = combat.shield_coverage_chance("torso", "melee", 100, -1, 0)
        self.assertGreater(front, side)
        self.assertGreater(side, rear)

    def test_tower_has_more_ranged_torso_coverage_than_buckler(self):
        buckler_state, buckler = self.combat("core:rawhide_buckler")
        tower_state, tower = self.combat("core:steel_tower_shield")
        buckler_state.player_skills["shield"] = 0
        tower_state.player_skills["shield"] = 0
        b = buckler.shield_coverage_chance("torso", "ranged", 100, 1, 0)
        t = tower.shield_coverage_chance("torso", "ranged", 100, 1, 0)
        self.assertGreater(t, b)

    def test_guarding_improves_coverage_and_shield_block_costs_stamina(self):
        state, combat = self.combat("core:steel_tower_shield")
        state.player_skills["shield"] = 12
        unguarded = combat.shield_coverage_chance("torso", "ranged", 100, 1, 0)
        state.player_guarding = True
        guarded = combat.shield_coverage_chance("torso", "ranged", 100, 1, 0)
        self.assertGreaterEqual(guarded, unguarded)
        found = None
        for turn in range(1, 80):
            remaining, text, drain = combat.shield_defend(18, "torso", "ranged", "pierce", turn, 100, 1, 0, "arena:arrow")
            if text:
                found = (remaining, text, drain)
                break
        self.assertIsNotNone(found)
        self.assertLess(found[0], 18)
        self.assertGreater(found[2], 0)
        self.assertIn("Steel Tower Shield", found[1])

    def test_resolve_player_hit_uses_active_shield_before_wound_resolution(self):
        state, combat = self.combat("core:steel_tower_shield")
        state.player_skills["shield"] = 20
        state.player_guarding = True
        vitals = Vitals()
        before = vitals.hp
        blocked = False
        for turn in range(1, 100):
            vitals.hp = before
            vitals.stamina = 100
            state.player_wounds.clear()
            msg = combat.resolve_player_hit(vitals, "torso", 10, "pierce", "ranged", turn, "Arena arrow", "arena:arrow", 1, 0)
            if "shield" in msg.lower():
                blocked = True
                self.assertGreaterEqual(vitals.hp, before - 4)
                break
        self.assertTrue(blocked)

    def test_legacy_state_backfills_shield_skill_and_combat_state_roundtrips(self):
        old = LivingWorldState().to_dict()
        old["player_skills"].pop("shield", None)
        old.pop("player_facing_dx", None)
        old.pop("player_facing_dy", None)
        old.pop("player_guarding", None)
        restored = LivingWorldState.from_dict(old)
        self.assertEqual(restored.player_skills["shield"], 0)
        self.assertEqual((restored.player_facing_dx, restored.player_facing_dy), (0, 1))
        state = LivingWorldState()
        state.player_facing_dx = -1
        state.player_facing_dy = 0
        state.player_guarding = True
        state.creatures["c"] = CreatureState("c", "core:deer", 1, 2, 0, 20, embedded_projectiles=[{"item_id": "core:wood_arrow", "part": "torso"}])
        state.carcasses["k"] = CarcassState("k", "core:deer", 1, 2, 0, 10, source_uid="c", embedded_items={"core:wood_arrow": 2})
        again = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual((again.player_facing_dx, again.player_facing_dy), (-1, 0))
        self.assertTrue(again.player_guarding)
        self.assertEqual(again.creatures["c"].embedded_projectiles[0]["item_id"], "core:wood_arrow")
        self.assertEqual(again.carcasses["k"].embedded_items["core:wood_arrow"], 2)

    def test_character_creation_exposes_shield_skill(self):
        self.assertIn("shield", {key for key, _, _ in SKILL_DEFS})

    def test_projectile_preview_models_partial_cover_and_hard_blockers(self):
        tree_id = next(f.id for f in self.reg.resources.values() if "tree" in f.tags)
        world = _World()
        resources = _Resources(tree_id, {(2, 0, 0)})
        projectiles = ProjectileSystem(LivingWorldState(), self.reg, b"projectile", world, resources, _Building())
        preview = projectiles.preview(WorldPos(0, 0, 0), WorldPos(5, 0, 0))
        self.assertIsNone(preview.blocked_at)
        self.assertGreater(preview.cover_penalty, 0)
        self.assertTrue(preview.cover_notes)

        hard = ProjectileSystem(LivingWorldState(), self.reg, b"projectile-hard", _World({(3, 0, 0)}), _Resources(), _Building())
        blocked = hard.preview(WorldPos(0, 0, 0), WorldPos(5, 0, 0))
        self.assertEqual(blocked.blocked_at, WorldPos(3, 0, 0))

    def test_projectile_miss_landing_is_deterministic_and_bounded(self):
        system = ProjectileSystem(LivingWorldState(), self.reg, b"scatter", _World(), _Resources(), _Building())
        bow = self.reg.items["core:short_bow"]
        origin = WorldPos(0, 0, 0)
        target = WorldPos(5, 0, 0)
        a = system.miss_landing(origin, target, bow, 41, "deer")
        b = system.miss_landing(origin, target, bow, 41, "deer")
        self.assertEqual(a, b)
        self.assertLessEqual(abs(a.x-origin.x)+abs(a.y-origin.y), bow.range+2)

    def test_arena_creatures_do_not_modify_ecology_authority(self):
        state = LivingWorldState()
        arena = TestArenaSystem(state, self.reg, _World(), _Resources(), _Building())
        cohorts_before = dict(state.cohorts)
        msg = arena.spawn_creature(WorldPos(0, 0, 0), "core:boar", 2, 0)
        creature = next(iter(state.creatures.values()))
        self.assertTrue(creature.uid.startswith("arena:"))
        self.assertTrue(creature.notable)
        self.assertEqual(creature.cohort_key, "")
        self.assertEqual(state.cohorts, cohorts_before)
        self.assertIn("boar", msg.lower())

    def test_arena_changes_stats_injuries_and_loads_oriented_presets(self):
        state = LivingWorldState()
        arena = TestArenaSystem(state, self.reg, _World(), _Resources(), _Building())
        inv = Inventory()
        vitals = Vitals()
        arena.set_stat("skill", "shield", 17)
        self.assertEqual(state.player_skills["shield"], 17)
        arena.injury(vitals, "arm_fracture")
        self.assertTrue(state.player_wounds[-1]["fracture"])
        arena.heal(vitals)
        self.assertFalse(state.player_wounds)
        msg = arena.preset("ranged", WorldPos(0, 0, 0), inv, vitals)
        self.assertIn("ranged lane", msg.lower())
        self.assertGreaterEqual(inv.count("core:wood_arrow"), 30)
        self.assertGreaterEqual(len(state.creatures), 4)
        positions={(c.x,c.y) for c in state.creatures.values()}
        self.assertTrue(any(abs(x)+abs(y)>=7 for x,y in positions))

    def test_embedded_projectiles_are_recovered_during_processing(self):
        state = LivingWorldState()
        state.carcasses["c"] = CarcassState(
            "c", "core:deer", 0, 0, 0, 0,
            embedded_items={"core:wood_arrow": 2, "core:wooden_spear": 1},
        )
        processing = ProcessingSystem(state, self.reg, _Building())
        inv = Inventory()
        ok, msg, minutes = processing.process_carcass("c", "recover", inv, 0, 10)
        self.assertTrue(ok)
        self.assertEqual(inv.count("core:wood_arrow"), 2)
        self.assertEqual(inv.count("core:wooden_spear"), 1)
        self.assertFalse(state.carcasses["c"].embedded_items)
        self.assertGreater(minutes, 0)
        self.assertIn("extract", msg.lower())


if __name__ == "__main__":
    unittest.main()
