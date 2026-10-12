"""RC14 balancing/stabilization regressions. All state transitions are deterministic."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.ai import NPCSystem
from worldseed.systems.artifacts import ArtifactSystem
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.resources import ResourceSystem,FeatureView
from worldseed.systems.state import LivingWorldState,NPCState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


class BalancingStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def resource_fixture(self):
        state=LivingWorldState()
        fields=SimpleNamespace(temperature=35000,moisture=60000,fertility=48000)
        world=SimpleNamespace(
            resourcegen_version=5,delta_source=SimpleNamespace(),
            generator=SimpleNamespace(sample_fields=lambda pos:fields),
            tile_at=lambda pos:SimpleNamespace(terrain_id="core:river_shallow",
                                                terrain=SimpleNamespace(name="Shallow river")))
        return ResourceSystem(state,self.registry,b"reed-test-v5",world),state

    def test_shallow_river_reeds_have_deterministic_harvestable_patches(self):
        resource,state=self.resource_fixture()
        cells=[WorldPos(x,y,0) for y in range(12) for x in range(12)]
        occupied=[p for p in cells if (f:=resource.feature_at(p)) and f.feature_id=="core:reed_bed"]
        self.assertGreater(len(occupied),5)
        second,_=self.resource_fixture()
        self.assertEqual(occupied,[p for p in cells if (f:=second.feature_at(p)) and f.feature_id=="core:reed_bed"])
        self.assertTrue(resource.is_harvestable(occupied[0]))
        ok,msg,minutes,goods=resource.harvest(occupied[0],Inventory(),0)
        self.assertTrue(ok,msg)
        self.assertGreaterEqual(goods["core:reed_bundle"],2)
        self.assertGreaterEqual(minutes,3)
        self.assertEqual(resource.feature_at(occupied[0]).stage,"depleted")

    def test_cutter_improves_reed_yield_and_reduces_time(self):
        pos=WorldPos(3,5,0)
        bare,_=self.resource_fixture()
        bare.feature_at=lambda p,minute=None:FeatureView("core:reed_bed")
        cutter,_=self.resource_fixture()
        cutter.feature_at=lambda p,minute=None:FeatureView("core:reed_bed")
        ok,_,base_time,base_goods=bare.harvest(pos,Inventory(),0)
        self.assertTrue(ok)
        inv=Inventory({"core:crude_knife":1})
        ok,_,tool_time,tool_goods=cutter.harvest(pos,inv,0)
        self.assertTrue(ok)
        self.assertGreater(tool_goods["core:reed_bundle"],base_goods["core:reed_bundle"])
        self.assertLess(tool_time,base_time)

    def test_experiment_returns_persisted_low_quality_prototype(self):
        state=LivingWorldState(player_crafting_discovery_enabled=True)
        artifacts=ArtifactSystem(state,self.registry,b"prototype-test")
        pot=CraftingSystem(state,self.registry,artifacts)
        inv=Inventory({"core:stone":3})
        ok,msg,minutes=pot.combine_in_pot(("core:stone",),inv,b"prototype-test",600)
        self.assertTrue(ok,msg)
        self.assertIn("prototype",msg.lower())
        recipe=self.registry.recipes[state.player_discovered_recipes[-1]]
        for iid,count in recipe.outputs.items():
            if count>0:
                self.assertGreaterEqual(inv.count(iid),1)
                sample=[a for a in state.artifacts.values() if a.base_item==iid]
                self.assertTrue(sample)
                self.assertTrue(sample[0].name.startswith("Experimental "))
                self.assertGreaterEqual(sample[0].quality,8)
                self.assertLessEqual(sample[0].quality,20)
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(set(restored.artifacts),set(state.artifacts))

    def test_npcs_may_not_move_onto_another_exterior_npc(self):
        state=LivingWorldState()
        a=NPCState("npc:a","Ada",32,"farmer",[],0,0,0,"town","faction")
        b=NPCState("npc:b","Bram",29,"farmer",[],1,0,0,"town","faction")
        state.npcs={a.uid:a,b.uid:b}
        npc=NPCSystem(state,b"no-overlap",None,world=SimpleNamespace(is_passable=lambda pos:True))
        self.assertFalse(npc.movement_passable(a,WorldPos(1,0,0),600))
        self.assertTrue(npc.movement_passable(a,WorldPos(2,0,0),600))
        state.interior_actors[b.uid]=SimpleNamespace(space_id="inside")
        self.assertTrue(npc.movement_passable(a,WorldPos(1,0,0),600))

    def test_distant_frontage_is_rebound_to_reachable_real_door(self):
        state=LivingWorldState()
        npc=NPCState("npc:a","Ada",32,"farmer",[],0,0,0,"town","faction")
        npc.home_id="home:1"
        state.npcs[npc.uid]=npc
        ai=NPCSystem(state,b"doors",None,world=SimpleNamespace(is_passable=lambda p:True))
        door=SimpleNamespace(uid="entrance:1",role="entrance",x=10,y=10,z=0)
        ai.property_security=SimpleNamespace(doors_for_property=lambda _: (door,),
                                            blocks_actor=lambda *args:False)
        ai.interiors=SimpleNamespace()
        ai.settlement_physicalization=SimpleNamespace(frontage_for=lambda _:WorldPos(2,2,0))
        task=ai._home_entry_task(npc)
        self.assertLessEqual(abs(task["x"]-10)+abs(task["y"]-10),1)
        self.assertEqual(task["interior_home_door_uid"],door.uid)


@unittest.skipUnless(PygameTerminal.available(),"requires pygame-ce")
class InventoryDescriptionScrollTests(unittest.TestCase):
    def test_long_item_details_have_real_scroll_track_and_mouse_wheel(self):
        term=PygameTerminal(1280,800)
        term.enter()
        try:
            term._input_mode="ui"
            term._current_presentation="inventory_unified"
            item="core:reed_bundle"
            data={"items":{item:{"name":"Reeds","count":2,"category":"plant",
                                "description":"Long wetland fibers. "*75,
                                "detail_lines":["A description detail. "*30]}},
                  "selected_item_id":item,"filter_categories":[],"active_filter":"all"}
            rows=[MenuRow(item,"Reeds")]
            term._present_inventory_unified("Inventory",rows,0,data=data)
            self.assertGreater(term._inventory_desc_max,0)
            self.assertIsNotNone(term._inventory_desc_track)
            position=term._inventory_desc_rect.center
            term._last_mouse=position
            term.pg.event.clear()
            term.pg.event.post(term.pg.event.Event(term.pg.MOUSEWHEEL,x=0,y=-1))
            self.assertEqual(term.read_key(),"UI_REDRAW")
            self.assertGreater(term._inventory_desc_scroll,0)
        finally:term.restore()


if __name__=="__main__":
    unittest.main()
