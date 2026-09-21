import unittest
from unittest.mock import patch
from types import SimpleNamespace
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator,WorldFields,SurfaceCurrent
from worldseed.content.registry import ContentRegistry
from worldseed.config import DATA_DIR
from worldseed.systems.swimming import exposure,stroke_cost
from worldseed.systems.state import LivingWorldState,StructureInstance,pos_key
from worldseed.entities.components import Vitals,Position
from worldseed.sim.commands import MoveCommand,RestCommand,WaitCommand
import test_rc5_gameplay as helpers

class WaterV6Tests(unittest.TestCase):
 def test_coastal_transect_orders_shore_wading_shallow_shelf_deep(self):
  g=WorldGenerator(b'coast',ContentRegistry.load(DATA_DIR),version=6)
  g.sample_fields=lambda p:WorldFields(23800-p.x*100,32000,30000,30000)
  self.assertEqual([g.terrain_at(WorldPos(x,0,0)) for x in [-5,-1,1,6,18,40]],
   ['core:sand','core:shore','core:ocean_wade','core:ocean_shallow','core:ocean_shelf','core:ocean_deep'])
 def test_legacy_ocean_keeps_terrain(self):
  g=WorldGenerator(b'coast',ContentRegistry.load(DATA_DIR),version=5)
  g.sample_fields=lambda p:WorldFields(23700,32000,30000,30000)
  self.assertEqual(g.terrain_at(WorldPos(1,0,0)),'core:water')
 def test_generation_order_is_independent(self):
  reg=ContentRegistry.load(DATA_DIR);a=WorldGenerator(b'water-order',reg,6);b=WorldGenerator(b'water-order',reg,6)
  coords=[WorldPos(x,y,0) for x in range(-100,101,13) for y in range(-100,101,13)]
  forward={p:a.terrain_at(p) for p in coords};reverse={p:b.terrain_at(p) for p in reversed(coords)}
  self.assertEqual(forward,reverse)
 def test_swimming_state_roundtrip_and_old_default(self):
  s=LivingWorldState();s.player_swimming_xp=17;s.player_skills['swimming']=4
  copy=LivingWorldState.from_dict(s.to_dict());self.assertEqual(copy.player_swimming_xp,17);self.assertEqual(copy.player_skills['swimming'],4)
  raw=s.to_dict();del raw['player_swimming_xp'];self.assertEqual(LivingWorldState.from_dict(raw).player_swimming_xp,0)

class SwimmingTests(unittest.TestCase):
 def setUp(self):
  self.td,self.db,self.reg,self.world,self.entities,self.pid,self.sim=helpers.RC5GameplayTests().make_sim(gen_version=5)
  self.addCleanup(self.td.cleanup);self.addCleanup(self.db.close)
  for x in range(-2,5):
   for y in range(-2,3):self.world.set_terrain(WorldPos(x,y,0),'core:sand')
  self.world.set_terrain(WorldPos(1,0,0),'core:ocean_shallow')
  self.world.set_terrain(WorldPos(2,0,0),'core:ocean_deep')
  self.world.set_terrain(WorldPos(3,0,0),'core:ocean_wade')
  self.v=self.entities.get(self.pid,Vitals)
  self.sim.resources.blocks_movement=lambda p:False
  self.world.current_at=lambda *a,**k:None
  # Isolate local locomotion/time accounting from regional NPC/ecology ticks.
  self.sim._post_action=lambda:None
  self.sim._advance_time=self.sim._update_vitals
 def move(self,dx):self.sim.execute(MoveCommand(self.pid,dx,0))
 def test_enter_swim_spends_stamina_and_practices(self):
  self.move(1);self.assertEqual(self.sim.player_pos,WorldPos(1,0,0));self.assertLess(self.v.stamina,95);self.assertEqual(self.sim.state.player_swimming_xp,1)
 def test_exhaustion_can_escape_but_cannot_enter(self):
  self.v.stamina=5;self.move(1);self.assertEqual(self.sim.player_pos.x,0)
  self.entities.get(self.pid,Position).value=WorldPos(2,0,0);self.v.stamina=0;self.move(1)
  self.assertEqual(self.sim.player_pos.x,3)
 def test_wait_and_rest_cannot_restore_stamina_in_water(self):
  self.move(1);self.v.stamina=3;self.sim.execute(RestCommand(self.pid,60));self.assertLess(self.v.stamina,3)
  hp=self.v.hp;self.sim.execute(WaitCommand(self.pid,30));self.assertLess(self.v.hp,hp)
 def test_skill_endurance_and_current_change_cost(self):
  p=WorldPos(1,0,0);base=stroke_cost(self.sim,p,1,0)
  self.sim.state.player_skills['swimming']=8;self.sim.state.player_attributes['endurance']=9
  self.assertLess(stroke_cost(self.sim,p,1,0),base)
  self.world.current_at=lambda *a,**k:SurfaceCurrent('river',1,0,80)
  self.assertGreater(stroke_cost(self.sim,p,-1,0),stroke_cost(self.sim,p,1,0))
 def test_solid_structures_still_block(self):
  self.sim.building.passable=lambda *a:False
  self.move(1);self.assertEqual(self.sim.player_pos.x,0);self.assertEqual(self.sim.state.player_swimming_xp,0)
 def test_bridge_stays_dry(self):
  bridge=next((s for s in self.reg.structures.values() if 'bridge' in s.tags and s.passable),None)
  self.assertIsNotNone(bridge)
  self.sim.building.structure_at=lambda p:SimpleNamespace(structure_id=bridge.id)
  self.assertEqual(exposure(self.sim,WorldPos(1,0,0)).mode,'dry')
 def test_practice_level_and_save(self):
  self.sim.state.player_swimming_xp=19;self.move(1)
  self.assertEqual(self.sim.player_skill('swimming'),1);self.assertEqual(self.sim.state.player_swimming_xp,0)

class MaterializationTests(unittest.TestCase):
 def test_estuary_does_not_replace_offshore_shelf(self):
  reg=ContentRegistry.load(DATA_DIR);g=WorldGenerator(b'estuary',reg,6)
  h=SimpleNamespace(river_class=2,river_depth_class=2,terrain_override='core:river')
  g.hydrology=SimpleNamespace(surface_at=lambda p:h)
  g._surface_terrain_base=lambda p:'core:ocean_shelf'
  self.assertEqual(g.terrain_at(WorldPos(0,0,0)),'core:ocean_shelf')
  g._surface_terrain_base=lambda p:'core:ocean_shallow'
  self.assertEqual(g.terrain_at(WorldPos(0,0,0)),'core:estuary_deep')
 def test_new_materials_have_visuals(self):
  from worldseed.presentation.visuals import VisualRegistry
  reg=ContentRegistry.load(DATA_DIR);self.assertEqual(VisualRegistry.load_default().coverage_issues(reg),[])
 def test_verifier_rejects_bad_swim_progress(self):
  from worldseed.persistence.validation import validate_sim_state
  self.assertTrue(any('swimming' in x for x in validate_sim_state({'player_swimming_xp':-1})))
