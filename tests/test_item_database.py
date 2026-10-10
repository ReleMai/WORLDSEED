"""The live item database, browsing UI and generated catalogs stay in sync."""
from __future__ import annotations

from copy import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")

from worldseed.app import _crafting_material_ui_data, _crafting_menu, _inventory_menu, _inventory_ui_data
from worldseed.config import DATA_DIR
from worldseed.content.item_catalog import ITEM_TYPE_ORDER, ordered_items
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.state import LivingWorldState
from worldseed.systems.crafting import CraftingSystem
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/"worldseed"/"assets"


class ItemDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)
        cls.raw=json.loads((DATA_DIR/"items.json").read_text(encoding="utf-8"))
        cls.raw_by_id={item["id"]:item for item in cls.raw}

    def simulation(self):
        return SimpleNamespace(state=LivingWorldState(),player_pos=None,
                               building=SimpleNamespace(nearby_container=lambda pos:None))

    def test_runtime_visual_ids_and_files_match_the_live_database(self):
        visuals=VisualRegistry.load_default()
        self.assertEqual(set(visuals.manifest["items"]),set(self.registry.items))
        resolved=[]
        for item in self.registry.items.values():
            path=visuals.resolve(visuals.ref("items",item.id))
            self.assertEqual(path,ASSETS/"sprites"/"items"/(self.raw_by_id[item.id]["asset"]+".png"),item.id)
            self.assertTrue(path.is_file(),item.id)
            resolved.append(path)
        self.assertEqual(len(resolved),len(set(resolved)))

    def test_runtime_atlas_maps_every_item_to_a_distinct_nonempty_cell(self):
        index=json.loads((ASSETS/"atlas_index.json").read_text(encoding="utf-8"))
        atlas=index["atlases"]["items"];entries=atlas["entries"]
        self.assertEqual(set(entries),set(self.registry.items),"rebuild the item atlas after changing the database")
        cells=[tuple(row["cell"]) for row in entries.values()]
        self.assertEqual(len(cells),len(set(cells)))
        expected=[item.id for item in ordered_items(self.registry.items.values())]
        actual=sorted(entries,key=lambda iid:(entries[iid]["cell"][1],entries[iid]["cell"][0]))
        self.assertEqual(actual,expected)
        with Image.open(ROOT/"worldseed"/atlas["image"]) as sheet:
            sheet=sheet.convert("RGBA")
            for iid,row in entries.items():
                x,y,w,h=row["rect"];col,cell_row=row["cell"]
                self.assertEqual((x,y),(col*index["cell_px"],cell_row*index["cell_px"]),iid)
                self.assertGreater(w,0);self.assertGreater(h,0)
                self.assertLessEqual(x+w,sheet.width,iid);self.assertLessEqual(y+h,sheet.height,iid)
                self.assertIsNotNone(sheet.crop((x,y,x+w,y+h)).getchannel("A").getbbox(),iid)

    def test_readable_catalog_has_every_live_id_and_asset_once_in_database_order(self):
        text=(ASSETS/"ITEM_ATLAS.md").read_text(encoding="utf-8")
        rows=re.findall(r"\| `([^`]+)` \| `([a-z0-9_]+\.png)` \|",text)
        expected=[(item.id,self.raw_by_id[item.id]["asset"]+".png") for item in ordered_items(self.registry.items.values())]
        self.assertEqual(rows,expected,"rebuild the readable item catalog after changing the database")

    def test_inventory_and_material_discoveries_keep_all_items_in_catalog_order(self):
        sim=self.simulation()
        reversed_ids=list(reversed(self.registry.items))
        inv=Inventory({iid:1 for iid in reversed_ids})
        sim.state.player_discovered_items=reversed_ids+[reversed_ids[0]]
        before=sim.state.to_dict();before_inventory=dict(inv.items)
        inventory=_inventory_ui_data(self.registry,inv,sim)
        discoveries=_crafting_material_ui_data(self.registry,sim)
        expected=[item.id for item in ordered_items(self.registry.items.values())]
        self.assertEqual(list(inventory["items"]),expected)
        self.assertEqual(list(discoveries["items"]),expected)
        self.assertEqual(inventory["stack_count"],len(expected))
        self.assertEqual(inventory["categories"]["misc"],204)
        self.assertEqual(sim.state.to_dict(),before)
        self.assertEqual(inv.items,before_inventory)

    def test_inventory_use_actions_follow_physical_fields_in_every_display_group(self):
        registry=copy(self.registry);registry.items=dict(registry.items)
        foods=next(item for item in registry.items.values() if item.nutrition>0)
        weapon=next(item for item in registry.items.values() if item.weapon_damage>0 and item.nutrition<=0)
        equipment=next(item for item in registry.items.values() if item.equip_slot and item.weapon_damage<=0 and item.nutrition<=0)
        for item,action in ((foods,"eat"),(weapon,"ready"),(equipment,"equip")):
            with self.subTest(item=item.id):
                registry.items[item.id]=replace(item,category="misc",subcategory="hardware")
                data=_inventory_ui_data(registry,Inventory({item.id:1}),self.simulation())
                self.assertEqual(data["items"][item.id]["use_kind"],action)

    def test_terminal_material_discoveries_include_the_entire_miscellaneous_group(self):
        sim=self.simulation();sim.player_skill=lambda skill:1
        sim.building.nearby_station_ids=lambda pos:set()
        sim.crafting=CraftingSystem(sim.state,self.registry)
        misc=[item for item in ordered_items(self.registry.items.values()) if item.category=="misc"]
        sim.state.player_discovered_items=[item.id for item in reversed(misc)]
        ctx=SimpleNamespace(sim=sim,registry=self.registry,player_id=1,entities=SimpleNamespace(get=lambda *args:Inventory()))
        terminal=SimpleNamespace(size=lambda:(100,30))
        with patch("worldseed.app._select",side_effect=("materials",None)),patch("worldseed.app._view_text") as view:
            _crafting_menu(ctx,terminal)
        text=view.call_args.args[1]
        for item in misc:self.assertIn(item.name,text)

    def test_inventory_filter_navigation_reaches_the_complete_miscellaneous_group(self):
        sim=self.simulation();inv=Inventory({iid:1 for iid in reversed(self.registry.items)})
        frames=[]
        class Terminal:
            mouse_ui=True
            def __init__(self):
                self.keys=iter(("UI_ACTION:filter_page:next","UI_ACTION:filter_page:next","UI_ACTION:filter:misc","ESC"))
            def size(self):return 100,30
            def menu_page_size(self,presentation):return 1000
            def present_feature_menu(self,*args,**kwargs):frames.append((args,kwargs))
            def read_key(self):return next(self.keys)
        ctx=SimpleNamespace(sim=sim,registry=self.registry,player_id=1,entities=SimpleNamespace(get=lambda *args:inv))
        before=sim.state.to_dict()
        _inventory_menu(ctx,Terminal())
        _,kwargs=frames[-1];data=kwargs["data"]
        self.assertEqual(data["active_filter"],"misc")
        self.assertEqual(data["filter_page"],2)
        rows=frames[-1][0][2]
        self.assertEqual({row.key for row in rows},{item.id for item in self.registry.items.values() if item.category=="misc"})
        self.assertEqual(len(rows),204)
        self.assertEqual(sim.state.to_dict(),before)


@unittest.skipUnless(PygameTerminal.available(),"requires pygame-ce")
class ItemCategoryFilterUITests(unittest.TestCase):
    def test_every_category_filter_is_reachable_and_fits_the_inventory_panel(self):
        terminal=PygameTerminal(1024,768);terminal.enter()
        try:
            terminal._floating_panels["inventory_unified"]={"x":10,"y":10,"w":780,"h":600}
            expected={"UI_ACTION:filter:all"}|{f"UI_ACTION:filter:{cat}" for cat in ITEM_TYPE_ORDER}
            reached=set()
            for page in range((len(ITEM_TYPE_ORDER)+1+5)//6):
                terminal.present_feature_menu("inventory_unified","INVENTORY",[MenuRow("__empty__","Empty")],0,
                    data={"items":{},"filter_categories":list(ITEM_TYPE_ORDER),"filter_page":page})
                filters=[(rect,token) for rect,token in terminal._pointer_targets if token.startswith("UI_ACTION:filter:")]
                for rect,token in filters:
                    self.assertGreaterEqual(rect.left,26);self.assertLessEqual(rect.right,774)
                    reached.add(token)
                self.assertEqual(len({rect.y for rect,_ in filters}),1)
                self.assertIn("UI_ACTION:filter_page:next",{token for _,token in terminal._pointer_targets})
            self.assertEqual(reached,expected)
        finally:terminal.restore()


if __name__=="__main__":unittest.main()
