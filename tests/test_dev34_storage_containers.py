import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")

import unittest

from worldseed.config import DATA_DIR, RESOURCEGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.building import BuildingSystem
from worldseed.systems.resources import FeatureView
from worldseed.systems.state import LivingWorldState, pos_key
from worldseed.ui.widgets import MenuRow, select_menu


class _NaturalResources:
    def __init__(self, feature_id):
        self.feature_id=feature_id
        self.revision=0
    def feature_at(self, pos):
        return FeatureView(self.feature_id,"mature")


class _KeyTerm:
    def __init__(self, key):
        self.key=key
    def size(self): return (100,30)
    def read_key(self): return self.key
    def present(self, text): pass
    def present_feature_menu(self, *args, **kwargs): pass


class Dev34StorageContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=ContentRegistry.load(DATA_DIR)

    def test_resourcegen_v4_and_storage_content_load(self):
        self.assertEqual(RESOURCEGEN_VERSION,4)
        self.assertIn("core:wicker_basket",self.reg.items)
        self.assertIn("core:wood_storage_box",self.reg.items)
        self.assertIn("core:wicker_basket",self.reg.recipes)
        self.assertIn("core:wood_storage_box",self.reg.recipes)
        basket=self.reg.structures["core:storage_basket"]
        box=self.reg.structures["core:wood_storage_box"]
        self.assertEqual(basket.cost,{"core:wicker_basket":1})
        self.assertEqual(box.cost,{"core:wood_storage_box":1})
        self.assertIn("movable",basket.tags)
        self.assertIn("movable",box.tags)

    def test_natural_container_definitions_are_data_driven(self):
        hollow=self.reg.resources["core:hollow_log_cache"]
        stump=self.reg.resources["core:rotten_stump_cache"]
        rock=self.reg.resources["core:rock_crevice_cache"]
        for row in (hollow,stump,rock):
            self.assertIn("natural_container",row.tags)
            self.assertIn(row.container_structure_id,self.reg.structures)
            self.assertTrue(row.container_loot)
            self.assertTrue(row.container_salvage)
        self.assertTrue(hollow.container_movable)
        self.assertFalse(stump.container_movable)
        self.assertFalse(rock.container_movable)

    def _materialize(self, feature_id, pos=WorldPos(3,4,0)):
        state=LivingWorldState()
        building=BuildingSystem(state,self.reg)
        resources=_NaturalResources(feature_id)
        building.attach_resources(resources,b"dev34-natural-container")
        container=building.materialize_natural_container_at(pos)
        return state,building,resources,container

    def test_natural_container_loot_is_deterministic_and_persistent(self):
        p=WorldPos(3,4,0)
        state_a,building_a,res_a,a=self._materialize("core:hollow_log_cache",p)
        state_b,building_b,res_b,b=self._materialize("core:hollow_log_cache",p)
        self.assertIsNotNone(a)
        self.assertEqual(a.items,b.items)
        self.assertGreaterEqual(a.items.get("core:bark",0),1)
        key=pos_key(p.x,p.y,p.z)
        self.assertEqual(a.kind,"natural")
        self.assertTrue(a.movable)
        self.assertIn(key,state_a.structures)
        self.assertIs(state_a.containers[key],a)
        self.assertIn(key,state_a.resource_depletion)
        self.assertEqual(res_a.revision,1)
        # Re-realization is idempotent and does not reroll or double-count.
        before=dict(a.items)
        self.assertIs(building_a.materialize_natural_container_at(p),a)
        self.assertEqual(a.items,before)
        self.assertEqual(building_a.materialize_natural_containers([p]),0)

    def test_natural_container_can_move_and_break_into_ground_loot(self):
        old=WorldPos(3,4,0);new=WorldPos(4,4,0)
        state,building,_,c=self._materialize("core:hollow_log_cache",old)
        c.items["core:berries"]=2
        ok,msg=building.move_container(c,new)
        self.assertTrue(ok,msg)
        self.assertNotIn(pos_key(old.x,old.y,old.z),state.containers)
        self.assertIn(pos_key(new.x,new.y,new.z),state.containers)
        self.assertEqual(state.structures[pos_key(new.x,new.y,new.z)].x,new.x)
        ok,msg=building.destroy_container(c)
        self.assertTrue(ok,msg)
        key=pos_key(new.x,new.y,new.z)
        self.assertNotIn(key,state.containers)
        self.assertNotIn(key,state.structures)
        self.assertEqual(state.ground_piles[key].items["core:berries"],2)
        self.assertGreaterEqual(state.ground_piles[key].items.get("core:wood",0),1)

    def test_rooted_natural_container_refuses_move(self):
        _,building,_,c=self._materialize("core:rotten_stump_cache")
        ok,msg=building.move_container(c,WorldPos(4,4,0))
        self.assertFalse(ok)
        self.assertIn("fixed",msg.lower())

    def test_crafted_storage_item_places_as_movable_container(self):
        state=LivingWorldState();building=BuildingSystem(state,self.reg)
        inv=Inventory({"core:wicker_basket":1})
        p=WorldPos(8,9,0)
        ok,msg=building.place("core:storage_basket",p,inv)
        self.assertTrue(ok,msg)
        self.assertEqual(inv.count("core:wicker_basket"),0)
        c=state.containers[pos_key(8,9,0)]
        self.assertEqual(c.kind,"built")
        self.assertTrue(c.movable)
        self.assertEqual(c.name,"Placed Wicker Basket")

    def test_portable_crafted_storage_can_be_packed_up_for_reuse(self):
        state=LivingWorldState();building=BuildingSystem(state,self.reg)
        inv=Inventory({"core:wicker_basket":1})
        p=WorldPos(8,9,0)
        ok,msg=building.place("core:storage_basket",p,inv)
        self.assertTrue(ok,msg)
        state.containers[pos_key(8,9,0)].items["core:bark"]=2
        ok,msg=building.dismantle(p,inv)
        self.assertTrue(ok,msg)
        self.assertEqual(inv.count("core:wicker_basket"),1)
        self.assertEqual(state.ground_piles[pos_key(8,9,0)].items["core:bark"],2)
        self.assertNotIn(pos_key(8,9,0),state.containers)

    def test_container_keyboard_transfer_intent(self):
        term=_KeyTerm("t")
        choice=select_menu(
            term,"STORAGE",
            [("pack|core:wood","Wood x4")],
            presentation="container_inventory",
            presentation_data={},
        )
        self.assertEqual(choice,"UI_ACTION:transfer")


class Dev34StoragePygameTests(unittest.TestCase):
    def test_dual_pane_container_targets_stay_inside_small_window(self):
        from worldseed.ui.pygame_terminal import PygameTerminal
        if not PygameTerminal.available():
            self.skipTest("requires pygame-ce")
        t=PygameTerminal(800,520);t.enter()
        try:
            t._resize(800,520)
            rows=[MenuRow("pack|core:wood","Wood x4"),MenuRow("container|core:bark","Bark x2")]
            data={
                "entries":{
                    "pack|core:wood":{"iid":"core:wood","name":"Wood Log","count":4,"side":"pack","unit_mass_kg":3.0,"description":"Timber."},
                    "container|core:bark":{"iid":"core:bark","name":"Tannin-Rich Bark","count":2,"side":"container","unit_mass_kg":0.25,"description":"Bark."},
                },
                "action_amount":1,
                "pack":{"item_count":4},
                "container":{
                    "uid":"natural:test","name":"Hollow Log","kind":"natural","movable":True,
                    "mass_kg":0.5,"volume_l":0.9,"capacity_mass_kg":45.0,"capacity_volume_l":60.0,
                    "item_count":2,"stack_count":1,
                },
            }
            t.present_feature_menu("container_inventory","STORAGE",rows,0,data=data)
            screen=t.screen.get_rect()
            wanted={"UI_ACTION:transfer","UI_ACTION:move:-1:0","UI_ACTION:move:0:-1","UI_ACTION:move:0:1","UI_ACTION:move:1:0","UI_ACTION:destroy"}
            found={token for _,token in t._pointer_targets}
            self.assertTrue(wanted.issubset(found),wanted-found)
            for rect,token in t._pointer_targets:
                self.assertTrue(screen.contains(rect),(token,rect))
                if token in wanted:
                    self.assertLessEqual(rect.bottom,520-56,(token,rect))
        finally:
            t.restore()


if __name__=="__main__":
    unittest.main()
