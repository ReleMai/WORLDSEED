"""Gameplay illumination, target visibility, and non-generating light reads."""
import unittest
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.illumination import (
    Q, detection_scale, indoor_actor_visible, indoor_light, indoor_line_clear,
    indoor_sources, interior_ambient, light_description, outdoor_light,
    outdoor_sources, source_strength, LightSource,
)
from worldseed.systems.interior_state import (
    InteriorActor, InteriorFurniture, InteriorPlan, InteriorRect,
)
from worldseed.systems.state import FireCell, LivingWorldState, NPCState, pos_key
from worldseed.systems.stealth import StealthSystem


class LightingTests(unittest.TestCase):
    def plan(self):
        return InteriorPlan("interior:test","home:test","door:test",10,10,0,14000,12000)

    def test_clock_day_is_brighter_than_night_indoors_and_out(self):
        plan=self.plan()
        self.assertGreater(indoor_light(plan,6000,5000,720),indoor_light(plan,6000,5000,0))
        self.assertGreater(outdoor_light(None,720,WorldPos(0,0)),outdoor_light(None,0,WorldPos(0,0)))
        self.assertEqual(outdoor_light(None,720,WorldPos(0,0,-1)),1500)

    def test_weather_ambient_is_consumed_without_fake_daylight(self):
        plan=self.plan()
        env=SimpleNamespace(visual_conditions=lambda minute,pos:({},SimpleNamespace(ambient_light=5000)))
        self.assertEqual(interior_ambient(env,720,plan),5000)
        self.assertEqual(indoor_light(plan,6000,5000,720,ambient_light=5000),1100)
        self.assertEqual(outdoor_light(env,720,WorldPos(0,0)),5000)

    def test_lamp_falloff_and_wall_occlusion(self):
        plan=self.plan()
        lamp=InteriorFurniture("fixture:lamp","core:lamp_stand_piece",1600,1600,800,800)
        plan.furniture=[lamp]
        lit=indoor_light(plan,2500,2000,0)
        dark=indoor_light(plan,8000,2000,0)
        self.assertGreater(lit,dark)
        plan.walls=[InteriorRect(2250,0,120,12000)]
        self.assertEqual(indoor_light(plan,2500,2000,0),dark)
        self.assertFalse(indoor_line_clear(plan,2000,2000,2500,2000))

    def test_wall_opening_transmits_light_but_unbroken_wall_does_not(self):
        plan=self.plan()
        plan.walls=[InteriorRect(6000,0,100,3500),InteriorRect(6000,4500,100,7500)]
        self.assertTrue(indoor_line_clear(plan,3000,4000,9000,4000))
        self.assertFalse(indoor_line_clear(plan,3000,2000,9000,2000))
        self.assertTrue(indoor_line_clear(plan,3000,2000,3000,8000))
        self.assertFalse(indoor_line_clear(plan,6050,2000,6050,8000))

    def test_source_order_is_stable_and_samples_do_not_mutate_plan(self):
        plan=self.plan()
        plan.furniture=[InteriorFurniture("b","core:brazier_piece",2000,2000,600,600),
                        InteriorFurniture("a","core:lamp_stand_piece",3000,3000,600,600)]
        before=plan.to_dict()
        first=indoor_light(plan,3500,3500,720)
        sources=indoor_sources(plan)
        self.assertEqual(tuple(s.uid for s in sources),("a","b"))
        self.assertEqual(plan.to_dict(),before)
        plan.furniture.reverse()
        self.assertEqual(indoor_light(plan,3500,3500,720),first)

    def test_fire_extinguishing_and_fuel_change_actual_light(self):
        state=LivingWorldState()
        key=pos_key(2,1,0)
        state.fires[key]=FireCell(2,1,0,80,3)
        pos=WorldPos(2,1)
        lit=outdoor_light(None,0,pos,state=state)
        self.assertGreater(lit,outdoor_light(None,0,WorldPos(20,20),state=state))
        state.fires[key].fuel=0
        self.assertEqual(outdoor_light(None,0,pos,state=state),outdoor_light(None,0,pos))
        state.fires[key].fuel=3;state.fires[key].intensity=0
        self.assertFalse(outdoor_sources(state,pos))

    def test_local_fire_queries_do_not_scan_world_or_call_terrain(self):
        class KeyedOnly(dict):
            def values(self):raise AssertionError("Global fire scan")
            def items(self):raise AssertionError("Global fire scan")
            def __iter__(self):raise AssertionError("Global fire scan")
        fires=KeyedOnly({pos_key(0,0,0):FireCell(0,0,0,50,5)})
        state=SimpleNamespace(fires=fires)
        self.assertEqual(len(outdoor_sources(state,WorldPos(0,0))),1)
        self.assertGreater(outdoor_light(None,0,WorldPos(0,0),state=state),6500)

    def test_fire_occlusion_uses_supplied_physical_line_authority(self):
        source=(LightSource(0,0,6,50000),)
        ambient=outdoor_light(None,0,WorldPos(2,0),sources=())
        self.assertEqual(outdoor_light(None,0,WorldPos(2,0),sources=source,clear_line=lambda *_:False),ambient)
        self.assertGreater(outdoor_light(None,0,WorldPos(2,0),sources=source,clear_line=lambda *_:True),ambient)

    def test_light_and_detection_are_bounded_and_monotonic(self):
        self.assertEqual(detection_scale(Q),Q)
        for light in (0,1000,9000,24000,48000,Q):
            self.assertGreaterEqual(detection_scale(light),1)
            self.assertLessEqual(detection_scale(light),Q)
            self.assertLess(detection_scale(light,True,4),detection_scale(light))
        self.assertLess(detection_scale(5000,True,8),detection_scale(5000,True,0))
        self.assertLess(detection_scale(5000),detection_scale(50000))
        self.assertEqual([light_description(v) for v in (0,12000,30000,60000)],["Dark","Dim","Lit","Bright"])
        source=LightSource(0,0,6000,50000)
        self.assertEqual(source_strength(source,6000,0),0)
        self.assertGreater(source_strength(source,1000,0),source_strength(source,4000,0))

    def test_indoor_player_cannot_see_actors_through_walls_or_deep_darkness(self):
        plan=self.plan()
        # Outdoor daylight is attenuated to diffuse indoor light. A genuinely
        # bright room needs an installed lamp, not an unlit-room assumption.
        plan.furniture=[InteriorFurniture("lamp","core:lamp_stand_piece",6600,2600,800,800)]
        self.assertTrue(indoor_actor_visible(plan,1000,3000,7000,3000,720,ambient_light=Q))
        plan.furniture.clear()
        self.assertFalse(indoor_actor_visible(plan,1000,3000,7000,3000,0,ambient_light=5000))
        plan.furniture=[InteriorFurniture("lamp","core:lamp_stand_piece",6600,2600,800,800)]
        plan.walls=[InteriorRect(5000,0,80,12000)]
        self.assertFalse(indoor_actor_visible(plan,1000,3000,7000,3000,720,ambient_light=Q))


class LightingPerceptionTests(unittest.TestCase):
    def fixture(self,ambient):
        state=LivingWorldState()
        npc=NPCState("npc:guard","Guard",30,"guard",[],0,0,0,"town","",facing_dx=1,facing_dy=0)
        state.npcs[npc.uid]=npc
        env=SimpleNamespace(visual_conditions=lambda minute,pos:({"visibility":8,"fog":0},SimpleNamespace(ambient_light=ambient)))
        world=SimpleNamespace(tile_at=lambda pos:SimpleNamespace(terrain=SimpleNamespace(blocks_sight=False)))
        physical=SimpleNamespace(clears_natural_feature=lambda pos:False,cell_at=lambda pos:None)
        building=SimpleNamespace(blocks_sight=lambda pos:False)
        resources=SimpleNamespace(blocks_sight=lambda pos:False)
        return state,npc,StealthSystem(state,b"light-test",world,resources,building,physical,env)

    def test_darkness_and_stalk_change_the_same_outdoor_witness_path(self):
        state,npc,stealth=self.fixture(Q)
        target=WorldPos(8,0)
        self.assertTrue(stealth.can_see(npc,target,720))
        self.assertEqual(stealth.witnesses(target,720),(npc.uid,))
        state.player_stealth_mode=True;state.player_skills["stealth"]=4
        self.assertFalse(stealth.can_see(npc,target,720))
        self.assertFalse(stealth.witnesses(target,720))
        state,npc,stealth=self.fixture(5000)
        self.assertFalse(stealth.can_see(npc,WorldPos(4,0),0))
        self.assertFalse(stealth.witnesses(WorldPos(4,0),0))
        self.assertTrue(stealth.can_see(npc,WorldPos(1,0),0))

    def test_target_fire_reveals_target_even_when_observer_remains_dark(self):
        state,npc,stealth=self.fixture(5000)
        target=WorldPos(6,0)
        self.assertFalse(stealth.can_see(npc,target,0))
        state.fires[pos_key(6,0,0)]=FireCell(6,0,0,100,10)
        self.assertTrue(stealth.can_see(npc,target,0))
        self.assertEqual(stealth.witnesses(target,0),(npc.uid,))

    def test_installed_indoor_lamp_changes_witnessing_not_the_clock_or_plan(self):
        state,npc,stealth=self.fixture(5000)
        plan=InteriorPlan("interior:test","home:test","door:test",0,0,0,16000,12000)
        actor=InteriorActor(plan.uid,1000,5000)
        player=InteriorActor(plan.uid,7000,5000)
        state.interiors[plan.uid]=plan;state.interior_actors={npc.uid:actor,"player":player}
        interiors=SimpleNamespace(player_presence=lambda:player,current_plan=lambda:plan,
            actors_in_space=lambda uid:tuple(state.interior_actors.items()),room_at=lambda *_:None)
        stealth.attach_interior_system(interiors)
        self.assertFalse(stealth.witnesses(WorldPos(0,0),0))
        plan.furniture=[InteriorFurniture("fixture:lamp","core:lamp_stand_piece",6600,4600,800,800)]
        before=state.to_dict()
        self.assertEqual(stealth.witnesses(WorldPos(0,0),0),(npc.uid,))
        self.assertEqual(state.to_dict(),before)
        plan.walls=[InteriorRect(4000,0,100,12000)]
        self.assertFalse(stealth.witnesses(WorldPos(0,0),0))

    def test_sightline_does_not_load_missing_chunks(self):
        _,_,stealth=self.fixture(Q)
        stealth.world=SimpleNamespace(cache=SimpleNamespace(peek=lambda key:None),
            tile_at=lambda *_:self.fail("Sight must not generate/load missing terrain"))
        self.assertFalse(stealth.visible_from(WorldPos(0,0),WorldPos(4,0)))

    def test_repeated_unchanged_snapshots_use_local_observer_buckets(self):
        class Counted(dict):
            reads=0
            def values(self):
                self.reads+=1
                return super().values()
        state,npc,stealth=self.fixture(Q)
        state.npcs=Counted(state.npcs)
        # Explicit preparation is simulation-owned. Repeated UI snapshots only
        # query these references; they cannot rebuild a population-wide index.
        prepared=tuple(state.npcs.values())
        stealth.attach_observer_query(lambda pos,radius:prepared)
        stealth.snapshot(WorldPos(5,0),720)
        initial=state.npcs.reads
        stealth.snapshot(WorldPos(6,0),720)
        stealth.snapshot(WorldPos(7,0),720)
        self.assertEqual(state.npcs.reads,initial)
        self.assertEqual(initial,1)

    def test_large_far_population_is_not_iterated_by_render_queries(self):
        from worldseed.systems.ai import NPCSystem
        state,npc,stealth=self.fixture(Q)
        for i in range(200):
            uid="npc:far:"+str(i)
            state.npcs[uid]=NPCState(uid,"Far",30,"guard",[],10000+i*16,10000,0,"far","",facing_dx=1)
        ai=NPCSystem(state,b"spatial-light",SimpleNamespace())
        stealth.attach_observer_query(ai.nearby_npcs)
        class NoScan(dict):
            def values(self):raise AssertionError("Renderer iterated all NPCs")
            def items(self):raise AssertionError("Renderer iterated all NPCs")
            def __iter__(self):raise AssertionError("Renderer iterated all NPCs")
        state.npcs=NoScan(state.npcs)
        self.assertEqual(stealth.witnesses(WorldPos(5,0),720),(npc.uid,))
        self.assertEqual(ai.nearby_npcs(WorldPos(5,0),24),(npc,))

    def test_simulation_existing_iteration_updates_actor_bucket_after_movement(self):
        from worldseed.systems.ai import NPCSystem
        state,npc,_=self.fixture(Q)
        ai=NPCSystem(state,b"spatial-light",SimpleNamespace())
        for actor in ai._indexed_npcs():
            actor.x=80
        self.assertFalse(ai.nearby_npcs(WorldPos(0,0),24))
        self.assertEqual(ai.nearby_npcs(WorldPos(80,0),24),(npc,))

    def test_indoor_hearing_uses_actor_positions_not_shared_exterior_anchor(self):
        from tests.test_interior_security import InteriorSecurityTests
        state,plan,npc,stealth,security,door=InteriorSecurityTests().fixture()
        state.interior_actors["player"].x=11000
        state.interior_actors[npc.uid].x=1000
        plan.walls=[InteriorRect(6000,0,100,12000)]
        # Both NPC exterior coordinates still equal the portal; a distant
        # resident behind a wall must not hear quiet lockpicking at that anchor.
        self.assertFalse(security._witnesses(door,WorldPos(10,10),0,stealth,noise_radius=1))
        state.interior_actors[npc.uid].x=10500
        self.assertEqual(security._witnesses(door,WorldPos(10,10),0,stealth,noise_radius=1),(npc.uid,))


if __name__=="__main__":unittest.main()
