import dataclasses
import os
import unittest
from unittest.mock import Mock

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
from worldseed.presentation.atmosphere import WeatherSample,EffectFrame,FieldEmitter,EffectStack
from worldseed.ui.pygame_terminal import PygameTerminal


def frame(**kwargs):
    values=dict(seed=b'particles',width=640,height=360,left=0,top=0,tile_px=20,
                elapsed_ms=15000,game_minute=720,weather=WeatherSample(cloud_cover=90,wind_dx=700,wind_dy=-200))
    values.update(kwargs)
    return EffectFrame(**values)


class AtmosphereTests(unittest.TestCase):
    def test_samples_are_copies_and_frozen(self):
        original=dict(cloud_cover=70,wind_dx=100)
        sample=WeatherSample.capture(original)
        original['cloud_cover']=0
        self.assertEqual(sample.cloud_cover,70)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            sample.cloud_cover=10

    def test_field_is_camera_independent_and_reconstructable(self):
        emitter=FieldEmitter('test:clouds',24)
        a={p.identity:p for p in emitter.particles(frame())}
        b={p.identity:p for p in emitter.particles(frame(left=1,top=-1))}
        common=set(a)&set(b)
        self.assertGreater(len(common),5)
        for identity in common:
            self.assertEqual(a[identity],b[identity])
        self.assertEqual(a,{p.identity:p for p in FieldEmitter('test:clouds',24).particles(frame())})
        other={p.identity for p in FieldEmitter('test:smoke',24).particles(frame())}
        self.assertFalse(set(a)&other)

    def test_lifecycles_change_without_retained_history_and_are_bounded(self):
        emitter=FieldEmitter('test:life',24,lifetime_ms=1000,max_particles=17)
        early=list(emitter.particles(frame(elapsed_ms=0)))
        late=list(emitter.particles(frame(elapsed_ms=10000)))
        self.assertFalse({p.identity for p in early}&{p.identity for p in late})
        for particle in early+late:
            self.assertGreaterEqual(particle.opacity,0)
            self.assertLessEqual(particle.opacity,1)
            self.assertGreaterEqual(particle.age,0)
            self.assertLess(particle.age,1)
        enormous=list(emitter.particles(frame(width=10**9,height=10**9)))
        self.assertLessEqual(len(enormous),17)
        self.assertEqual(set(vars(emitter)),{'namespace','spacing','reach','drift_scale','lifetime_ms','max_particles'})


@unittest.skipUnless(PygameTerminal.available(),'pygame optional')
class AtmosphereRenderingTests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal();self.term.enter();self.pg=self.term.pg

    def tearDown(self):
        self.term.restore()

    def test_cloud_identities_have_distinct_silhouettes_and_share_shadow_support(self):
        clouds=self.term._weather_fx._clouds
        signatures=set()
        for identity in range(12):
            cloud,shadow=clouds._shape(identity,'bank')
            cloud_pixels=self.pg.image.tobytes(cloud,'RGBA')[3::4]
            shadow_pixels=self.pg.image.tobytes(shadow,'RGBA')[3::4]
            signatures.add(cloud_pixels)
            self.assertTrue(all(c>0 or s==0 for c,s in zip(cloud_pixels,shadow_pixels)))
            self.assertGreater(sum(a>0 for a in shadow_pixels)/sum(a>0 for a in cloud_pixels),0.98)
        self.assertEqual(len(signatures),12)
        self.assertNotEqual(self.pg.image.tobytes(clouds._shape(0,'bank')[0],'RGBA'),
                            self.pg.image.tobytes(clouds._shape(0,'wisp')[0],'RGBA'))
        clouds._shapes.clear()
        self.assertIn(self.pg.image.tobytes(clouds._shape(0,'bank')[0],'RGBA')[3::4],signatures)

    def test_registered_layers_are_ordered_clipped_and_restore_clip_on_failure(self):
        pg=self.pg;screen=pg.Surface((30,30));screen.fill((0,0,0))
        stack=EffectStack();calls=[]
        def render(name,color):
            def draw(sample):
                calls.append((name,sample))
                surf=pg.Surface((30,30));surf.fill(color)
                return (surf,)
            return draw
        stack.register('late',30,render('late',(255,0,0)),lambda w: w.rain>0)
        stack.register('early',10,render('early',(0,255,0)),lambda w: False)
        rect=pg.Rect(5,5,10,10);sample=frame()
        stack.draw(screen,rect,sample)
        self.assertEqual([name for name,_ in calls],['early','late'])
        self.assertTrue(all(item is sample for _,item in calls))
        self.assertEqual(screen.get_at((6,6))[:3],(255,0,0))
        self.assertEqual(screen.get_at((16,16))[:3],(0,0,0))
        self.assertEqual(screen.get_clip(),pg.Rect(0,0,30,30))
        self.assertTrue(stack.animated(WeatherSample(rain=1)))
        with self.assertRaises(ValueError):
            stack.register('late',0,None,None)
        stack.register('broken',40,Mock(side_effect=RuntimeError('test')),lambda w: False)
        with self.assertRaises(RuntimeError):
            stack.draw(screen,rect,sample)
        self.assertEqual(screen.get_clip(),pg.Rect(0,0,30,30))
