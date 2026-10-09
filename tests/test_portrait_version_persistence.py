"""Saved people retain their face catalog while new people gain more features."""
from __future__ import annotations

import copy
from dataclasses import asdict
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from tests import test_dev50_npc_introductions as introductions
from worldseed.app import _conversation_menu, _npc_portrait, _npc_profile_data
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.persistence.validation import validate_sim_state
from worldseed.presentation.portraits import portrait_spec, render_portrait
from worldseed.systems.state import LivingWorldState, NPCState


SEED = b'portrait-version-world'


def npc(uid='npc:legacy:one', *, sex='male', age=35):
    return NPCState(uid, 'Eda Vale', age, 'healer', [], 1, 0, 0, '', '', sex=sex)


def legacy_state() -> dict:
    row = asdict(npc())
    del row['portrait_version']
    return {'clock_minute': 600, 'npcs': {row['uid']: row}}


def write_representative_save(path: Path) -> LivingWorldState:
    """Exercise an old missing-field checkpoint followed by a mixed new save."""
    db = WorldDatabase.create(path, 'Portrait version migration', SEED.hex())
    try:
        db.save_state(turn=0, tile_deltas={}, player_id=1, position=WorldPos(0, 0, 0),
                      inventory={}, sim_state=legacy_state())
    finally:
        db.close()
    db = WorldDatabase.open(path)
    try:
        state = LivingWorldState.from_dict(db.load_sim_state())
        modern = npc('npc:modern', sex='female', age=42)
        state.npcs[modern.uid] = modern
        db.save_state(turn=0, tile_deltas={}, player_id=1, position=WorldPos(0, 0, 0),
                      inventory={}, sim_state=state.to_dict())
        return state
    finally:
        db.close()


class PortraitVersionPersistenceTests(unittest.TestCase):
    def test_new_npcs_use_latest_catalog_and_roundtrip_explicit_pin(self):
        person = npc()
        self.assertEqual(person.portrait_version, 2)
        state = LivingWorldState()
        state.npcs[person.uid] = person
        restored = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.npcs[person.uid].portrait_version, 2)
        self.assertEqual(restored.to_dict(), state.to_dict())

    def test_missing_legacy_field_loads_v1_without_mutating_input(self):
        raw = legacy_state()
        before = copy.deepcopy(raw)
        state = LivingWorldState.from_dict(raw)
        self.assertEqual(raw, before)
        self.assertEqual(state.npcs['npc:legacy:one'].portrait_version, 1)
        serialized = state.to_dict()
        self.assertEqual(serialized['npcs']['npc:legacy:one']['portrait_version'], 1)
        self.assertEqual(LivingWorldState.from_dict(serialized).to_dict(), serialized)

    def test_mixed_catalog_checkpoint_reopens_with_same_faces_and_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'portrait-version.db'
            state = write_representative_save(path)
            before = state.to_dict()
            expected = {uid: _npc_portrait(SimpleNamespace(seed=SEED), person)
                        for uid, person in state.npcs.items()}
            db = WorldDatabase.open(path)
            try:
                self.assertEqual(db.verify(), [])
                restored = LivingWorldState.from_dict(db.load_sim_state())
            finally:
                db.close()
            self.assertEqual(state.to_dict(), before)
            self.assertEqual(restored.to_dict(), before)
            self.assertEqual(restored.clock_minute, 600)
            self.assertEqual({uid: _npc_portrait(SimpleNamespace(seed=SEED), person)
                              for uid, person in restored.npcs.items()}, expected)
            self.assertEqual({person.portrait_version for person in restored.npcs.values()}, {1, 2})

    def test_verifier_accepts_legacy_and_supported_pins_and_rejects_bad_versions(self):
        raw = legacy_state()
        self.assertEqual(validate_sim_state(raw), [])
        person = raw['npcs']['npc:legacy:one']
        for version in (1, 2):
            person['portrait_version'] = version
            self.assertEqual(validate_sim_state(raw), [])
        for version in (True, False, 0, -1, 3, 1.0, '1', None):
            with self.subTest(version=version):
                person['portrait_version'] = version
                self.assertIn('invalid NPC portrait version: npc:legacy:one', validate_sim_state(raw))

    def test_app_missing_version_fallback_uses_legacy_catalog(self):
        person = SimpleNamespace(uid='npc:legacy:one', sex='male', age=35)
        actual = _npc_portrait(SimpleNamespace(seed=SEED), person)
        self.assertEqual(actual.version, 1)
        self.assertEqual(actual, portrait_spec(SEED, person.uid, person.sex, person.age, version=1))


class PortraitVersionConversationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def test_chat_and_profile_observe_each_saved_catalog_without_disclosing_identity(self):
        for version in (1, 2):
            with self.subTest(version=version):
                fixture = introductions.NPCIntroductionTests()
                fixture.registry = self.registry
                sim, person, ctx = fixture.fixture()
                person.portrait_version = version
                # A save/reload must retain the version used by both screens.
                sim.state = LivingWorldState.from_dict(sim.state.to_dict())
                person = sim.state.npcs[person.uid]
                before = sim.state.to_dict()
                term = introductions.RecordingTerm(['UI_ACTION:inspect', 'ESC', 'ESC'])
                _conversation_menu(ctx, term, person)
                chat = next(frame[4]['data'] for frame in term.frames if frame[0] == 'npc_dialogue')
                profile = next(frame[4]['data'] for frame in term.frames if frame[0] == 'npc_profile')
                self.assertEqual(chat['portrait'].version, version)
                self.assertEqual(chat['portrait'], profile['portrait'])
                self.assertEqual(profile['portrait'], _npc_profile_data(sim, person, 'appearance')['portrait'])
                self.assertEqual(chat['speaker'], 'Stranger')
                self.assertEqual(profile['summary']['name'], 'Stranger')
                self.assertNotIn(person.name, str(term.frames))
                self.assertEqual(sim.state.to_dict(), before)
                sim._advance_time.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'requires pygame-ce')
class LegacyPortraitPixelTests(unittest.TestCase):
    def test_saved_v1_faces_preserve_dev61_pixels_after_load_and_save(self):
        import pygame
        expected = (
            ('npc:legacy:one', 'male', 35,
             '0b32ffb0c83a3e498fcaf7faf793ae1d6cedf1aeb6cbb69d53857af7cc5b97e4'),
            ('npc:legacy:two', 'female', 70,
             'd9291d81f90d6ca3efda40049440e98cc94badedb7c57ac81f5a7d32fa65f765'),
            ('npc:legacy:three', 'female', 12,
             '8b72559ef5ee4e1912233dedba6b0da6c2cc675db2fc148952d19a96b18950a6'),
        )
        rows = {}
        for uid, sex, age, _ in expected:
            row = asdict(npc(uid, sex=sex, age=age))
            del row['portrait_version']
            rows[uid] = row
        state = LivingWorldState.from_dict({'npcs': rows})
        state = LivingWorldState.from_dict(state.to_dict())
        for uid, _, _, pixel_hash in expected:
            with self.subTest(uid=uid):
                spec = _npc_portrait(SimpleNamespace(seed=SEED), state.npcs[uid])
                pixels = pygame.image.tobytes(render_portrait(spec, 96), 'RGBA')
                self.assertEqual(hashlib.sha256(pixels).hexdigest(), pixel_hash)


if __name__ == '__main__':
    unittest.main()
