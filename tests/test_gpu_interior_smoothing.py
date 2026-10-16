"""Indoor viewport acceleration and remembered-object fade regressions.

No OpenGL context or saved world is needed: clip authority is frozen inputs.
"""
from __future__ import annotations

from dataclasses import replace
from random import Random
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from worldseed.presentation.gl_worldspace import SpriteCommand
from worldseed.presentation.interior_clip_index import InteriorClipIndex
from worldseed.presentation.interior_memory_fade import (
    DURATION_SECONDS, MEMORY_OPACITY, fade_commands, fading, update_departures)


def overlap(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]


def direct(rectangles,bounds,padding=0):
    a,b,c,d=bounds
    found=[]
    for x,y,x1,y1 in rectangles:
        x-=padding;y-=padding;x1+=padding;y1+=padding
        if overlap((x,y,x1,y1),bounds):
            found.append((max(a,x),max(b,y),min(c,x1),min(d,y1)))
    return tuple(found)


def scene(space,*,visible=(),remembered=()):
    return NS(space_id=space,objects=tuple(visible),memory_objects=tuple(remembered))


def art(uid,kind='furniture',content_id='core:bed',bounds=(2.,3.,3.,4.)):
    return NS(uid=uid,kind=kind,content_id=content_id,bounds=bounds)


def sprite(visual_id,remembered=False):
    return SpriteCommand(visual_id,'test-texture',1,b'\x80\x50\x20\xff'*4,2,2,
        (2.,3.,3.,4.),((2.,3.,2.4,3.6),),opacity=.62 if remembered else 1.,
        remembered=remembered)


class ClipIndexContracts(TestCase):
    def test_exact_intersections_match_ordered_reference_for_fine_sight_and_wall_padding(self):
        rng=Random(19)
        rectangles=[]
        for _ in range(550):
            x,y=rng.randrange(-80,160),rng.randrange(-80,160)
            w,h=rng.randrange(2,16),rng.randrange(2,16)
            rectangles.append((x+.125,y+.625,x+w+.125,y+h+.625))
        index=InteriorClipIndex(rectangles,bucket_size=16.)
        for _ in range(300):
            x,y=rng.randrange(-130,210),rng.randrange(-130,210)
            w,h=rng.randrange(2,62),rng.randrange(2,62)
            bounds=(x-.25,y+.375,x+w-.25,y+h+.375)
            for padding in (0,4.):
                with self.subTest(bounds=bounds,padding=padding):
                    self.assertEqual(index.intersect(bounds,padding),direct(rectangles,bounds,padding))

    def test_visible_and_memory_indexes_cannot_admit_hidden_rooms(self):
        visible=((0,0,500,500),(500,0,1000,500))
        memory=((0,500,500,1000),)
        current=InteriorClipIndex(visible,500)
        remembered=InteriorClipIndex(memory,500)
        self.assertEqual(current.intersect((1500,0,2000,500)),())
        self.assertEqual(remembered.intersect((600,0,900,500)),())
        self.assertEqual(current.intersect((500,0,1000,500)),((500,0,1000,500),))
        self.assertEqual(remembered.intersect((0,500,500,1000)),memory)
        self.assertEqual(current.intersect((1000,0,1500,500)),())

    def test_zero_area_rectangles_and_large_spans_are_safe(self):
        index=InteriorClipIndex(((0,0,0,4),(-1000,-1,1000,1),(0,1,100,100)),8)
        self.assertEqual(index.intersect((0,0,0,8)),())
        self.assertEqual(index.intersect((50,-1,60,0)),((50,-1,60,0),))
        self.assertEqual(index.intersect((200,20,220,40)),())
        with self.assertRaises(ValueError):
            InteriorClipIndex((),0)


class InteriorFadeContracts(TestCase):
    def test_only_last_seen_static_art_transitions_out_of_live_sight(self):
        previous=scene('floor-1',visible=(art('bed'),art('actor','npc')))
        current=scene('floor-1',remembered=(art('bed'),art('actor','npc')))
        stamps=update_departures(previous,current,{},100.)
        self.assertEqual(stamps,{'bed':100.})
        self.assertTrue(fading(stamps,100.2))
        self.assertFalse(fading(stamps,101.))
        self.assertEqual(update_departures(current,current,stamps,101.),{})

    def test_transitions_do_not_cross_saved_floors_or_repaint_hidden_new_props(self):
        current=scene('floor-2',remembered=(art('new'),art('bed')))
        previous=scene('floor-1',visible=(art('bed'),))
        self.assertEqual(update_departures(previous,current,{},10.),{})
        current_same=scene('floor-1',remembered=(art('bed',content_id='core:changed'),))
        self.assertEqual(update_departures(previous,current_same,{},10.),{})
        self.assertEqual(update_departures(None,current,{},10.),{})

    def test_fade_preserves_memory_classification_and_exact_visibility_scissor(self):
        commands=(sprite('interior-memory-object:bed',True),
                  sprite('interior-memory-object:other',True),
                  sprite('interior-actor:npc:visible'))
        for elapsed in (0.,DURATION_SECONDS/2,DURATION_SECONDS):
            result=fade_commands(commands,{'bed':10.},10.+elapsed)
            self.assertEqual(result[0].clip_rects,commands[0].clip_rects)
            self.assertTrue(result[0].remembered)
            self.assertEqual(result[1:],commands[1:])
            self.assertGreaterEqual(result[0].opacity,MEMORY_OPACITY)
            self.assertLessEqual(result[0].opacity,1.)
        self.assertAlmostEqual(fade_commands(commands,{'bed':10.},10.)[0].opacity,1.)
        self.assertAlmostEqual(fade_commands(commands,{'bed':10.},10.+DURATION_SECONDS)[0].opacity,MEMORY_OPACITY)
        self.assertEqual(fade_commands(commands,{},10.),commands)

    def test_idle_gpu_refresh_runs_only_during_active_fade_and_one_terminal_frame(self):
        from worldseed.ui.gpu_terminal import GpuTerminal
        terminal=object.__new__(GpuTerminal)
        terminal._focused=True
        terminal._snapshot=NS(interior=True)
        terminal._smoke_frames=0
        terminal._gpu_last_idle=0
        terminal._interior_fades={'bed':10.}
        terminal._composite=Mock()
        with patch('worldseed.ui.gpu_terminal.time.monotonic',return_value=10.25):
            terminal._animate_idle_effects(100)
        terminal._composite.assert_called_once()
        with patch('worldseed.ui.gpu_terminal.time.monotonic',return_value=11.):
            terminal._animate_idle_effects(200)
        self.assertEqual(terminal._composite.call_count,2)
        self.assertFalse(terminal._interior_fades)
        terminal._animate_idle_effects(300)
        self.assertEqual(terminal._composite.call_count,2)
