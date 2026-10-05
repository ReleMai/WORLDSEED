"""Authored furnishing families preserve functional fixtures and real stock."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from PIL import Image

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.persistence.validation import validate_sim_state
from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.building_variants import catalog as building_catalog
from worldseed.systems.container_profiles import container_profile
from worldseed.systems.interior_floors import prepare_floors
from worldseed.systems.interior_furnishing import (
    furniture_base_piece, furniture_dimensions, furniture_variant,
    furniture_variant_catalog,
)
from worldseed.systems.interior_state import InteriorActor, InteriorFurniture, InteriorPlan, InteriorRect, InteriorRoom
from worldseed.systems.interior_storage import bind_storage
from worldseed.systems.interior_templates import profile_for
from worldseed.systems.interiors import InteriorSystem, build_interior, position_clear
from worldseed.systems.state import ContainerState, LivingWorldState
from worldseed.systems.workshops import STATION_PIECE_ALIASES, recipes_for_station
from worldseed.world.regional_plan import StructurePiecePlan


class FurnitureContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.visuals = VisualRegistry.load_default()

    def structure(self, variant=None, size=5):
        variant = variant or next(row for row in building_catalog() if row['asset'] == 'merchant_villa')
        structure = SimpleNamespace(uid='building:content:' + variant['asset'],
                                    function=variant['function'], variant_id=variant['id'],
                                    building_form='rectangular', enclosed=True,
                                    footprint=[(x, y) for y in range(size) for x in range(size)])
        door = SimpleNamespace(uid=structure.uid + ':door', x=size // 2, y=size - 1,
                               z=0, owner_uid='player')
        return structure, door

    def test_twenty_unique_furniture_definitions_preserve_base_functions_and_footprints(self):
        rows = furniture_variant_catalog()
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({row['id'] for row in rows}), 20)
        self.assertEqual(len({row['asset'] for row in rows}), 20)
        for row in rows:
            with self.subTest(piece=row['id']):
                actual = asdict(self.registry.settlement_pieces[row['id']])
                base = asdict(self.registry.settlement_pieces[row['base_piece']])
                for key in base:
                    if key not in {'id', 'name', 'tags'}:
                        self.assertEqual(actual[key], base[key], key)
                self.assertEqual(set(actual['tags']) - {'dev52_furniture_variant'}, set(base['tags']))
                self.assertEqual(furniture_dimensions(row['id']), furniture_dimensions(row['base_piece']))
                self.assertEqual(furniture_base_piece(row['id']), row['base_piece'])

    def test_all_twenty_have_unique_authored_transparent_silhouettes(self):
        paths, contents = set(), set()
        for row in furniture_variant_catalog():
            path = self.visuals.resolve(self.visuals.ref('interiors', row['id']))
            self.assertIsNotNone(path, row['id'])
            self.assertTrue(path.is_file(), row['id'])
            self.assertNotIn(path, paths); paths.add(path)
            contents.add(sha256(path.read_bytes()).hexdigest())
            with Image.open(path) as source:
                self.assertEqual(source.mode, 'RGBA', row['id'])
                alpha = source.getchannel('A')
                self.assertEqual(alpha.getextrema()[0], 0)
                self.assertGreater(alpha.getextrema()[1], 16)
                for point in ((0, 0), (source.width - 1, 0),
                              (0, source.height - 1), (source.width - 1, source.height - 1)):
                    self.assertEqual(alpha.getpixel(point), 0, row['id'])
        self.assertEqual(len(contents), 20)

    def test_six_workstation_styles_resolve_real_station_recipes(self):
        rows = [row for row in furniture_variant_catalog() if row['id'] in STATION_PIECE_ALIASES]
        self.assertEqual(len(rows), 6)
        for row in rows:
            sid = STATION_PIECE_ALIASES[row['id']]
            self.assertEqual(sid, STATION_PIECE_ALIASES[row['base_piece']])
            self.assertIn(sid, self.registry.structures)
            recipes = recipes_for_station(self.registry, sid)
            self.assertTrue(recipes, row['id'])
            self.assertTrue(all(recipe.station == sid for recipe in recipes))

    def test_selection_is_order_independent_and_never_restyles_explicit_pieces(self):
        rows = furniture_variant_catalog()
        originals = [(row['base_piece'], 'fixture:' + row['asset']) for row in rows]
        first = {uid: furniture_variant(base, uid) for base, uid in originals}
        second = {uid: furniture_variant(base, uid) for base, uid in reversed(originals)}
        self.assertEqual(first, second)
        for row in rows:
            self.assertEqual(furniture_variant(row['id'], 'different:identity'), row['id'])
        self.assertEqual(furniture_variant('mod:astrolabe_piece', 'fixture:mod'), 'mod:astrolabe_piece')

    def test_preparing_source_fixtures_preserves_original_ids_and_workstation_authority(self):
        variant = next(row for row in building_catalog() if row['asset'] == 'foundry_hall')
        structure, door = self.structure(variant)
        bases = sorted({row['base_piece'] for row in furniture_variant_catalog()
                        if row['id'] in STATION_PIECE_ALIASES})
        pieces = [StructurePiecePlan('original:' + base, structure.uid, base, 1, 1, role='fixture')
                  for base in bases]
        first = build_interior(structure, door, pieces=pieces)
        second = build_interior(structure, door, pieces=list(reversed(pieces)))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual({f.uid for f in first.furniture}, {p.uid for p in pieces})
        self.assertEqual({f.source_uid for f in first.furniture}, {p.uid for p in pieces})
        originals = {p.uid: p.piece_id for p in pieces}
        for fixture in first.furniture:
            self.assertEqual(furniture_base_piece(fixture.piece_id), originals[fixture.source_uid])
            self.assertEqual(STATION_PIECE_ALIASES[fixture.piece_id], STATION_PIECE_ALIASES[originals[fixture.source_uid]])

    def test_new_version_four_plans_pin_styles_and_cover_seven_floors_and_three_walls(self):
        floors, walls = set(), set()
        for variant in building_catalog():
            structure, door = self.structure(variant)
            plan = build_interior(structure, door)
            self.assertEqual(plan.version, 4)
            self.assertEqual((plan.variant_id, plan.floor_material, plan.wall_material),
                             (variant['id'], variant['floor'], variant['wall']))
            floors.add(plan.floor_material); walls.add(plan.wall_material)
            self.assertTrue(position_clear(plan, plan.entry_x, plan.entry_y))
        self.assertEqual(len(floors), 7)
        self.assertEqual(len(walls), 3)
        paths = {self.visuals.resolve(self.visuals.ref('interior_textures', visual_id))
                 for visual_id in floors | walls}
        self.assertEqual(len(paths), 10)
        self.assertTrue(all(path is not None and path.is_file() for path in paths))

    def test_roundtrip_defaults_and_invalid_saved_style_metadata(self):
        structure, door = self.structure()
        plan = build_interior(structure, door)
        self.assertEqual(InteriorPlan.from_dict(plan.to_dict()).to_dict(), plan.to_dict())
        legacy = plan.to_dict()
        for field in ('variant_id', 'floor_material', 'wall_material'):
            del legacy[field]
        legacy['version'] = 3
        restored = InteriorPlan.from_dict(legacy)
        self.assertEqual((restored.variant_id, restored.floor_material, restored.wall_material), ('', '', ''))
        state = LivingWorldState(); state.interiors[plan.uid] = plan
        self.assertEqual(validate_sim_state(state.to_dict()), [])
        for field, bad in (('variant_id', 'not namespaced'), ('floor_material', 5),
                           ('wall_material', 'core:bad wall')):
            raw = state.to_dict(); raw['interiors'][plan.uid][field] = bad
            self.assertTrue(any('invalid interior ' + field in issue for issue in validate_sim_state(raw)))

    def storage_plan(self, version=4):
        return InteriorPlan('interior:storage-style', 'storage-style', 'door:storage-style',
                            0, 0, 0, 12000, 12000, entry_x=6000, entry_y=11000, version=version,
                            rooms=[InteriorRoom('room:storage-style', 'Store', InteriorRect(250, 250, 11500, 11200))])

    def container(self, plan):
        style = container_profile('core:household_chest')
        return ContainerState('storage:real', 0, 0, 0, 'player', style.capacity_mass_g,
                              style.capacity_volume_ml, {'core:wood': 3}, source_id=style.source_id,
                              profile_id=style.uid, kind='property', property_id=plan.building_id,
                              interior_space_id=plan.uid, interior_furniture_uid='storage-furniture:storage:real')

    def test_storage_binding_reuses_family_fixture_and_preserves_inventory_profile_source(self):
        plan = self.storage_plan()
        fixture = InteriorFurniture('fixture:existing-coffer', 'core:ironbound_coffer_piece',
                                    700, 700, 1150, 750, 'player', source_uid='fixture:existing-coffer')
        plan.furniture.append(fixture)
        container = self.container(plan)
        before = asdict(container); original_fixture = fixture.to_dict() if hasattr(fixture, 'to_dict') else asdict(fixture)
        bound = bind_storage(plan, [container])
        self.assertEqual(len(plan.furniture), 1)
        self.assertIs(bound[fixture.uid], container)
        self.assertEqual(asdict(fixture), original_fixture)
        after = asdict(container)
        self.assertEqual(after.pop('interior_furniture_uid'), fixture.uid)
        before.pop('interior_furniture_uid')
        self.assertEqual(after, before)
        saved = deepcopy(plan.to_dict()); bind_storage(plan, [container])
        self.assertEqual(plan.to_dict(), saved)

    def test_only_new_storage_projection_selects_family_art_legacy_chest_stays_original(self):
        for version, expected in ((3, 'core:house_chest_piece'), (4, 'core:ironbound_coffer_piece')):
            plan = self.storage_plan(version)
            container = self.container(plan)
            bind_storage(plan, [container])
            self.assertEqual(len(plan.furniture), 1)
            fixture = plan.furniture[0]
            self.assertEqual(fixture.piece_id, expected)
            self.assertEqual(fixture.source_uid, container.uid)
            self.assertEqual(container.items, {'core:wood': 3})
            style = container_profile(container.profile_id)
            self.assertEqual((fixture.w, fixture.h), (style.width, style.height))

    def test_seating_family_has_real_rest_action_without_new_goods(self):
        entities = EntityStore(); pid = entities.spawn(preferred_id=1)
        vitals = Vitals(stamina=40, pain=4); entities.add(pid, vitals)
        for row in furniture_variant_catalog():
            if row['base_piece'] not in {'core:chair_piece', 'core:bench_piece', 'core:stool_piece'}:
                continue
            with self.subTest(piece=row['id']):
                plan = self.storage_plan()
                plan.furniture = [InteriorFurniture('seat', row['id'], 1200, 1000,
                                                    row['width'], row['depth'], 'player')]
                state = LivingWorldState(); state.interiors[plan.uid] = plan
                state.interior_actors['player'] = InteriorActor(plan.uid, 1100, 1200)
                sim = SimpleNamespace(state=state, registry=self.registry, entities=entities, player_id=pid)
                system = InteriorSystem(sim)
                old_stamina = vitals.stamina
                self.assertIn('You rest', system.interact('seat'))
                self.assertEqual(vitals.stamina, min(100, old_stamina + 5))
                self.assertEqual(system.player_presence().action, 'resting')
                self.assertFalse(state.containers)

    def test_version_four_multifloor_sqlite_roundtrip_and_cli_verifier(self):
        structure, door = self.structure(size=8)
        pieces = [StructurePiecePlan('fixture:v4-bed', structure.uid, 'core:single_bed_piece', 1, 1, role='fixture')]
        ground = build_interior(structure, door, pieces=pieces)
        state = LivingWorldState(); state.interiors[ground.uid] = ground
        system = InteriorSystem(SimpleNamespace(state=state))
        floors = prepare_floors(system, ground, structure, profile_for(structure), new_ground=True)
        self.assertEqual(len(floors), 3)
        self.assertTrue(all((floor.variant_id, floor.floor_material, floor.wall_material)
                            == (ground.variant_id, ground.floor_material, ground.wall_material) for floor in floors))
        self.assertEqual(sum(f.source_uid == 'fixture:v4-bed' for floor in floors for f in floor.furniture), 1)
        self.assertEqual(validate_sim_state(state.to_dict()), [])
        with tempfile.TemporaryDirectory(prefix='worldseed-dev52-v4-') as folder:
            path = Path(folder) / 'furnished-v4.db'
            database = WorldDatabase.create(path, 'Dev52 furnished floors', 'aa' * 32)
            try:
                database.save_state(turn=1, tile_deltas={}, player_id=1, position=WorldPos(1, 3),
                                    inventory={}, sim_state=state.to_dict())
                self.assertEqual(database.verify(), [])
            finally:
                database.close()
            database = WorldDatabase.open(path)
            try:
                self.assertEqual(database.load_sim_state(), state.to_dict())
            finally:
                database.close()
            proof = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'tools' / 'verify_save.py'), str(path)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(proof.returncode, 0, proof.stdout + proof.stderr)
            self.assertIn('Save integrity: OK', proof.stdout)


if __name__ == '__main__':
    unittest.main()
