"""Authored carpets remain passive, bounded and save-compatible."""
from hashlib import sha256
from dataclasses import asdict
from types import SimpleNamespace
import unittest

from PIL import Image

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.validation import validate_sim_state
from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.interior_furnishing import furnish_plan, furniture_visual, is_bed_piece
from worldseed.systems.interior_state import InteriorActor, InteriorFurniture, InteriorPlan, InteriorRect, InteriorRoom
from worldseed.systems.interiors import InteriorSystem
from worldseed.systems.state import LivingWorldState


class DecorationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.visuals = VisualRegistry.load_default()

    def plan(self):
        return InteriorPlan('interior:building:decor', 'building:decor', 'door:decor', 0, 0, 0,
                            14000, 14000, function='residence', entry_x=7000, entry_y=13200,
                            rooms=[InteriorRoom('room:decor', 'Living room', InteriorRect(250,250,13500,13500))])

    def test_three_unique_transparent_flat_assets_have_no_bed_or_work_capacity(self):
        hashes = set()
        for name in ('hearth_rug','bedside_runner','hall_carpet'):
            uid = 'core:' + name + '_piece'
            definition = self.registry.settlement_pieces[uid]
            self.assertTrue(definition.passable)
            self.assertFalse(definition.blocks_sight)
            self.assertFalse(definition.workplace_role)
            self.assertNotIn('bed', definition.tags)
            self.assertFalse(is_bed_piece(uid))
            self.assertTrue(furniture_visual(uid)['flat'])
            path = self.visuals.resolve(self.visuals.ref('interiors', uid))
            self.assertEqual(path, self.visuals.resolve(self.visuals.ref('settlement_pieces', uid)))
            hashes.add(sha256(path.read_bytes()).hexdigest())
            with Image.open(path) as image:
                self.assertEqual(image.mode, 'RGBA')
                alpha = image.getchannel('A')
                self.assertEqual(alpha.getextrema()[0], 0)
                self.assertGreater(alpha.getextrema()[1], 16)
                self.assertEqual(alpha.getpixel((0,0)), 0)
        self.assertEqual(len(hashes), 3)

    def test_explicit_v1_upgrade_never_moves_saved_furniture_and_is_idempotent(self):
        plan = self.plan()
        plan.furnishing_version = 1
        old = InteriorFurniture('saved:table', 'core:large_table_piece', 3900,4400,1700,1100, 'owner')
        plan.furniture.append(old)
        before = asdict(old)
        state = LivingWorldState()
        state.interiors[plan.uid] = plan
        system = InteriorSystem(SimpleNamespace(state=state, registry=self.registry))
        system._furnish_prepared([plan])
        self.assertEqual(plan.furnishing_version, 2)
        self.assertEqual(asdict(old), before)
        self.assertTrue(any(f.piece_id == 'core:hearth_rug_piece' for f in plan.furniture))
        after = plan.to_dict()
        system._furnish_prepared([plan])
        self.assertEqual(plan.to_dict(), after)
        self.assertEqual(InteriorPlan.from_dict(after).to_dict(), after)
        errors = validate_sim_state(state.to_dict())
        self.assertFalse(errors, errors)

    def test_bedside_carpet_is_not_a_rest_action_or_sleeping_floor(self):
        plan = self.plan()
        rug = InteriorFurniture('rug', 'core:bedside_runner_piece',4000,4000,950,2300, solid=False)
        plan.furniture.append(rug)
        actor = InteriorActor(plan.uid,4400,5000)
        state = LivingWorldState()
        state.interiors[plan.uid] = plan
        state.interior_actors['player'] = actor
        system = InteriorSystem(SimpleNamespace(state=state, registry=self.registry))
        self.assertNotIn('You rest', system.interact('rug'))
        self.assertNotEqual(actor.action, 'resting')

    def test_outdoor_glow_has_dark_edge_and_follows_real_source_strength(self):
        import pygame
        from worldseed.presentation.weather_fx import WeatherFxRenderer
        from worldseed.systems.illumination import MAX_FIRE_RADIUS
        renderer = WeatherFxRenderer(pygame)
        radius = 16 * MAX_FIRE_RADIUS
        dark = renderer._glow_surface(radius, 0)
        weak = renderer._glow_surface(radius, 25)
        strong = renderer._glow_surface(radius, 100)
        self.assertEqual(tuple(dark.get_at((radius,radius)))[:3], (0,0,0))
        self.assertEqual(tuple(strong.get_at((0,0)))[:3], (0,0,0))
        self.assertGreater(strong.get_at((radius,radius)).r, weak.get_at((radius,radius)).r)
        self.assertGreater(strong.get_at((radius,radius)).r, strong.get_at((radius+radius//2,radius)).r)


if __name__ == '__main__':
    unittest.main()
