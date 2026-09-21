from __future__ import annotations

import tempfile
import unittest
from collections import deque
from pathlib import Path

from worldseed.app import _load_context
from worldseed.config import RESOURCEGEN_VERSION, WORLDGEN_VERSION
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.ui.startup import StartSelection


def _profile():
    return {
        'attributes': {'strength': 5, 'agility': 5, 'endurance': 5, 'intellect': 5, 'perception': 5, 'will': 5},
        'skills': {k: 0 for k in ('athletics','survival','foraging','woodcutting','mining','hunting','melee','crafting','medicine','scholarship','persuasion','trading','naturalism','arcana')},
        'talents': [],
    }


class RC10WorldgenTests(unittest.TestCase):
    def _new_context(self, root: Path, seed_text: str):
        seed=seed_text.encode()
        sel=StartSelection(root/f'{seed_text}.db',True,seed_text,seed.hex(),'Tester','custom',_profile())
        return _load_context(sel,prepare_world=False)

    def test_new_world_uses_current_versioned_terrain_and_v3_resources(self):
        with tempfile.TemporaryDirectory() as td:
            ctx=self._new_context(Path(td),'rc10-version')
            try:
                self.assertEqual(ctx.world.generator.version,WORLDGEN_VERSION)
                self.assertEqual(ctx.world.resourcegen_version,RESOURCEGEN_VERSION)
                self.assertEqual(ctx.db.get_meta('worldgen_version'),WORLDGEN_VERSION)
                self.assertEqual(ctx.db.get_meta('resourcegen_version'),RESOURCEGEN_VERSION)
            finally:ctx.db.close()

    def test_old_save_keeps_terrain_version_but_adopts_safe_resource_version(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'old.db';seed=b'rc10-old-save'
            db=WorldDatabase.create(path,'old',seed.hex())
            db.set_meta('worldgen_version',3)
            db.connection.execute("DELETE FROM world_meta WHERE key='resourcegen_version'")
            db.connection.commit();db.close()
            ctx=_load_context((path,False,'old',seed.hex()),prepare_world=False)
            try:
                self.assertEqual(ctx.world.generator.version,3)
                self.assertEqual(ctx.world.resourcegen_version,RESOURCEGEN_VERSION)
                self.assertEqual(ctx.db.get_meta('resourcegen_version'),RESOURCEGEN_VERSION)
            finally:ctx.db.close()

    def test_blocking_natural_features_never_share_cardinal_edge(self):
        with tempfile.TemporaryDirectory() as td:
            ctx=self._new_context(Path(td),'rc10-spacing')
            try:
                p=ctx.sim.player_pos;blocked=set()
                for y in range(p.y-20,p.y+21):
                    for x in range(p.x-20,p.x+21):
                        q=WorldPos(x,y,0)
                        if ctx.sim.resources.blocks_movement(q):blocked.add((x,y))
                for x,y in blocked:
                    self.assertNotIn((x+1,y),blocked)
                    self.assertNotIn((x,y+1),blocked)
            finally:ctx.db.close()

    def test_spawn_has_large_connected_walkable_neighborhood(self):
        with tempfile.TemporaryDirectory() as td:
            ctx=self._new_context(Path(td),'rc10-connected-start')
            try:
                p=ctx.sim.player_pos;radius=14
                def walkable(x,y):
                    q=WorldPos(x,y,0)
                    return ctx.world.is_passable(q) and not ctx.sim.resources.blocks_movement(q)
                self.assertTrue(walkable(p.x,p.y))
                seen={(p.x,p.y)};q=deque([(p.x,p.y)])
                while q:
                    x,y=q.popleft()
                    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                        nx,ny=x+dx,y+dy
                        if (nx,ny) in seen or max(abs(nx-p.x),abs(ny-p.y))>radius:continue
                        if not walkable(nx,ny):continue
                        seen.add((nx,ny));q.append((nx,ny))
                self.assertGreaterEqual(len(seen),450)
            finally:ctx.db.close()

    def test_pygame_clicks_require_hit_tested_targets(self):
        source=(Path(__file__).resolve().parents[1]/'worldseed'/'ui'/'pygame_terminal.py').read_text(encoding='utf-8')
        self.assertIn('token=self._hit_token(self._last_mouse)',source)
        self.assertNotIn('if event.button == 3:\n                    return "ESC"',source)
        self.assertNotIn('if event.button == 1:\n                    return "\\r"',source)
        self.assertIn('pg.K_w,pg.K_a,pg.K_s,pg.K_d',source)


if __name__=='__main__':unittest.main()
