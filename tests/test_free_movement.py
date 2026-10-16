from __future__ import annotations

import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.free_movement import SPRINT_SPEED, WALK_SPEED, update_npcs_free, update_player_free
from worldseed.systems.state import LivingWorldState, NPCState


class _PlayerSim:
    def __init__(self, *, blocked: bool = False):
        self.state=SimpleNamespace(player_fx=0.5,player_fy=0.5,player_facing_dx=0,player_facing_dy=0)
        self._pos=WorldPos(0,0,0);self.blocked=blocked;self.step_calls=0
    @property
    def player_pos(self):return self._pos
    def try_free_movement_step(self,dx:int,dy:int,*,fx=0.5,fy=0.5)->bool:
        self.step_calls+=1
        if self.blocked:return False
        self._pos=self._pos.moved(dx,dy);return True


class _NpcController:
    continuous_motion_enabled=True
    @staticmethod
    def movement_passable(npc,pos,minute):return True
    @staticmethod
    def _face_step(npc,old_x,old_y):
        npc.facing_dx=0 if npc.x==old_x else (1 if npc.x>old_x else -1)
        npc.facing_dy=0 if npc.y==old_y else (1 if npc.y>old_y else -1)
    @staticmethod
    def _index_npc(npc):return None


class FreeMovementTests(unittest.TestCase):
    def test_walk_and_sprint_use_realtime_subtile_distance(self):
        walk=_PlayerSim();sprint=_PlayerSim()
        self.assertTrue(update_player_free(walk,0.1,1.0,0.0,False))
        self.assertTrue(update_player_free(sprint,0.1,1.0,0.0,True))
        self.assertAlmostEqual(walk.state.player_fx,0.5+WALK_SPEED*0.1,places=6)
        self.assertAlmostEqual(sprint.state.player_fx,0.5+SPRINT_SPEED*0.1,places=6)

    def test_tile_crossing_uses_authoritative_step_and_block_is_latched(self):
        sim=_PlayerSim(blocked=True);sim.state.player_fx=0.95
        update_player_free(sim,0.1,1.0,0.0,False)
        self.assertEqual(sim.player_pos,WorldPos(0,0,0));self.assertEqual(sim.step_calls,1)
        self.assertAlmostEqual(sim.state.player_fx,0.999)
        update_player_free(sim,0.1,1.0,0.0,False);self.assertEqual(sim.step_calls,1)
        update_player_free(sim,0.05,-1.0,0.0,False);sim.blocked=False
        update_player_free(sim,0.1,1.0,0.0,False);self.assertGreaterEqual(sim.step_calls,2)

    def test_successful_crossing_preserves_fractional_progress(self):
        sim=_PlayerSim();sim.state.player_fx=0.95
        update_player_free(sim,0.1,1.0,0.0,False)
        self.assertEqual(sim.player_pos,WorldPos(1,0,0))
        self.assertAlmostEqual(sim.state.player_fx,0.13,places=6)

    def test_npc_cached_path_advances_continuously(self):
        npc=NPCState(uid="npc:test",name="Walker",age=30,occupation="farmer",traits=[],x=0,y=0,z=0,
                     settlement_id="settlement:test",faction_id="faction:test",
                     tasks=[{"kind":"move","x":1,"y":0,"z":0,"exact":True,"_local_path":[[1,0]]}])
        sim=SimpleNamespace(state=SimpleNamespace(npcs={npc.uid:npc},interior_actors={}),
                            npcs=_NpcController(),clock=SimpleNamespace(minute=600))
        self.assertTrue(update_npcs_free(sim,0.1));self.assertGreater(npc.fx,0.5)
        for _ in range(8):update_npcs_free(sim,0.1)
        self.assertEqual((npc.x,npc.y),(1,0));self.assertGreaterEqual(npc.fx,0.0);self.assertLess(npc.fx,1.0)

    def test_fractional_positions_round_trip_without_schema_bump(self):
        state=LivingWorldState(player_fx=0.23,player_fy=0.81)
        npc=NPCState(uid="npc:persist",name="Persist",age=27,occupation="guard",traits=[],x=4,y=5,z=0,
                     settlement_id="settlement:test",faction_id="faction:test",fx=0.17,fy=0.76)
        state.npcs[npc.uid]=npc
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertAlmostEqual(restored.player_fx,0.23);self.assertAlmostEqual(restored.player_fy,0.81)
        self.assertAlmostEqual(restored.npcs[npc.uid].fx,0.17);self.assertAlmostEqual(restored.npcs[npc.uid].fy,0.76)


if __name__=="__main__":
    unittest.main()
