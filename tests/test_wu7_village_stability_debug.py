from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from worldseed.debug import SessionDebugLog
from tools.run_ci_check import _console_print


class VillageStabilityDebugTests(unittest.TestCase):
    def test_bounded_runner_escapes_output_unsupported_by_console_codec(self):
        raw=io.BytesIO()
        narrow=io.TextIOWrapper(raw,encoding="ascii",errors="strict",write_through=True)
        original=sys.stdout
        try:
            sys.stdout=narrow
            _console_print("bad \ufffd glyph",flush=True)
            narrow.flush()
        finally:
            sys.stdout=original
        self.assertIn(b"bad \\ufffd glyph",raw.getvalue())

    def test_session_debug_log_is_jsonl_bounded_and_records_stage_timings(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=SessionDebugLog(root=Path(tmp),engine_version="test",world="fixture")
            log.event("ui_input",key="w")
            with log.stage("village_stage",warn_ms=0):
                pass
            log.flush()
            rows=[json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["kind"],"session_start")
            self.assertTrue(any(row.get("kind")=="ui_input" and row.get("key")=="w" for row in rows))
            stage=next(row for row in rows if row.get("kind")=="stage" and row.get("name")=="village_stage")
            self.assertIn("elapsed_ms",stage)
            self.assertTrue(stage["slow"])
            for handler in list(log.logger.handlers):
                handler.close()
                log.logger.removeHandler(handler)

    def test_region_entry_uses_bounded_local_route_sync_and_stage_diagnostics(self):
        src=Path("worldseed/sim/engine.py").read_text(encoding="utf-8")
        start=src.index("    def _ensure_nearby_world")
        end=src.index("    def _post_action",start)
        body=src[start:end]
        self.assertIn('self.debug.event("region_activation_start"',body)
        self.assertIn('self.debug.stage("settlement_physicalization"',body)
        self.assertIn("self.route_planner.sync(self.state.settlements.values(),(rx,ry),radius=2,persist=True)",body)
        self.assertNotIn("sync_network(",body)
        self.assertIn("for ax in range(rx-1,rx+2)",body)
        self.assertIn("self.society_gen.settlement_for_cell(rx,ry)",body)
        self.assertNotIn("self.society_gen.settlement_for_cell(ax,ay)",body)

    def test_routine_movement_no_longer_spams_activity_feed(self):
        src=Path("worldseed/sim/engine.py").read_text(encoding="utf-8")
        start=src.index("    def _move(")
        end=src.index("    def _vertical(",start)
        body=src[start:end]
        self.assertNotIn("You move across",body)
        self.assertIn("Ordinary one-tile movement is intentionally silent",body)

    def test_generated_buildings_keep_door_corridors_clear_and_cover_shell(self):
        src=Path("worldseed/systems/settlement_planner.py").read_text(encoding="utf-8")
        self.assertIn("for cell in sorted(shell|interior",src)
        self.assertIn("door_clearance={",src)
        self.assertIn("safe_cells=[cell for cell in interior_sorted if cell not in door_clearance]",src)
        self.assertIn("abs(cell[0]-entrance_inside[0])+abs(cell[1]-entrance_inside[1])>1",src)

    def test_retired_casing_cannot_survey_or_disclose_property(self):
        from types import SimpleNamespace
        from worldseed.core.coords import WorldPos
        from worldseed.systems.property_intrusion import CasingSystem
        from worldseed.systems.state import LivingWorldState
        state=LivingWorldState(player_hunting_stance="stalk",player_stealth_mode=True)
        # No physical queries are available: the retired action must not
        # inspect terrain, reveal inventories, or synthesize new intel.
        casing=CasingSystem(state,SimpleNamespace(),SimpleNamespace(),SimpleNamespace())
        before=state.to_dict()
        ok,message=casing.start("home:test",WorldPos(0,0),600,SimpleNamespace())
        self.assertFalse(ok)
        self.assertIn("disabled",message)
        self.assertEqual(casing.observe_step(WorldPos(0,1),601,SimpleNamespace()),[])
        self.assertEqual(state.to_dict(),before)

    def test_discovered_static_buildings_remain_visible_as_memory_not_live_entities(self):
        src=Path("worldseed/ui/pygame_terminal.py").read_text(encoding="utf-8")
        self.assertIn("def _blit_static_memory",src)
        self.assertIn("if pos_key(*key) in visible",src)
        self.assertIn("if pk not in known:continue",src)
        self.assertIn("if not is_visible:",src)
        self.assertIn("Never remember live actors",src)

    def test_village_npc_movement_reuses_local_path_between_ticks(self):
        src=Path("worldseed/systems/ai.py").read_text(encoding="utf-8")
        self.assertIn('task.get("_local_path",[])',src)
        self.assertIn('task["_local_path"]=cached',src)
        self.assertIn('task["_local_path_goal"]=cache_goal',src)
        self.assertIn("while cached and moved<3",src)

    def test_world_interaction_and_live_panel_contracts_are_exposed(self):
        app=Path("worldseed/app.py").read_text(encoding="utf-8")
        pointer=Path("worldseed/ui/pointer.py").read_text(encoding="utf-8")
        widgets=Path("worldseed/ui/widgets.py").read_text(encoding="utf-8")
        for token in (
            "use_fixture","use_market_here","inspect_property_storage",
            "lockpick_property_storage",
        ):
            self.assertIn(token,app)
        self.assertIn("UI_WORLD_MOVE:",widgets)
        self.assertIn("menu_page_size",pointer)
        self.assertIn("inventory_unified",pointer)
        self.assertIn("container_inventory",pointer)
        self.assertIn("crafting_unified",pointer)

    def test_crash_report_points_to_continuous_session_debug_log(self):
        src=Path("worldseed/app.py").read_text(encoding="utf-8")
        self.assertIn('ctx.sim.debug.exception(',src)
        self.assertIn("debug_log_path(ctx.sim)",src)
        self.assertIn("Session debug log:",src)


if __name__=="__main__":
    unittest.main()
