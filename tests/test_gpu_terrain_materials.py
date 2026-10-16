"""GPU materials consume current terrain art without inventing forest cells."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.gpu_scene_bridge import _terrain_path, terrain_source
from worldseed.presentation.visuals import VisualRegistry


class GPUTerrainMaterials(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)
        cls.visuals=VisualRegistry.load_default()

    def test_all_canonical_ground_uses_existing_catalog_materials(self):
        # In particular, ocean shelves, estuaries, streams, riverbanks and new
        # coastal/cave materials have no same-ID filename to guess.
        for terrain_id in self.registry.terrains:
            with self.subTest(terrain_id=terrain_id):
                path=terrain_source(terrain_id,11,23,terrain_defs=self.registry.terrains)
                expected={self.visuals.base_dir/raw for raw in self.visuals.ref('terrain',terrain_id).paths}
                self.assertIn(path,expected)
                self.assertTrue(path.is_file())
        self.assertEqual(terrain_source('core:forest',0,0).name,'forest_floor.png')
        self.assertTrue(terrain_source('core:river',0,0).name.startswith('v6_freshwater_deep_'))

    def test_coordinate_variants_are_stable_without_changing_content(self):
        first=terrain_source('core:ocean_shelf',-15,37)
        self.assertEqual(first,terrain_source('core:ocean_shelf',-15,37))
        variants={terrain_source('core:ocean_shelf',x,37) for x in range(20)}
        self.assertGreater(len(variants),1)
        self.assertTrue(all(path.name.startswith('v6_ocean_shelf_') for path in variants))

    def test_mod_namespace_cannot_collide_with_core_filename(self):
        unknown=self.visuals.special('unknown')
        self.assertEqual(terrain_source('mod:forest',0,0),unknown)
        self.assertEqual(terrain_source('../../forest',0,0),unknown)
        self.assertEqual(terrain_source('unregistered',0,0),unknown)

    def test_explicit_mod_catalog_entry_takes_precedence_over_tag_fallback(self):
        with TemporaryDirectory() as directory:
            base=Path(directory)
            (base/'new-ground.png').touch()
            visuals=VisualRegistry({'terrain':{'mod:forest':'new-ground.png'}},base)
            definitions={'mod:forest':SimpleNamespace(tags=('surface','water'))}
            self.assertEqual(terrain_source('mod:forest',0,0,terrain_defs=definitions,visuals=visuals),base/'new-ground.png')

    def test_new_surface_and_underground_ground_inherit_physical_tags(self):
        definitions={
            'mod:brackish_pool':SimpleNamespace(tags=('surface','water','brackish','shallow')),
            'mod:salt_deep':SimpleNamespace(tags=('surface','water','saltwater','deep')),
            'mod:shingle':SimpleNamespace(tags=('surface','shore','rock')),
            'mod:meadow':SimpleNamespace(tags=('surface','soil')),
            'mod:passage':SimpleNamespace(tags=('underground',),passable=True),
            'mod:wall':SimpleNamespace(tags=('underground','rock'),passable=False),
        }
        expected={
            'mod:brackish_pool':'core:estuary_shallow','mod:salt_deep':'core:ocean_deep',
            'mod:shingle':'core:rock','mod:meadow':'core:grass',
            'mod:passage':'core:cave_floor','mod:wall':'core:cave_wall',
        }
        before={key:vars(value).copy() for key,value in definitions.items()}
        for terrain_id,material in expected.items():
            with self.subTest(terrain_id=terrain_id):
                self.assertEqual(terrain_source(terrain_id,3,7,terrain_defs=definitions),terrain_source(material,3,7))
        self.assertEqual(before,{key:vars(value).copy() for key,value in definitions.items()})

    def test_unmapped_hard_features_remain_explicit_unknown(self):
        for tag in ('shaft','ore','loot'):
            definition={'mod:feature':SimpleNamespace(tags=('underground',tag))}
            self.assertEqual(terrain_source('mod:feature',0,0,terrain_defs=definition),self.visuals.special('unknown'))

    def test_material_lookup_cache_is_bounded_for_many_missing_mod_ids(self):
        for index in range(160):
            terrain_source(f'mod:unknown_{index}',index,-index)
        self.assertLessEqual(_terrain_path.cache_info().currsize,128)


if __name__=='__main__':unittest.main()
