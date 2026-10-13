"""Checkpoint failure and revision-aware terrain acknowledgement regressions.

``make_save_fixture`` also creates a small legacy-version save for verify_save.py.
It deliberately avoids Simulation startup, regional planning and pygame.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from worldseed.app import GameContext, _save
from worldseed.config import CHUNK_SIZE, DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos, split_world
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class CommitFailureConnection(sqlite3.Connection):
    """Fail once at the actual transaction-exit boundary, before durable commit."""
    fail_next_commit = False

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None and self.fail_next_commit:
            self.fail_next_commit = False
            self.rollback()
            raise sqlite3.OperationalError("injected checkpoint commit failure")
        return super().__exit__(exc_type, exc, traceback)


def make_save_fixture(directory, registry=None, *, cache_chunks=2, failing_commit=False):
    """Return an open context; its owner must close ``ctx.db`` when finished."""
    registry = registry or ContentRegistry.load(DATA_DIR)
    path = Path(directory) / "save-retry.db"
    seed = b"save-retry-regression"
    db = WorldDatabase.create(path, "Save retry regression", seed.hex())
    db.set_meta("worldgen_version", 3)
    db.connection.commit()
    if failing_commit:
        db.close()
        db = WorldDatabase(path, sqlite3.connect(path, factory=CommitFailureConnection))
    world = World(WorldGenerator(seed, registry, version=3), registry, db,
                  cache_chunks=cache_chunks, auto_hydrology=False)
    entities = EntityStore()
    player = entities.spawn(preferred_id=1)
    entities.add(player, Position(WorldPos(2, 3, 0)))
    entities.add(player, Inventory({"core:stone": 2}))
    entities.add(player, Vitals(hp=85, blood=90))
    state = LivingWorldState(player_name="Retry Tester", clock_minute=495)
    debug = SimpleNamespace(event=lambda *args, **kwargs: None, flush=lambda: None)
    sim = SimpleNamespace(turn=3, state=state, debug=debug)
    return GameContext(db, registry, world, entities, sim, player)


class SaveRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def make_context(self, **kwargs):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        ctx = make_save_fixture(directory.name, self.registry, **kwargs)
        self.addCleanup(ctx.db.close)
        return ctx

    def begin_pending_checkpoint(self, ctx):
        """Persist a baseline, then change all checkpoint-owned state."""
        _save(ctx, backup=False)
        before = {
            "last_saved_at": ctx.db.get_meta("last_saved_at"),
            "player_name": ctx.db.get_meta("player_name"),
            "offline_time": ctx.sim.state.last_offline_wall_time,
            "state": ctx.db.load_sim_state(),
            "inventory": ctx.db.load_component(ctx.player_id, "Inventory"),
            "vitals": ctx.db.load_component(ctx.player_id, "Vitals"),
            "turn": ctx.db.get_meta("turn"),
        }
        pos = ctx.entities.get(ctx.player_id, Position).value
        ctx.world.set_terrain(pos, "core:rock")
        ctx.sim.turn += 1
        ctx.sim.state.clock_minute += 5
        ctx.sim.state.player_name = "After checkpoint"
        ctx.entities.get(ctx.player_id, Inventory).add("core:stone", 3)
        ctx.entities.get(ctx.player_id, Vitals).hp = 82
        return pos, before

    def assert_pending_checkpoint(self, ctx, pos, before):
        self.assertEqual(ctx.world.dirty_tiles, {pos: "core:rock"})
        self.assertIn(split_world(pos)[0], ctx.world.cache._pinned)
        self.assertEqual(ctx.world.tile_at(pos).terrain_id, "core:rock")
        self.assertEqual(ctx.sim.state.last_offline_wall_time, before["offline_time"])
        self.assertEqual(ctx.db.get_meta("last_saved_at"), before["last_saved_at"])
        self.assertEqual(ctx.db.get_meta("player_name"), before["player_name"])
        self.assertEqual(ctx.db.get_meta("turn"), before["turn"])
        self.assertEqual(ctx.db.load_sim_state(), before["state"])
        self.assertEqual(ctx.db.load_component(ctx.player_id, "Inventory"), before["inventory"])
        self.assertEqual(ctx.db.load_component(ctx.player_id, "Vitals"), before["vitals"])

    def retry_and_reload(self, ctx, pos):
        _save(ctx, backup=False)
        self.assertFalse(ctx.world.dirty_tiles)
        self.assertNotIn(split_world(pos)[0], ctx.world.cache._pinned)
        self.assertEqual(ctx.db.verify(), [])
        reopened = WorldDatabase.open(ctx.db.path)
        self.addCleanup(reopened.close)
        seed = bytes.fromhex(reopened.get_meta("world_seed"))
        loaded_world = World(WorldGenerator(seed, self.registry,
                                           version=int(reopened.get_meta("worldgen_version"))),
                             self.registry, reopened, auto_hydrology=False)
        self.assertEqual(loaded_world.tile_at(pos).terrain_id, "core:rock")
        self.assertEqual(reopened.load_component(ctx.player_id, "Inventory")["items"],
                         {"core:stone": 5})
        self.assertEqual(reopened.load_component(ctx.player_id, "Vitals")["hp"], 82)
        self.assertEqual(reopened.get_meta("turn"), ctx.sim.turn)
        restored = LivingWorldState.from_dict(reopened.load_sim_state())
        self.assertEqual(restored.clock_minute, ctx.sim.state.clock_minute)
        self.assertEqual(restored.player_name, "After checkpoint")
        self.assertEqual(restored.last_offline_wall_time, reopened.get_meta("last_saved_at"))
        self.assertEqual(restored.last_offline_wall_time, ctx.sim.state.last_offline_wall_time)
        self.assertEqual(reopened.get_meta("worldgen_version"), 3)
        self.assertEqual(reopened.get_meta("save_schema"), 3)

    def test_state_snapshot_failure_preserves_retry_then_reload(self):
        ctx = self.make_context()
        pos, before = self.begin_pending_checkpoint(ctx)
        with patch.object(LivingWorldState, "to_dict", side_effect=ValueError("injected snapshot failure")):
            with self.assertRaisesRegex(ValueError, "snapshot failure"):
                _save(ctx, backup=False)
        self.assert_pending_checkpoint(ctx, pos, before)
        self.retry_and_reload(ctx, pos)

    def test_json_encoding_failure_preserves_retry_then_reload(self):
        ctx = self.make_context()
        pos, before = self.begin_pending_checkpoint(ctx)
        snapshot = ctx.sim.state.to_dict()
        snapshot["unserializable_probe"] = object()
        with patch.object(LivingWorldState, "to_dict", return_value=snapshot):
            with self.assertRaises(TypeError):
                _save(ctx, backup=False)
        self.assert_pending_checkpoint(ctx, pos, before)
        self.retry_and_reload(ctx, pos)

    def test_sql_failure_rolls_back_components_metadata_and_terrain(self):
        ctx = self.make_context()
        pos, before = self.begin_pending_checkpoint(ctx)
        # SQLite itself rejects the write after earlier metadata/components ran.
        ctx.db.connection.execute(
            "CREATE TEMP TRIGGER fail_checkpoint_tile BEFORE INSERT ON tile_deltas "
            "BEGIN SELECT RAISE(ABORT, 'injected tile write failure'); END"
        )
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "tile write failure"):
                _save(ctx, backup=False)
        finally:
            ctx.db.connection.execute("DROP TRIGGER IF EXISTS fail_checkpoint_tile")
        self.assertFalse(ctx.db.connection.in_transaction)
        self.assert_pending_checkpoint(ctx, pos, before)
        self.retry_and_reload(ctx, pos)

    def test_commit_failure_keeps_retry_data_until_successful_commit(self):
        ctx = self.make_context(failing_commit=True)
        pos, before = self.begin_pending_checkpoint(ctx)
        ctx.db.connection.fail_next_commit = True
        with self.assertRaisesRegex(sqlite3.OperationalError, "commit failure"):
            _save(ctx, backup=False)
        self.assertFalse(ctx.db.connection.in_transaction)
        self.assert_pending_checkpoint(ctx, pos, before)
        self.retry_and_reload(ctx, pos)

    def test_backup_failure_preserves_previous_checkpoint_and_retry(self):
        ctx = self.make_context()
        pos, before = self.begin_pending_checkpoint(ctx)
        with patch.object(ctx.db, "backup", side_effect=OSError("injected backup failure")):
            with self.assertRaisesRegex(OSError, "backup failure"):
                _save(ctx)
        self.assert_pending_checkpoint(ctx, pos, before)
        self.retry_and_reload(ctx, pos)

    def test_autosave_does_not_request_full_database_backup(self):
        ctx = self.make_context()
        pos = WorldPos(2, 3)
        ctx.world.set_terrain(pos, "core:rock")
        with patch.object(ctx.db, "backup", side_effect=AssertionError("autosave copied DB")):
            _save(ctx, backup=False)
        self.assertFalse(ctx.world.dirty_tiles)
        self.assertEqual(ctx.db.load_chunk_deltas(split_world(pos)[0])[(2, 3)], "core:rock")

    def test_explicit_backup_retains_previous_checkpoint(self):
        ctx = self.make_context()
        pos, before = self.begin_pending_checkpoint(ctx)
        _save(ctx)
        backup = WorldDatabase.open(ctx.db.path.parent / "backups" / "save-retry.bak1.db")
        self.addCleanup(backup.close)
        self.assertEqual(backup.get_meta("last_saved_at"), before["last_saved_at"])
        self.assertEqual(backup.load_sim_state(), before["state"])
        self.assertNotIn((2, 3), backup.load_chunk_deltas(split_world(pos)[0]))
        self.assertEqual(ctx.db.load_sim_state()["player_name"], "After checkpoint")

    def test_snapshot_is_immutable_and_does_not_clear_edits(self):
        ctx = self.make_context()
        pos = WorldPos(2, 3)
        ctx.world.set_terrain(pos, "core:grass")
        snapshot = ctx.world.snapshot_dirty_tiles()
        with self.assertRaises(TypeError):
            snapshot.tiles[pos] = "core:forest"
        with self.assertRaises(TypeError):
            snapshot.revisions[pos] = 100
        ctx.world.set_terrain(pos, "core:forest")
        self.assertEqual(snapshot.tiles[pos], "core:grass")
        self.assertEqual(ctx.world.dirty_tiles[pos], "core:forest")
        self.assertIn(split_world(pos)[0], ctx.world.cache._pinned)

    def test_acknowledgement_retains_newer_edit(self):
        ctx = self.make_context()
        pos = WorldPos(2, 3)
        ctx.world.set_terrain(pos, "core:grass")
        snapshot = ctx.world.snapshot_dirty_tiles()
        ctx.world.set_terrain(pos, "core:forest")
        ctx.world.acknowledge_dirty_tiles(snapshot)
        self.assertEqual(ctx.world.dirty_tiles, {pos: "core:forest"})
        self.assertIn(split_world(pos)[0], ctx.world.cache._pinned)

    def test_acknowledgement_retains_newer_edit_with_identical_value(self):
        ctx = self.make_context()
        pos = WorldPos(2, 3)
        ctx.world.set_terrain(pos, "core:grass")
        snapshot = ctx.world.snapshot_dirty_tiles()
        ctx.world.set_terrain(pos, "core:forest")
        ctx.world.set_terrain(pos, "core:grass")
        ctx.world.acknowledge_dirty_tiles(snapshot)
        self.assertEqual(ctx.world.dirty_tiles, {pos: "core:grass"})
        self.assertIn(split_world(pos)[0], ctx.world.cache._pinned)

    def test_saved_revision_clears_but_other_dirty_tile_keeps_same_chunk_pinned(self):
        ctx = self.make_context(cache_chunks=1)
        saved = WorldPos(2, 3)
        pending = saved.moved(1, 0)
        key = split_world(saved)[0]
        ctx.world.set_terrain(saved, "core:grass")
        snapshot = ctx.world.snapshot_dirty_tiles()
        ctx.world.set_terrain(pending, "core:rock")
        ctx.db.save_state(turn=ctx.sim.turn, tile_deltas=snapshot.tiles,
                          player_id=ctx.player_id, position=saved, inventory={})
        ctx.world.acknowledge_dirty_tiles(snapshot)
        self.assertEqual(ctx.world.dirty_tiles, {pending: "core:rock"})
        self.assertIn(key, ctx.world.cache._pinned)
        ctx.world.tile_at(WorldPos(CHUNK_SIZE * 2, 3))
        self.assertIsNotNone(ctx.world.cache.peek(key))
        self.assertEqual(ctx.world.tile_at(pending).terrain_id, "core:rock")
        _save(ctx, backup=False)
        self.assertNotIn(key, ctx.world.cache._pinned)
        self.assertLessEqual(len(ctx.world.cache), 1)

    def test_two_dirty_chunks_survive_reads_with_single_chunk_capacity(self):
        ctx = self.make_context(cache_chunks=1)
        first = WorldPos(2, 3)
        second = first.moved(CHUNK_SIZE, 0)
        ctx.world.set_terrain(first, "core:rock")
        ctx.world.set_terrain(second, "core:forest")
        self.assertEqual(ctx.world.tile_at(first).terrain_id, "core:rock")
        self.assertEqual(ctx.world.tile_at(second).terrain_id, "core:forest")
        self.assertEqual(len(ctx.world.cache), 2)
        _save(ctx, backup=False)
        self.assertFalse(ctx.world.cache._pinned)
        self.assertLessEqual(len(ctx.world.cache), 1)
        ctx.world.tile_at(WorldPos(CHUNK_SIZE * 3, 3))
        self.assertEqual(ctx.world.tile_at(first).terrain_id, "core:rock")
        self.assertEqual(ctx.world.tile_at(second).terrain_id, "core:forest")

    def test_edit_during_save_is_not_acknowledged_and_retry_saves_newer_value(self):
        ctx = self.make_context()
        pos = WorldPos(2, 3)
        ctx.world.set_terrain(pos, "core:grass")
        save_state = ctx.db.save_state

        def write_then_edit(**kwargs):
            save_state(**kwargs)
            ctx.world.set_terrain(pos, "core:forest")

        with patch.object(ctx.db, "save_state", side_effect=write_then_edit):
            _save(ctx, backup=False)
        self.assertEqual(ctx.db.load_chunk_deltas(split_world(pos)[0])[(2, 3)], "core:grass")
        self.assertEqual(ctx.world.dirty_tiles, {pos: "core:forest"})
        self.assertIn(split_world(pos)[0], ctx.world.cache._pinned)
        _save(ctx, backup=False)
        self.assertFalse(ctx.world.dirty_tiles)
        self.assertEqual(ctx.db.load_chunk_deltas(split_world(pos)[0])[(2, 3)], "core:forest")

    def test_backup_callback_cannot_mutate_captured_components_or_nested_state(self):
        ctx = self.make_context()
        inventory = ctx.entities.get(ctx.player_id, Inventory)
        vitals = ctx.entities.get(ctx.player_id, Vitals)
        ctx.sim.state.learned_regions["0,0"] = {"settlement_name": "Captured village"}
        backup = ctx.db.backup

        def mutate_after_capture(max_backups):
            inventory.add("core:stone", 8)
            vitals.hp = 12
            ctx.sim.state.learned_regions["0,0"]["settlement_name"] = "Later village"
            return backup(max_backups)

        with patch.object(ctx.db, "backup", side_effect=mutate_after_capture):
            _save(ctx)
        self.assertEqual(ctx.db.load_component(ctx.player_id, "Inventory")["items"], {"core:stone": 2})
        self.assertEqual(ctx.db.load_component(ctx.player_id, "Vitals")["hp"], 85)
        self.assertEqual(ctx.db.load_sim_state()["learned_regions"]["0,0"]["settlement_name"],
                         "Captured village")
        self.assertEqual(inventory.count("core:stone"), 10)
        self.assertEqual(vitals.hp, 12)
        self.assertEqual(ctx.sim.state.learned_regions["0,0"]["settlement_name"], "Later village")

    def test_failed_chunk_load_does_not_leave_an_unnecessary_pin(self):
        ctx = self.make_context(cache_chunks=1)
        pos = WorldPos(CHUNK_SIZE * 4, 3)
        key = split_world(pos)[0]
        with patch.object(ctx.world.cache, "loader", side_effect=OSError("injected chunk load failure")):
            with self.assertRaisesRegex(OSError, "chunk load failure"):
                ctx.world.set_terrain(pos, "core:rock")
        self.assertNotIn(key, ctx.world.cache._pinned)
        self.assertFalse(ctx.world.dirty_tiles)

    def test_legacy_schema_migration_preserves_terrain_and_missing_field_defaults(self):
        for schema in (1, 2):
            with self.subTest(schema=schema):
                ctx = self.make_context()
                pos = WorldPos(2, 3)
                ctx.world.set_terrain(pos, "core:rock")
                ctx.db.save_state(turn=3, tile_deltas={pos: "core:rock"},
                                  player_id=ctx.player_id, position=pos,
                                  inventory={"core:stone": 2},
                                  sim_state={"clock_minute": 495})
                ctx.db.set_meta("save_schema", schema)
                for name in ("hydrology_version", "hydrology_morphology_version",
                             "coast_morphology_version", "settlement_plan_version", "routegen_version"):
                    ctx.db.connection.execute("DELETE FROM world_meta WHERE key=?", (name,))
                ctx.db.connection.commit()
                ctx.db.close()
                reopened = WorldDatabase.open(ctx.db.path)
                self.addCleanup(reopened.close)
                self.assertEqual(reopened.get_meta("save_schema"), 3)
                self.assertEqual(reopened.get_meta("worldgen_version"), 3)
                self.assertEqual(reopened.get_meta("hydrology_version"), 1)
                self.assertEqual(reopened.get_meta("hydrology_morphology_version"), 1)
                self.assertEqual(reopened.get_meta("coast_morphology_version"), 0)
                self.assertEqual(reopened.get_meta("routegen_version"), 1)
                self.assertEqual(reopened.load_chunk_deltas(split_world(pos)[0])[(2, 3)], "core:rock")
                state = LivingWorldState.from_dict(reopened.load_sim_state())
                self.assertEqual(state.clock_minute, 495)
                self.assertEqual(state.last_offline_wall_time, 0.0)
                self.assertEqual(state.discovered_tiles, [])
                self.assertEqual(reopened.verify(), [])


if __name__ == "__main__":
    unittest.main()
