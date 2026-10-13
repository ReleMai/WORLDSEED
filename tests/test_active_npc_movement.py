"""Bounded graphical locomotion preserves simulation actor/collision order."""
from types import SimpleNamespace
import unittest

from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.free_movement import update_npcs_free
from worldseed.systems.lod import LODSystem
from worldseed.systems.state import LivingWorldState, NPCState


class _NoPopulationScan(dict):
    def values(self):raise AssertionError("whole population values scan")
    def items(self):raise AssertionError("whole population items scan")
    def __iter__(self):raise AssertionError("whole population iteration")


def _walker(uid, x=0, y=0, z=0, *, dx=1):
    return NPCState(uid, "Walker", 30, "farmer", [], x, y, z,
                    "settlement:test", "faction:test", tasks=[{
                        "kind":"move", "x":x+dx, "y":y, "z":z,
                        "exact":True, "_local_path":[[x+dx,y]],
                        "_local_path_goal":[x+dx,y,z]}])


def _fixture(*actors):
    state=LivingWorldState()
    state.npcs={npc.uid:npc for npc in actors}
    controller=NPCSystem(state,b"active-npc-test",SimpleNamespace(record=lambda *a:None),
                         world=SimpleNamespace(is_passable=lambda pos:True),lod=LODSystem(state))
    controller.continuous_motion_enabled=True
    return SimpleNamespace(state=state,npcs=controller,player_pos=WorldPos(0,0,0),
                           clock=SimpleNamespace(minute=600))


class ActiveNPCMovementTests(unittest.TestCase):
    def test_distant_population_is_never_enumerated_by_frame_update(self):
        local=_walker("local")
        sim=_fixture(local,*(_walker(f"distant:{i}",x=10000+i*16) for i in range(10000)))
        sim.state.npcs=_NoPopulationScan(sim.state.npcs)
        self.assertTrue(update_npcs_free(sim,0.1))
        self.assertAlmostEqual(local.fx,0.68)
        self.assertEqual(sim.state.npcs["distant:0"].fx,0.5)

    def test_collision_contenders_keep_authoritative_insertion_order(self):
        first=_walker("npc:z-first",x=0)
        second=_walker("npc:a-second",x=2,dx=-1)
        first.fx=0.95;second.fx=0.05
        sim=_fixture(first,second)
        self.assertEqual(tuple(n.uid for n in sim.npcs.continuous_movement_npcs(sim.player_pos)),
                         (first.uid,second.uid))
        self.assertEqual(tuple(n.uid for n in sim.npcs.nearby_npcs(sim.player_pos,4)),
                         (second.uid,first.uid))
        self.assertTrue(update_npcs_free(sim,0.1))
        self.assertEqual((first.x,second.x),(1,2))
        self.assertNotIn("_local_path",second.tasks[0])

    def test_lod_and_cached_route_filters_keep_only_managed_walkers(self):
        immediate=_walker("immediate",x=64)
        paused=_walker("paused",x=65)
        commerce=_walker("commerce",x=256)
        commerce.tasks[0]["commerce_task"]=True
        distant=_walker("distant",x=257)
        distant.tasks[0]["commerce_task"]=True
        idle=_walker("idle",x=4);idle.tasks.clear()
        unplanned=_walker("unplanned",x=3);unplanned.tasks[0].pop("_local_path")
        inside=_walker("inside",x=2)
        dead=_walker("dead",x=1);dead.alive=False
        sim=_fixture(immediate,paused,commerce,distant,idle,unplanned,inside,dead)
        sim.state.interior_actors[inside.uid]=SimpleNamespace(space_id="home")
        self.assertEqual(tuple(n.uid for n in sim.npcs.continuous_movement_npcs(sim.player_pos)),
                         (immediate.uid,commerce.uid))
        self.assertTrue(update_npcs_free(sim,0.1))
        for npc in (paused,distant,idle,unplanned,inside,dead):self.assertEqual(npc.fx,0.5)

    def test_tier_b_profession_routes_include_adjacent_cave_levels(self):
        cave=_walker("cave",x=80,z=-1)
        deeper=_walker("deeper",x=80,z=-2)
        too_deep=_walker("too_deep",x=80,z=-3)
        sim=_fixture(cave,deeper,too_deep)
        sim.npcs.mining=SimpleNamespace(has_active_trip=lambda npc:True)
        sim.state.npcs=_NoPopulationScan(sim.state.npcs)
        self.assertEqual(tuple(n.uid for n in sim.npcs.continuous_movement_npcs(sim.player_pos)),
                         (cave.uid,deeper.uid))
        self.assertTrue(update_npcs_free(sim,0.1))
        self.assertGreater(cave.fx,0.5);self.assertGreater(deeper.fx,0.5)
        self.assertEqual(too_deep.fx,0.5)

    def test_player_lod_transition_reselects_without_rebuilding_population(self):
        near=_walker("near")
        later=_walker("later",x=1000)
        sim=_fixture(near,later)
        sim.state.npcs=_NoPopulationScan(sim.state.npcs)
        update_npcs_free(sim,0.1)
        near_progress=near.fx
        sim.player_pos=WorldPos(1000,0,0)
        update_npcs_free(sim,0.1)
        self.assertEqual(near.fx,near_progress)
        self.assertGreater(later.fx,0.5)

    def test_fixed_tick_queries_local_taskless_actors_without_population_scan(self):
        local=_walker("local");local.tasks.clear();local.home_id="home:local"
        far=_walker("far",x=10000);far.tasks.clear();far.home_id="home:far"
        sim=_fixture(local,far)
        sim.state.settlements[local.settlement_id]=SimpleNamespace(uid=local.settlement_id)
        sim.state.npcs=_NoPopulationScan(sim.state.npcs)
        planned=[]
        sim.npcs.refresh_schedule=lambda *args:None
        def plan(npc,town,minute):
            planned.append(npc.uid)
            npc.tasks=_walker(npc.uid,x=npc.x).tasks
        sim.npcs._choose_goal_and_plan=plan
        sim.npcs.tick_update(605,sim.player_pos)
        self.assertEqual(planned,[local.uid])
        self.assertEqual(local.tasks[0]["_local_path"],[[1,0]])
        self.assertEqual(far.tasks,[])

    def test_fixed_tick_keeps_managed_profession_cave_and_collision_order(self):
        first=_walker("npc:z-first",x=15)
        second=_walker("npc:a-second",x=17,dx=-1)
        cave=_walker("cave",x=80,z=-1)
        for npc in (first,second,cave):npc.home_id="home:existing"
        sim=_fixture(first,second,cave);sim.npcs.continuous_motion_enabled=False
        sim.state.settlements[first.settlement_id]=SimpleNamespace(uid=first.settlement_id)
        sim.npcs.refresh_schedule=lambda *args:None
        sim.npcs.mining=SimpleNamespace(has_active_trip=lambda npc:npc.uid==cave.uid)
        sim.state.npcs=_NoPopulationScan(sim.state.npcs)
        sim.npcs.tick_update(605,sim.player_pos)
        self.assertEqual((first.x,second.x),(16,17))
        self.assertEqual(cave.x,81)
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(81,0,81,0,-1),(cave,))

    def test_no_lod_controller_preserves_managed_profession_other_z(self):
        cave=_walker("cave",x=80,z=-8)
        sim=_fixture(cave);sim.npcs.lod=None
        sim.npcs.mining=SimpleNamespace(has_active_trip=lambda npc:True)
        self.assertEqual(sim.npcs.continuous_movement_npcs(sim.player_pos),(cave,))

    def test_remote_physical_route_still_progresses_on_coarse_execution(self):
        remote=_walker("remote",x=300)
        remote.tasks[0].update(physical_path=True,commerce_task=True)
        sim=_fixture(remote)
        self.assertFalse(update_npcs_free(sim,0.1))
        self.assertEqual(remote.x,300)
        # Coarse AI owns travel after an actor leaves the bounded Tier-B window;
        # it must not cache a route awaiting a graphical frame that excludes it.
        sim.npcs._execute_task(remote,SimpleNamespace(),600,sim.player_pos)
        self.assertEqual(remote.x,301)
        self.assertEqual(remote.tasks,[])

    def test_negative_bucket_crossing_updates_locator_immediately(self):
        npc=_walker("crossing",x=-1);npc.fx=0.95
        sim=_fixture(npc)
        self.assertTrue(update_npcs_free(sim,0.1))
        self.assertEqual(npc.x,0)
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(-1,0,-1,0,0),())
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(0,0,0,0,0),(npc,))
        self.assertNotIn((-1,0,0),sim.npcs._npc_spatial_buckets)

    def test_direct_tick_execution_refreshes_position_and_connector_z(self):
        npc=_walker("tick",x=15)
        sim=_fixture(npc);sim.npcs.continuous_motion_enabled=False
        sim.npcs.execute_tick(npc,SimpleNamespace(),600,sim.player_pos)
        self.assertEqual(npc.x,16)
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(16,0,16,0,0),(npc,))
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(15,0,15,0,0),())
        npc.tasks=[{"kind":"mining_transition"}]
        def descend(actor,task,minute):
            actor.z=-1
            return "completed"
        sim.npcs.mining=SimpleNamespace(transition=descend)
        sim.npcs.execute_tick(npc,SimpleNamespace(),605,sim.player_pos)
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(16,0,16,0,-1),(npc,))
        self.assertNotIn(0,sim.npcs._npc_spatial_level_counts)

    def test_index_refresh_handles_insert_replace_death_and_removal(self):
        original=_walker("first")
        sim=_fixture(original)
        added=_walker("added",x=5)
        sim.state.npcs[added.uid]=added;sim.npcs._index_npc(added)
        replacement=_walker(original.uid,x=20)
        sim.state.npcs[replacement.uid]=replacement;sim.npcs._index_npc(replacement)
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(0,0,30,0,0),(replacement,added))
        replacement.alive=False;sim.npcs._index_npc(replacement)
        self.assertNotIn(replacement.uid,sim.npcs._npc_spatial_positions)
        sim.state.npcs.pop(added.uid);sim.npcs._index_npc(added)
        self.assertEqual(sim.npcs._npc_spatial_buckets,{})
        self.assertEqual(sim.npcs._npc_spatial_level_counts,{})

    def test_rectangle_query_is_observational_and_not_radius_clamped(self):
        npc=_walker("wide",x=300)
        sim=_fixture(npc)
        before=sim.state.to_dict()
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(300,0,300,0,0),(npc,))
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(301,0,300,0,0),())
        self.assertEqual(sim.npcs.indexed_npcs_in_rect(300,0,300,0,-1),())
        self.assertEqual(before,sim.state.to_dict())

    def test_disabled_or_zero_dt_does_not_query_or_move(self):
        npc=_walker("paused")
        sim=_fixture(npc)
        sim.npcs.continuous_movement_npcs=lambda pos:(_ for _ in ()).throw(AssertionError("query"))
        self.assertFalse(update_npcs_free(sim,0))
        sim.npcs.continuous_motion_enabled=False
        self.assertFalse(update_npcs_free(sim,0.1))
        self.assertEqual(npc.fx,0.5)


if __name__=="__main__":unittest.main()
