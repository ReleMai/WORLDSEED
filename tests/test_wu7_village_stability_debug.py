from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from worldseed.debug import SessionDebugLog


class VillageStabilityDebugTests(unittest.TestCase):
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

    def test_property_casing_is_sightline_based_and_ignores_blocked_neighbor_cells(self):
        src=Path("worldseed/systems/property_intrusion.py").read_text(encoding="utf-8")
        self.assertIn("def _survey_targets",src)
        self.assertIn("cell.structure_id!=structure.uid",src)
        self.assertIn("self.physicalization.passable(p,True)",src)
        self.assertIn("stealth.visible_from(player_pos,target)",src)
        self.assertIn("Move within sight of the property before casing it.",src)
        self.assertIn("abs(x-int(entrance[0]))+abs(y-int(entrance[1]))<=1",src)

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
        self.assertIn("UI_WORLD_MOVE:",pointer)
        self.assertIn("UI_WORLD_MOVE:",widgets)
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
