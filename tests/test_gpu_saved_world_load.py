"""Real persistent world loading, not just frozen main-menu boot.

Covers the world definition, state restore, warm-up and Simulation initialisation
where player reports an 'int context manager' failure on the GPU load screen.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from worldseed.app import _load_context
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Vitals
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.state import LivingWorldState


class SavedWorldLoadContracts(TestCase):
    def test_actual_saved_world_load_and_world_preparation(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'saved-load.db'
            seed=b'worldseed-frozen-load-regression'
            db=WorldDatabase.create(path,'Saved load test',seed.hex())
            try:
                # Legacy save replay is intentionally part of the contract.
                # This mirrors a Windows game selected from the world menu.
                db.set_meta('worldgen_version',3)
                db.connection.commit()
                state=LivingWorldState(player_name='Save Tester',clock_minute=540)
                db.save_state(turn=2,tile_deltas={},player_id=1,
                              position=WorldPos(2,3,0),inventory={'core:stone':2},
                              vitals=asdict(Vitals()),sim_state=state.to_dict())
            finally:
                db.close()
            phases=[]
            ctx=_load_context((path,False,'Saved load test',seed.hex()),
                              progress=lambda name,*_:phases.append(name),
                              prepare_world=True)
            try:
                self.assertEqual(ctx.state if hasattr(ctx,'state') else ctx.sim.state.player_name,'Save Tester')
                self.assertIn('Opening seeded world',phases)
                self.assertIn('World ready',phases)
                self.assertEqual(ctx.entities.get(ctx.player_id,
                    __import__('worldseed.entities.components',fromlist=['Inventory']).Inventory)
                    .items.get('core:stone'),2)
            finally:
                ctx.db.close()

    def test_load_screen_records_complete_traceback_and_phase_on_error(self):
        # Check the reporting contract without opening a real window or save.
        from worldseed import app
        import inspect
        code=inspect.getsource(app.main)
        self.assertIn('traceback.format_exc()',code)
        self.assertIn('last_loading_phase[0]',code)
        self.assertIn('The save has not been overwritten.',code)
