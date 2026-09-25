import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

from worldseed.ui.widgets import MenuRow, select_menu
from worldseed.ui.pygame_terminal import PygameTerminal


class _SequenceTerm:
    def __init__(self, keys):
        self.keys = iter(keys)
    def size(self):
        return (100, 30)
    def read_key(self):
        return next(self.keys)
    def present(self, text):
        pass
    def present_feature_menu(self, *args, **kwargs):
        pass


class FloatingWidgetIntentTests(unittest.TestCase):
    def test_right_click_context_updates_selection_without_backing_out(self):
        term = _SequenceTerm(["UI_CONTEXT:1", "\r"])
        choice = select_menu(
            term,
            "INVENTORY",
            [("wood", "Wood"), ("stone", "Stone")],
            presentation="inventory_unified",
            presentation_data={"near_storage": False},
        )
        self.assertEqual(choice, "stone")

    def test_shift_click_container_maps_to_full_stack_transfer(self):
        term = _SequenceTerm(["UI_SHIFT_SELECT:0"])
        choice = select_menu(
            term,
            "STORAGE",
            [("pack|core:wood", "Wood x4")],
            presentation="container_inventory",
            presentation_data={},
        )
        self.assertEqual(choice, "UI_ACTION:quick_transfer")

    def test_shift_click_inventory_maps_to_full_stack_store_when_available(self):
        term = _SequenceTerm(["UI_SHIFT_SELECT:0"])
        choice = select_menu(
            term,
            "INVENTORY",
            [("core:wood", "Wood x4")],
            presentation="inventory_unified",
            presentation_data={"near_storage": True},
        )
        self.assertEqual(choice, "UI_ACTION:quick_store")


@unittest.skipUnless(PygameTerminal.available(), "requires pygame-ce")
class FloatingInteractionPygameTests(unittest.TestCase):
    def setUp(self):
        self.term = PygameTerminal(1280, 800)
        self.term.enter()
        self.pg = self.term.pg
        self.pg.event.clear()

    def tearDown(self):
        self.term.restore()

    def _inventory_data(self):
        return {
            "items": {
                "core:wood": {
                    "name": "Wood",
                    "count": 4,
                    "category": "material",
                    "unit_mass_kg": 1.0,
                    "unit_volume_l": 1.0,
                    "description": "A useful piece of wood.",
                    "detail_lines": [],
                    "can_use": False,
                    "use_label": "Use",
                }
            },
            "total_mass_kg": 4.0,
            "total_volume_l": 4.0,
            "stack_count": 1,
            "item_count": 4,
            "selected_item_id": "core:wood",
            "action_amount": 1,
            "active_filter": "all",
            "filter_categories": ["material"],
            "near_storage": True,
        }

    def _container_data(self):
        return {
            "entries": {
                "pack|core:wood": {
                    "iid": "core:wood",
                    "name": "Wood",
                    "count": 4,
                    "side": "pack",
                    "unit_mass_kg": 1.0,
                    "description": "A useful piece of wood.",
                },
                "container|core:bark": {
                    "iid": "core:bark",
                    "name": "Bark",
                    "count": 2,
                    "side": "container",
                    "unit_mass_kg": 0.25,
                    "description": "Tannin-rich bark.",
                },
            },
            "action_amount": 1,
            "pack": {"item_count": 4},
            "container": {
                "uid": "natural:test",
                "name": "Hollow Log",
                "kind": "natural",
                "movable": True,
                "mass_kg": 0.5,
                "volume_l": 0.9,
                "capacity_mass_kg": 45.0,
                "capacity_volume_l": 60.0,
                "item_count": 2,
                "stack_count": 1,
            },
        }

    def _target_rect(self, token):
        return next(rect for rect, value in self.term._pointer_targets if value == token)

    def test_inventory_is_smaller_floating_draggable_resizable_panel(self):
        rows = [MenuRow("core:wood", "Wood x4")]
        self.term.present_feature_menu(
            "inventory_unified", "INVENTORY", rows, 0, data=self._inventory_data()
        )
        state = self.term._floating_panels["inventory_unified"]
        sw, sh = self.term.screen.get_size()
        self.assertLess(state["w"], sw)
        self.assertLess(state["h"], sh)
        self.assertGreaterEqual(state["x"], 8)
        self.assertGreaterEqual(state["y"], 8)

        drag = self._target_rect("UI_WINDOW_DRAG:inventory_unified")
        old_xy = (state["x"], state["y"])
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=drag.center))
        self.pg.event.post(self.pg.event.Event(
            self.pg.MOUSEMOTION, pos=(drag.centerx + 24, drag.centery + 18), rel=(24, 18), buttons=(1, 0, 0)
        ))
        self.assertEqual(self.term.read_key(), "UI_REDRAW")
        self.assertNotEqual((state["x"], state["y"]), old_xy)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONUP, button=1, pos=(drag.centerx + 24, drag.centery + 18)))
        self.assertEqual(self.term.read_key(), "UI_REDRAW")

        self.term.present_feature_menu(
            "inventory_unified", "INVENTORY", rows, 0, data=self._inventory_data()
        )
        resize = self._target_rect("UI_WINDOW_RESIZE:inventory_unified")
        old_wh = (state["w"], state["h"])
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=resize.center))
        self.pg.event.post(self.pg.event.Event(
            self.pg.MOUSEMOTION, pos=(resize.centerx + 36, resize.centery + 24), rel=(36, 24), buttons=(1, 0, 0)
        ))
        self.assertEqual(self.term.read_key(), "UI_REDRAW")
        self.assertNotEqual((state["w"], state["h"]), old_wh)

    def test_inventory_right_click_opens_action_popup_instead_of_escape(self):
        rows = [MenuRow("core:wood", "Wood x4")]
        data = self._inventory_data()
        self.term.present_feature_menu("inventory_unified", "INVENTORY", rows, 0, data=data)
        item = self._target_rect("UI_SELECT:0")
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=3, pos=item.center))
        self.assertEqual(self.term.read_key(), "UI_CONTEXT:0")

        self.term.present_feature_menu("inventory_unified", "INVENTORY", rows, 0, data=data)
        tokens = {token for _, token in self.term._pointer_targets}
        self.assertIn("UI_ACTION:drop", tokens)
        self.assertIn("UI_ACTION:store", tokens)
        self.assertNotIn("ESC", {self.term._hit_token(item.center)})

    def test_item_popup_animates_once_and_actions_remain_clickable_at_window_edge(self):
        rows = [MenuRow("core:wood", "Wood x4")]
        data = self._inventory_data()
        self.term.present_feature_menu("inventory_unified", "INVENTORY", rows, 0, data=data)
        item = self._target_rect("UI_SELECT:0")
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=3, pos=item.center))
        self.assertEqual(self.term.read_key(), "UI_CONTEXT:0")
        self.term._ui_context["pos"] = (1270, 790)
        self.term.present_feature_menu("inventory_unified", "INVENTORY", rows, 0, data=data)
        self.assertTrue(self.term._ui_context["opened"])
        button = self._target_rect("UI_ACTION:drop")
        self.assertLessEqual(button.right, self.term.screen.get_width() - 8)
        self.assertLessEqual(button.bottom, self.term.screen.get_height() - 8)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=button.center))
        self.assertEqual(self.term.read_key(), "UI_ACTION:drop")

    def test_container_shift_click_emits_quick_transfer_intent(self):
        rows = [
            MenuRow("pack|core:wood", "Wood x4"),
            MenuRow("container|core:bark", "Bark x2"),
        ]
        self.term.present_feature_menu(
            "container_inventory", "STORAGE", rows, 0, data=self._container_data()
        )
        item = self._target_rect("UI_SELECT:0")
        self.pg.key.set_mods(self.pg.KMOD_SHIFT)
        try:
            self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=item.center))
            self.assertEqual(self.term.read_key(), "UI_SHIFT_SELECT:0")
        finally:
            self.pg.key.set_mods(0)

    def test_world_context_popup_is_cursor_anchored_and_restores_world_on_choice(self):
        self.term.screen.fill((33, 44, 55))
        self.term._context_backdrop = self.term.screen.copy()
        self.term._context_menu_origin = (240, 180)
        rows = [
            MenuRow("open", "Open Hollow Log"),
            MenuRow("examine", "Examine tile and contents"),
        ]
        self.term.present_feature_menu(
            "world_context", "WORLD ACTIONS 10,12", rows, 0,
            subtitle="Right-click world actions.", data={}
        )
        first = self._target_rect("UI_SELECT:0")
        self.assertGreaterEqual(first.x, 240)
        self.assertGreaterEqual(first.y, 180)
        self.assertNotEqual(self.term.screen.get_at(first.center)[:3], (33, 44, 55))

        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=first.center))
        self.assertEqual(self.term.read_key(), "UI_SELECT:0")
        self.assertEqual(self.term.screen.get_at(first.center)[:3], (33, 44, 55))
        self.assertIsNone(self.term._context_backdrop)

    def test_world_popup_opens_from_click_and_keeps_each_button_selectable(self):
        self.term.screen.fill((33, 44, 55))
        self.term._context_backdrop = self.term.screen.copy()
        self.term._context_menu_origin = (1240, 755)
        self.term._context_opening = True
        rows = [MenuRow("open", "Open cache"), MenuRow("inspect", "Inspect contents")]
        self.term.present_feature_menu("world_context", "WORLD ACTIONS", rows, 0)
        self.assertFalse(self.term._context_opening)
        buttons = [self._target_rect(f"UI_SELECT:{i}") for i in range(2)]
        self.assertTrue(all(0 <= r.x < r.right <= 1272 and 0 <= r.y < r.bottom <= 792 for r in buttons))
        self.assertEqual(self.term._hit_token(buttons[1].center), "UI_SELECT:1")


    def test_floating_overlays_suspend_world_hover_animation_until_world_redraw(self):
        rows=[MenuRow("core:wood","Wood x4")];data=self._inventory_data()
        used=self.pg.Rect(10,10,240,180)
        self.term._hover_context={"used":used,"tile_px":28}
        self.term._hover_map_snapshot=self.pg.Surface(used.size)
        self.term.present_feature_menu("inventory_unified","INVENTORY",rows,0,data=data)
        self.assertIsNone(self.term._hover_context)
        self.assertIsNone(self.term._hover_map_snapshot)
        self.term._hover_context={"used":used,"tile_px":28}
        self.term._hover_map_snapshot=self.pg.Surface(used.size)
        self.term._context_backdrop=self.term.screen.copy();self.term._context_menu_origin=(100,100)
        self.term.present_feature_menu("world_context","WORLD ACTIONS", [MenuRow("examine","Examine")],0,data={})
        self.assertIsNone(self.term._hover_context)
        self.assertIsNone(self.term._hover_map_snapshot)


    def test_world_context_dismisses_with_right_click_or_left_click_outside(self):
        rows=[MenuRow("examine","Examine")]
        self.term._context_backdrop=self.term.screen.copy();self.term._context_menu_origin=(200,160)
        self.term.present_feature_menu("world_context","WORLD ACTIONS",rows,0,data={})
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=3,pos=(20,20)))
        self.assertEqual(self.term.read_key(),"ESC")
        self.term._context_backdrop=self.term.screen.copy();self.term.present_feature_menu("world_context","WORLD ACTIONS",rows,0,data={})
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=1,pos=(20,20)))
        self.assertEqual(self.term.read_key(),"ESC")

    def test_open_item_context_does_not_follow_hover_to_another_item(self):
        rows=[MenuRow("core:wood","Wood"),MenuRow("core:bark","Bark")];data=self._inventory_data()
        self.term.present_feature_menu("inventory_unified","INVENTORY",rows,0,data=data)
        first=self._target_rect("UI_SELECT:0");second=self._target_rect("UI_SELECT:1")
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,button=3,pos=first.center));self.assertEqual(self.term.read_key(),"UI_CONTEXT:0")
        self.term.present_feature_menu("inventory_unified","INVENTORY",rows,0,data=data)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEMOTION,pos=second.center,rel=(1,0),buttons=(0,0,0)))
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,key=self.pg.K_ESCAPE,unicode=""))
        self.assertEqual(self.term.read_key(),"ESC")
        self.assertEqual(self.term._ui_context["index"],0)


    def test_world_context_keeps_live_hover_animation_state_attached(self):
        used=self.pg.Rect(10,10,240,180)
        self.term._hover_context={'used':used,'tile_px':28}
        self.term._hover_map_snapshot=self.pg.Surface(used.size)
        self.term._context_menu_origin=(100,100)
        self.term.present_feature_menu('world_context','WORLD ACTIONS',[MenuRow('examine','Examine')],0,data={})
        self.assertIsNotNone(self.term._hover_context)
        self.assertIsNotNone(self.term._hover_map_snapshot)
        self.assertIsNotNone(self.term._context_overlay_rect)


if __name__ == "__main__":
    unittest.main()
