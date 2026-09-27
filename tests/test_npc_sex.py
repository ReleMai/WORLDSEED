"""NPC identity survives old saves and selects a matching authored sprite."""
import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

from worldseed.systems.names import npc_sex_for_identity
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.presentation.visuals import VisualRegistry
from worldseed.ui.pygame_terminal import PygameTerminal


def npc(uid='npc:1',name='Mara Vale',sex=''):
    return NPCState(uid,name,29,'farmer',[],2,3,0,'settlement:1','faction:1',sex=sex)


class NPCSexTests(unittest.TestCase):
    def test_new_identity_uses_name_and_stable_ambiguous_fallback(self):
        self.assertEqual(npc().sex,'female')
        self.assertEqual(npc(name='Alden Ward').sex,'male')
        self.assertEqual(npc(uid='npc:ambiguous',name='Rowan Ash').sex,
                         npc_sex_for_identity('Rowan Ash','npc:ambiguous'))
        self.assertEqual(npc(name='Mara Vale',sex='male').sex,'male')

    def test_legacy_npcs_gain_sex_once_and_roundtrip_without_mutating_identity(self):
        old=LivingWorldState()
        old.npcs={'npc:1':npc(),'npc:2':npc('npc:2','Cass Rook')}
        raw=old.to_dict()
        for row in raw['npcs'].values():row.pop('sex')
        first=LivingWorldState.from_dict(raw)
        second=LivingWorldState.from_dict(raw)
        self.assertEqual({key:n.sex for key,n in first.npcs.items()},
                         {key:n.sex for key,n in second.npcs.items()})
        self.assertEqual(first.npcs['npc:1'].sex,'female')
        self.assertEqual(first.npcs['npc:1'].name,'Mara Vale')
        self.assertEqual(first.npcs['npc:1'].uid,'npc:1')
        self.assertEqual(first.npcs['npc:1'].x,2)
        self.assertEqual(first.to_dict()['npcs']['npc:1']['sex'],'female')
        self.assertEqual(LivingWorldState.from_dict(first.to_dict()).npcs['npc:2'].sex,
                         first.npcs['npc:2'].sex)

    def test_authored_rosters_and_renderer_match_persisted_sex(self):
        visuals=VisualRegistry.load_default()
        self.assertEqual(len(visuals.npc_paths()),24)
        self.assertEqual(len(visuals.npc_paths('male')),12)
        self.assertEqual(len(visuals.npc_paths('female')),12)
        self.assertFalse(set(visuals.npc_paths('male')) & set(visuals.npc_paths('female')))
        self.assertTrue(all(path.is_file() for path in visuals.npc_paths()))
        if not PygameTerminal.available():return
        terminal=PygameTerminal()
        male=npc(uid='npc:1',sex='male');female=npc(uid='npc:1',sex='female')
        self.assertIn(terminal._npc_sprite_path(male),visuals.npc_paths('male'))
        self.assertIn(terminal._npc_sprite_path(female),visuals.npc_paths('female'))
        self.assertEqual(terminal._npc_sprite_path(female),terminal._npc_sprite_path(female))


if __name__=='__main__':unittest.main()
