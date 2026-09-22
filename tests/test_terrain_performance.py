import unittest,json,hashlib,os
from dataclasses import asdict
from unittest.mock import patch
from worldseed.world.landforms import LandformSampler


class GeologyCacheTests(unittest.TestCase):
    def test_cached_geology_matches_frozen_dev33_outputs(self):
        sampler=LandformSampler(b'cache-regression')
        coords=[(-4097,-2049),(-1536,0),(-1,-1),(0,0),(511,1025),(2048,-3072),(8191,4097)]
        rows=[asdict(sampler.sample(x,y)) for x,y in coords]
        # Captured from main e9c41ac before the cache change.
        self.assertEqual(hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),"83246235aabd5509a225142833b5a38dad2fa3a95688ae63073b3281acc6044a")
        sampler.sample.cache_clear();sampler._feature_hash.cache_clear();sampler._stress_direction.cache_clear()
        self.assertEqual([asdict(sampler.sample(x,y)) for x,y in reversed(coords)],list(reversed(rows)))

    def test_adjacent_samples_reuse_geological_feature_hashes(self):
        sampler=LandformSampler(b'cache-regression');sampler.sample(10,10)
        before=sampler._feature_hash.cache_info()
        sampler.sample(11,10)
        after=sampler._feature_hash.cache_info()
        self.assertEqual(before.misses,after.misses)
        self.assertGreater(after.hits,before.hits)
        self.assertEqual(sampler.sample.cache_info().maxsize,65536)
        self.assertEqual(after.maxsize,8192)


class ContinuousGroundTests(unittest.TestCase):
    def setUp(self):
        from worldseed.ui.pygame_terminal import PygameTerminal
        if not PygameTerminal.available():self.skipTest('pygame optional')
        self.env=patch.dict(os.environ,{'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'});self.env.start()
        self.term=PygameTerminal();self.term.enter()

    def tearDown(self):
        if hasattr(self,'term'):self.term.restore();self.env.stop()

    def test_forest_uses_continuous_world_anchored_material(self):
        term=self.term;ref=term._visuals.ref('terrain','core:forest');path=term._visuals.resolve(ref)
        a=term._ground_material('core:forest',path,28,0,0)
        b=term._ground_material('core:forest',path,28,1,0)
        self.assertNotEqual(term.pg.image.tobytes(a,'RGB'),term.pg.image.tobytes(b,'RGB'))
        self.assertIs(a,term._ground_material('core:forest',path,28,16,0))
        self.assertEqual(term._material_phase('core:forest',-1,-1),(16,15,15))
        source=term._sprite_cache[('continuous-ground',str(path),28,16)]
        combined=term.pg.Surface((56,28));combined.blit(a,(0,0));combined.blit(b,(28,0))
        self.assertEqual(term.pg.image.tobytes(combined,'RGB'),term.pg.image.tobytes(source.subsurface((0,0,56,28)),'RGB'))

    def test_cached_sprites_do_not_stat_disk_every_frame(self):
        from pathlib import Path
        path=self.term._visuals.resolve(self.term._visuals.ref('terrain','core:forest'))
        one=self.term._load_sprite(path,28,28)
        ground=self.term._load_terrain_sprite(path,28)
        with patch.object(Path,'stat',side_effect=AssertionError('cached sprite hit disk')):
            self.assertIs(one,self.term._load_sprite(path,28,28))
            self.assertIs(ground,self.term._load_terrain_sprite(path,28))
