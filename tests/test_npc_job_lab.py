"""Behavioral contracts for the isolated, real-system NPC job laboratory."""

from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from worldseed.core.coords import WorldPos
from worldseed.labs.npc_jobs import MAX_MINUTES, NPCJobLab, SCENARIOS, START_MINUTE
from worldseed.systems.household_economy import FOODS


ROOT = Path(__file__).resolve().parents[1]


def goods(lab, item_id):
    """Count authoritative owners once; transfer logs never own cargo."""
    return (
        lab.town.stocks.get(item_id, 0)
        + sum(c.items.get(item_id, 0) for c in lab.state.containers.values())
        + sum(n.inventory.get(item_id, 0) for n in lab.state.npcs.values())
        + sum(p.items.get(item_id, 0) for p in lab.state.ground_piles.values())
    )


def all_goods(lab):
    """Read each real cargo owner independently of the report's total helper."""
    owners = [lab.town.stocks]
    owners += [c.items for c in lab.state.containers.values()]
    owners += [n.inventory for n in lab.state.npcs.values()]
    owners += [p.items for p in lab.state.ground_piles.values()]
    total = Counter()
    for items in owners:
        total.update(items)
    return +total


def cash(lab):
    return lab.town.wealth + sum(n.wealth for n in lab.state.npcs.values())


class NPCJobLabTests(unittest.TestCase):
    def assert_goods_conserved(self, lab, initial_goods):
        metrics = lab.snapshot()["metrics"]
        expected = Counter(initial_goods)
        expected.update(metrics["produced"])
        expected.update(metrics["gathered"])
        expected.subtract(metrics["consumed"])
        actual = all_goods(lab)
        for item_id in sorted(set(expected) | set(actual)):
            with self.subTest(item_id=item_id):
                self.assertEqual(actual[item_id], expected[item_id])

    def test_autonomous_tree_home_market_carpenter_chain_conserves_goods_and_cash(self):
        lab = NPCJobLab(scenario="supply_chain", seed="job-chain")
        logger = next(n for n in lab.state.npcs.values() if n.occupation == "lumberjack")
        carpenter = next(n for n in lab.state.npcs.values() if n.occupation == "carpenter")
        initial_cash = cash(lab)
        initial_wood = goods(lab, "core:wood")
        initial_bowls = goods(lab, "core:wooden_bowl")
        seen_carried_wood = False
        seen_home_wood = False
        positions = set()

        for _ in range(180):
            lab.step()
            positions.add((logger.x, logger.y, logger.z))
            seen_carried_wood |= logger.inventory.get("core:wood", 0) > 0
            seen_home_wood |= any(
                c.property_id == logger.home_id and c.items.get("core:wood", 0) > 0
                for c in lab.state.containers.values()
            )
            if lab.town.stocks.get("core:wooden_bowl", 0) > initial_bowls:
                break

        self.assertGreater(lab.town.stocks.get("core:wooden_bowl", 0), initial_bowls)
        self.assertTrue(seen_carried_wood)
        self.assertTrue(seen_home_wood)
        self.assertGreater(len(positions), 3)
        self.assertTrue(lab.state.resource_depletion)
        transactions = list(lab.state.market_transactions.values())
        for actor, kind in (
            (logger, "npc_output_sale"),
            (carpenter, "npc_input_purchase"),
            (carpenter, "npc_output_sale"),
        ):
            self.assertTrue(any(t.actor_uid == actor.uid and t.kind == kind for t in transactions))
        home_uids = {c.uid for c in lab.state.containers.values() if c.property_id == carpenter.home_id}
        self.assertTrue(any(
            t.container_uid in home_uids and t.direction == "deposit" and t.items.get("core:wooden_bowl", 0)
            for t in lab.state.physical_goods_transfers.values()
        ))
        self.assertEqual(cash(lab), initial_cash)
        gathered = lab.snapshot()["metrics"]["gathered"].get("core:wood", 0)
        self.assertGreater(gathered, 0)
        self.assertEqual(
            initial_wood + gathered,
            goods(lab, "core:wood") + goods(lab, "core:wooden_bowl") - initial_bowls,
        )

    def test_same_seed_and_actions_produce_identical_snapshots_in_every_scenario(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                first = NPCJobLab(scenario=scenario, seed="repeatable-job-lab", workers=2)
                second = NPCJobLab(scenario=scenario, seed="repeatable-job-lab", workers=2)
                first.run(600)
                second.step(120)
                self.assertEqual(first.snapshot(), second.snapshot())
                self.assertEqual(first.state.to_dict(), second.state.to_dict())
                self.assertTrue(all(
                    quantity >= 0
                    for owner in [first.town.stocks]
                    + [c.items for c in first.state.containers.values()]
                    + [n.inventory for n in first.state.npcs.values()]
                    for quantity in owner.values()
                ))

    def test_snapshot_is_observational_json_serializable_and_detached(self):
        lab = NPCJobLab(seed="snapshot-contract")
        lab.run(150)
        state_before = deepcopy(lab.state.to_dict())
        expected = lab.snapshot()
        self.assertIsInstance(json.loads(json.dumps(expected)), dict)
        snapshot = lab.snapshot()
        self.assertEqual(snapshot, expected)
        self.assertEqual(lab.state.to_dict(), state_before)

        # Mutate every exposed nested collection, including tasks and cargo.
        def contaminate(value):
            if isinstance(value, dict):
                for child in list(value.values()):
                    contaminate(child)
                value["test_only_mutation"] = True
            elif isinstance(value, list):
                for child in list(value):
                    contaminate(child)
                value.append("test_only_mutation")

        contaminate(snapshot)
        self.assertEqual(lab.snapshot(), expected)
        self.assertEqual(lab.state.to_dict(), state_before)

    def test_scarcity_blocks_crafting_without_inventing_inputs_or_output(self):
        lab = NPCJobLab(scenario="scarcity", seed="scarce-inputs", workers=2)
        initial_cash = cash(lab)
        expected = {item: goods(lab, item) for item in (
            "core:wood", "core:wooden_bowl", "core:iron_ore", "core:coal", "core:iron_bloom",
        )}
        lab.run(900)
        self.assertEqual({item: goods(lab, item) for item in expected}, expected)
        self.assertEqual(cash(lab), initial_cash)
        # Normal hunger still consumes paid meals. No profession may buy inputs
        # or sell nonexistent output while this experiment has no real inputs.
        transactions = list(lab.state.market_transactions.values())
        self.assertTrue(transactions)
        for transaction in transactions:
            self.assertEqual(transaction.kind, "npc_purchase")
            self.assertIn(transaction.actor_uid, lab.state.npcs)
            self.assertEqual(transaction.counterparty_uid, lab.town.uid)
            self.assertFalse(transaction.offered)
            self.assertEqual(sum(transaction.requested.values()), 1)
            self.assertTrue(set(transaction.requested).issubset(FOODS))
            self.assertGreater(transaction.copper_value, 0)
        self.assertFalse(lab.snapshot()["metrics"]["produced"])
        self.assertFalse(any(r.status == "completed" for r in lab.state.activity_reservations.values()))

    def test_all_scenarios_conserve_every_good_and_cash_through_one_day(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                lab = NPCJobLab(scenario=scenario, seed="day-long-conservation", workers=2)
                initial_goods, initial_cash = all_goods(lab), cash(lab)
                for _ in range(24):
                    lab.run(60)
                    self.assertEqual(lab.snapshot()["metrics"]["warnings"], [])
                self.assertEqual(cash(lab), initial_cash)
                self.assert_goods_conserved(lab, initial_goods)

    def test_every_scenario_spawns_workers_on_passable_cells_at_worker_limits(self):
        for scenario in SCENARIOS:
            for workers in (1, 8):
                with self.subTest(scenario=scenario, workers=workers):
                    lab = NPCJobLab(scenario=scenario, seed="worker-placement", workers=workers)
                    self.assertEqual(lab.snapshot()["metrics"]["warnings"], [])
                    for npc in lab.state.npcs.values():
                        self.assertTrue(lab.world.is_passable(WorldPos(npc.x, npc.y, npc.z)), npc.uid)
                        home = lab.physicalization.destination_for(npc.home_id)
                        self.assertIsNotNone(home)
                        self.assertTrue(lab.world.is_passable(home), npc.home_id)

    def test_every_supplied_workshop_job_produces_at_worker_limits(self):
        for workers in (1, 8):
            with self.subTest(workers=workers):
                lab = NPCJobLab(scenario="workshops", seed="all-workshop-outputs", workers=workers)
                initial_goods, initial_cash = all_goods(lab), cash(lab)
                lab.run(1440)
                metrics = lab.snapshot()["metrics"]
                self.assertEqual(metrics["warnings"], [])
                self.assertEqual(cash(lab), initial_cash)
                self.assert_goods_conserved(lab, initial_goods)
                for occupation in {n.occupation for n in lab.state.npcs.values()}:
                    worker = next(n for n in lab.state.npcs.values() if n.occupation == occupation)
                    with self.subTest(occupation=occupation):
                        if occupation == "farmer":
                            harvest_item = lab.registry.crops["core:wheat"].harvest_item
                            self.assertGreater(metrics["gathered"].get(harvest_item, 0), 0)
                        else:
                            self.assertGreater(metrics["batches"].get(worker.assigned_process_id, 0), 0)
                            process = lab.registry.settlement_processes[worker.assigned_process_id]
                            for item_id in process.outputs:
                                self.assertGreater(metrics["produced"].get(item_id, 0), 0)

    def test_blocked_work_is_diagnostic_without_failing_invariants(self):
        lab = NPCJobLab(scenario="blocked_path", seed="expected-path-stall")
        saw_stall = False
        for _ in range(180):
            metrics = lab.step()["metrics"]
            self.assertEqual(metrics["warnings"], [])
            saw_stall |= any("No path progress" in message for message in metrics["diagnostics"])
        self.assertTrue(saw_stall)
        self.assertFalse(lab.snapshot()["metrics"]["produced"])

    def test_simultaneous_paid_and_unpaid_meals_count_actual_consumption_once(self):
        lab = NPCJobLab(scenario="scarcity", seed="meal-accounting")
        eaters = list(lab.state.npcs.values())
        initial_goods, initial_cash = all_goods(lab), cash(lab)
        # An actor without cash can still consume a real available meal; the
        # observation must not depend on a purchase ledger entry being created.
        lab.town.wealth += eaters[0].wealth
        eaters[0].wealth = 0
        for npc in eaters:
            npc.hunger = 90
            npc.tasks = [dict(kind="perform", action="eat",
                              started_minute=lab.minute - 60, complete_minute=lab.minute + 5)]
        metrics = lab.step()["metrics"]
        self.assertEqual(metrics["consumed"], {"core:bread": len(eaters)})
        self.assertEqual(len(lab.state.market_transactions), len(eaters) - 1)
        self.assertTrue(all(n.hunger == 45 for n in eaters))
        self.assertEqual(metrics["warnings"], [])
        self.assertEqual(cash(lab), initial_cash)
        self.assert_goods_conserved(lab, initial_goods)

    def test_blocked_workplace_never_crosses_wall_or_teleports_to_produce(self):
        lab = NPCJobLab(scenario="blocked_path", seed="blocked-work")
        carpenter = next(n for n in lab.state.npcs.values() if n.occupation == "carpenter")
        self.assertLess(carpenter.x, 4)
        for y in range(-24, 25):
            self.assertFalse(lab.world.is_passable(WorldPos(4, y, 0)))
        initial_bowls = goods(lab, "core:wooden_bowl")
        previous = (carpenter.x, carpenter.y, carpenter.z)
        for _ in range(180):
            lab.step()
            current = (carpenter.x, carpenter.y, carpenter.z)
            self.assertLess(carpenter.x, 4)
            self.assertTrue(lab.world.is_passable(WorldPos(*current)))
            self.assertLessEqual(max(abs(a - b) for a, b in zip(previous, current)), 3)
            previous = current
        self.assertEqual(goods(lab, "core:wooden_bowl"), initial_bowls)

    def test_competing_workers_never_share_a_station_reservation(self):
        lab = NPCJobLab(scenario="station_contention", seed="shared-bench", workers=3)
        workers = [n for n in lab.state.npcs.values() if n.occupation == "carpenter"]
        self.assertGreaterEqual(len(workers), 2)
        saw_active_work = False
        for _ in range(180):
            lab.step()
            reservations = [r for r in lab.state.activity_reservations.values() if r.status in {"reserved", "active"}]
            targets = [r.target_uid for r in reservations]
            self.assertEqual(len(targets), len(set(targets)))
            saw_active_work |= any(r.status == "active" for r in reservations)
        self.assertTrue(saw_active_work)
        self.assertGreater(goods(lab, "core:wooden_bowl"), 0)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises((TypeError, ValueError)):
            NPCJobLab(scenario="missing_scenario")
        for workers in (0, 9, -1, True, 1.5, "2"):
            with self.subTest(workers=workers), self.assertRaises((TypeError, ValueError)):
                NPCJobLab(workers=workers)

    def test_time_validation_rejects_invalid_or_unbounded_advances_atomically(self):
        lab = NPCJobLab()
        lab.step()
        before = lab.snapshot()
        for minutes in (-5, 1, 5.0, True, "5", 7 * 1440, 7 * 1440 + 5):
            with self.subTest(minutes=minutes), self.assertRaises((TypeError, ValueError)):
                lab.run(minutes)
            self.assertEqual(lab.snapshot(), before)
        for ticks in (-1, True, 1.5, "1", 7 * 1440 // 5):
            with self.subTest(ticks=ticks), self.assertRaises((TypeError, ValueError)):
                lab.step(ticks)
            self.assertEqual(lab.snapshot(), before)
        lab.run(0)
        lab.step(0)
        self.assertEqual(lab.snapshot(), before)


class NPCJobLabCLITests(unittest.TestCase):
    def test_headless_zero_minutes_does_not_import_pygame(self):
        script = (
            "import sys\n"
            "from worldseed.labs.npc_job_cli import main\n"
            "result = main(['--headless', '--minutes', '0'])\n"
            "assert not any(name == 'pygame' or name.startswith('pygame.') for name in sys.modules)\n"
            "raise SystemExit(result)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["minute"], START_MINUTE)
        self.assertEqual(report["metrics"]["warnings"], [])

    def test_expected_blocked_path_diagnostics_do_not_fail_headless_run(self):
        result = subprocess.run(
            [sys.executable, "-m", "worldseed.labs.npc_job_cli", "--headless",
             "--scenario", "blocked_path", "--minutes", "900"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        metrics = json.loads(result.stdout)["metrics"]
        self.assertEqual(metrics["warnings"], [])
        self.assertTrue(metrics["diagnostics"])

    def test_headless_report_is_json_and_output_file_matches_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results" / "npc-jobs.json"
            result = subprocess.run(
                [sys.executable, "-m", "worldseed.labs.npc_job_cli", "--headless",
                 "--scenario", "supply_chain", "--seed", "cli-job-lab", "--minutes", "600", "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)
            expected = NPCJobLab(scenario="supply_chain", seed="cli-job-lab")
            expected.run(600)
            self.assertEqual(report, expected.snapshot())

    def test_headless_rejects_invalid_duration_with_nonzero_exit(self):
        result = subprocess.run(
            [sys.executable, "-m", "worldseed.labs.npc_job_cli", "--headless", "--minutes", "1"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.strip())


class NPCJobLabViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {
            "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", "PYGAME_HIDE_SUPPORT_PROMPT": "1",
        })
        cls.environment.start()
        import pygame
        from worldseed.labs.npc_job_viewer import LabViewer
        cls.pygame = pygame
        cls.viewer_class = LabViewer
        pygame.display.init()
        pygame.font.init()

    @classmethod
    def tearDownClass(cls):
        cls.pygame.display.quit()
        cls.pygame.font.quit()
        cls.environment.stop()

    def test_drawing_small_and_large_windows_is_observational(self):
        lab = NPCJobLab(scenario="workshops", seed="viewer-read-only", workers=2)
        lab.run(150)
        viewer = self.viewer_class(lab)
        state_before = deepcopy(lab.state.to_dict())
        snapshot_before = lab.snapshot()
        for dimensions in ((320, 240), (1180, 760)):
            with self.subTest(dimensions=dimensions):
                viewer.draw(self.pygame.Surface(dimensions))
                self.assertEqual(lab.state.to_dict(), state_before)
                self.assertEqual(lab.snapshot(), snapshot_before)

    def test_paused_update_resize_and_single_step_have_explicit_time_effects(self):
        lab = NPCJobLab(seed="viewer-controls")
        viewer = self.viewer_class(lab)
        before = lab.snapshot()
        viewer.update(2.0)
        self.assertEqual(lab.snapshot(), before)
        viewer.handle_event(self.pygame.event.Event(
            self.pygame.VIDEORESIZE, size=(640, 480), w=640, h=480,
        ))
        self.assertEqual(lab.snapshot(), before)
        viewer.handle_event(self.pygame.event.Event(self.pygame.KEYDOWN, key=self.pygame.K_RIGHT))
        expected = NPCJobLab(seed="viewer-controls")
        expected.step()
        self.assertEqual(lab.snapshot(), expected.snapshot())
        viewer.update(2.0)
        self.assertEqual(lab.snapshot(), expected.snapshot())

    def test_manual_step_at_limit_pauses_and_reset_restores_original_experiment(self):
        lab = NPCJobLab(seed="viewer-manual-limit")
        initial = lab.snapshot()
        lab.state.clock_minute = START_MINUTE + MAX_MINUTES - 5
        viewer = self.viewer_class(lab)
        right = self.pygame.event.Event(self.pygame.KEYDOWN, key=self.pygame.K_RIGHT)
        viewer.handle_event(right)
        self.assertEqual(lab.minute, START_MINUTE + MAX_MINUTES)
        self.assertFalse(viewer.running)
        capped = lab.snapshot()
        viewer.handle_event(right)
        self.assertEqual(lab.snapshot(), capped)
        self.assertIn("reset", viewer.status.lower())
        viewer.handle_event(self.pygame.event.Event(self.pygame.KEYDOWN, key=self.pygame.K_r))
        self.assertEqual(viewer.lab.snapshot(), initial)
        self.assertFalse(viewer.running)

    def test_automatic_update_advances_remaining_tick_then_pauses_at_limit(self):
        lab = NPCJobLab(seed="viewer-auto-limit")
        lab.state.clock_minute = START_MINUTE + MAX_MINUTES - 5
        viewer = self.viewer_class(lab)
        viewer.speed = 30
        viewer.running = True
        viewer.update(0.25)
        self.assertEqual(lab.minute, START_MINUTE + MAX_MINUTES)
        self.assertFalse(viewer.running)
        self.assertIn("reset", viewer.status.lower())
        capped = lab.snapshot()
        viewer.update(0.25)
        self.assertEqual(lab.snapshot(), capped)

    def test_cli_exports_final_viewer_experiment_after_replacement(self):
        from worldseed.labs.npc_job_cli import main

        replacement = NPCJobLab(scenario="scarcity", seed="viewer-return", workers=2)
        replacement.run(150)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "viewer-final.json"
            with patch("worldseed.labs.npc_job_viewer.run_viewer", return_value=replacement) as run_viewer:
                result = main(["--scenario", "supply_chain", "--minutes", "0", "--output", str(output)])
            self.assertEqual(result, 0)
            self.assertEqual(run_viewer.call_args.args[0].scenario, "supply_chain")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), replacement.snapshot())


if __name__ == "__main__":
    unittest.main()
