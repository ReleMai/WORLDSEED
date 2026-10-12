"""Selection and viewport behavior shared by retained item panels."""
from copy import deepcopy
import unittest

from worldseed.ui.session import NavigationStack, RouteState
from worldseed.ui.widgets import select_menu


class _PanelTerm:
    def __init__(self, keys, *, capacity=3, columns=1):
        self.keys=iter(keys)
        self.capacity=capacity
        self.columns=columns
        self.frames=[]

    def size(self):
        return (100,30)

    def menu_page_size(self,presentation):
        return self.capacity

    def menu_grid_columns(self,presentation):
        return self.columns

    def present_feature_menu(self,presentation,title,rows,selected,**kwargs):
        self.frames.append({
            'rows':[row.key for row in rows],
            'selected':selected,
            'page_start':kwargs['page_start'],
            'data':deepcopy(kwargs['data']),
        })

    def present(self,text):
        pass

    def read_key(self):
        key=next(self.keys)
        return key(self) if callable(key) else key


def _rows(count=10):
    return [(f'item:{index}',f'Item {index}') for index in range(count)]


class ItemPanelWidgetTests(unittest.TestCase):
    def test_hover_preserves_selected_item_quantity_and_action_target(self):
        for presentation in ('inventory_unified','container_inventory','crafting_unified'):
            with self.subTest(presentation=presentation):
                state=RouteState('items','Items',selected=0)
                data={'action_amount':7,'selected_item_id':'item:0'}
                before=deepcopy(data)
                term=_PanelTerm(['UI_HOVER:1','UI_ACTION:drop'])
                choice=select_menu(term,'Items',_rows(),state=state,
                                   presentation=presentation,presentation_data=data)
                self.assertEqual(choice,'UI_ACTION:drop')
                self.assertEqual((state.selected,state.scroll),(0,0))
                self.assertEqual([frame['data']['selected_key'] for frame in term.frames],['item:0','item:0'])
                self.assertTrue(all(frame['data']['action_amount']==7 for frame in term.frames))
                self.assertEqual(data,before)

    def test_scroll_preserves_action_target_even_when_selection_is_offscreen(self):
        state=RouteState('items','Items',selected=1)
        term=_PanelTerm(['UI_WHEEL:2','UI_SCROLL:6','UI_HOVER:2','UI_ACTION:qty_down'])
        choice=select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified',
                           presentation_data={'action_amount':4})
        self.assertEqual(choice,'UI_ACTION:qty_down')
        self.assertEqual((state.selected,state.scroll),(1,6))
        self.assertEqual([frame['page_start'] for frame in term.frames],[0,2,6,6])
        self.assertEqual([frame['selected'] for frame in term.frames],[1,-1,-1,-1])
        self.assertTrue(all(frame['data']['selected_key']=='item:1' for frame in term.frames))
        self.assertTrue(all(frame['data']['action_amount']==4 for frame in term.frames))

    def test_click_after_scroll_resolves_viewport_relative_index(self):
        state=RouteState('items','Items')
        term=_PanelTerm(['UI_SCROLL:5','UI_SELECT:2'])
        self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'),'item:7')
        self.assertEqual((state.selected,state.scroll),(7,5))

    def test_context_after_scroll_selects_exact_row_and_hover_cannot_replace_it(self):
        state=RouteState('items','Items')
        term=_PanelTerm(['UI_SCROLL:4','UI_CONTEXT:1','UI_HOVER:2','UI_ACTION:drop'])
        self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'),'UI_ACTION:drop')
        self.assertEqual((state.selected,state.scroll),(5,4))
        self.assertEqual(term.frames[-1]['data']['selected_key'],'item:5')

    def test_shift_click_after_scroll_transfers_the_clicked_storage_stack(self):
        state=RouteState('items','Items')
        term=_PanelTerm(['UI_SCROLL:5','UI_SHIFT_SELECT:1'])
        self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='container_inventory'),'UI_ACTION:quick_transfer')
        self.assertEqual((state.selected,state.scroll),(6,5))

    def test_scroll_clamps_to_existing_rows_without_changing_selection(self):
        state=RouteState('items','Items',selected=2)
        term=_PanelTerm(['UI_SCROLL:100','UI_WHEEL:-100','UI_SCROLL:bad','ESC'])
        self.assertIsNone(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'))
        self.assertEqual([frame['page_start'] for frame in term.frames],[0,7,0,0])
        self.assertEqual((state.selected,state.scroll),(2,0))

    def test_parent_selection_and_viewport_restore_after_child_route(self):
        nav=NavigationStack(RouteState('items','Items',selected=1,scroll=6))
        before=nav.snapshot()
        nav.push(RouteState('child','Child',selected=4,scroll=2))
        nav.pop()
        term=_PanelTerm(['UI_ACTION:qty_all'])
        self.assertEqual(select_menu(term,'Items',_rows(),state=nav.current,presentation='inventory_unified'),'UI_ACTION:qty_all')
        self.assertEqual(nav.snapshot(),before)
        self.assertEqual((term.frames[0]['page_start'],term.frames[0]['selected']),(6,-1))
        self.assertEqual(term.frames[0]['data']['selected_key'],'item:1')

    def test_resize_clamps_viewport_but_preserves_offscreen_selection(self):
        state=RouteState('items','Items',selected=1,scroll=7)
        def resize(term):
            term.capacity=6
            return 'RESIZE'
        term=_PanelTerm([resize,'ESC'])
        self.assertIsNone(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'))
        self.assertEqual([frame['page_start'] for frame in term.frames],[7,4])
        self.assertEqual([frame['selected'] for frame in term.frames],[-1,-1])
        self.assertEqual((state.selected,state.scroll),(1,4))

    def test_explicit_top_viewport_is_preserved_with_deep_selection(self):
        state=RouteState('items','Items',selected=9,scroll=0)
        term=_PanelTerm(['ESC'])
        self.assertIsNone(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'))
        self.assertEqual((state.selected,state.scroll),(9,0))
        self.assertEqual((term.frames[0]['selected'],term.frames[0]['page_start']),(-1,0))
        self.assertEqual(term.frames[0]['data']['selected_key'],'item:9')

    def test_initial_selection_without_retained_scroll_starts_visible(self):
        term=_PanelTerm(['ESC'])
        self.assertIsNone(select_menu(term,'Items',_rows(),initial=9,presentation='inventory_unified'))
        self.assertEqual((term.frames[0]['selected'],term.frames[0]['page_start']),(2,7))
        self.assertEqual(term.frames[0]['data']['selected_key'],'item:9')

    def test_removed_rows_clamp_retained_selection_and_scroll(self):
        state=RouteState('items','Items',selected=9,scroll=7)
        term=_PanelTerm(['ESC'])
        self.assertIsNone(select_menu(term,'Items',_rows(2),state=state,presentation='inventory_unified'))
        self.assertEqual((state.selected,state.scroll),(1,0))
        self.assertEqual(term.frames[0]['data']['selected_key'],'item:1')

    def test_keyboard_grid_moves_by_columns_and_reveals_selected_row(self):
        state=RouteState('items','Items')
        term=_PanelTerm(['DOWN','RIGHT','DOWN','LEFT','UP','UP','\r'],capacity=6,columns=3)
        self.assertEqual(select_menu(term,'Items',_rows(14),state=state,presentation='inventory_unified'),'item:0')
        self.assertEqual([frame['data']['selected_key'] for frame in term.frames],
                         ['item:0','item:3','item:4','item:7','item:6','item:3','item:0'])
        self.assertEqual([frame['page_start'] for frame in term.frames],[0,0,0,3,3,3,0])
        self.assertEqual((state.selected,state.scroll),(0,0))

    def test_keyboard_navigation_after_scroll_reveals_original_selection(self):
        state=RouteState('items','Items',selected=1,scroll=6)
        term=_PanelTerm(['DOWN','\r'],capacity=3)
        self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='crafting_unified'),'item:2')
        self.assertEqual([frame['page_start'] for frame in term.frames],[6,2])
        self.assertEqual((state.selected,state.scroll),(2,2))

    def test_page_and_home_end_keys_move_selection_and_keep_it_visible(self):
        state=RouteState('items','Items')
        term=_PanelTerm(['END','PGUP','PGDN','HOME','\r'],capacity=3)
        self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='crafting_unified'),'item:0')
        self.assertEqual([frame['data']['selected_key'] for frame in term.frames],
                         ['item:0','item:9','item:6','item:9','item:0'])
        self.assertTrue(all(frame['selected']>=0 for frame in term.frames))

    def test_wasd_still_returns_world_movement_without_changing_selection(self):
        for key in 'wasd':
            with self.subTest(key=key):
                state=RouteState('items','Items',selected=1,scroll=5)
                term=_PanelTerm([key],columns=3)
                self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'),f'UI_WORLD_MOVE:{key}')
                self.assertEqual((state.selected,state.scroll),(1,5))

    def test_keyboard_selection_then_scroll_uses_new_action_target(self):
        state=RouteState('items','Items')
        term=_PanelTerm(['DOWN','UI_SCROLL:6','UI_ACTION:drop'])
        self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'),'UI_ACTION:drop')
        self.assertEqual((state.selected,state.scroll),(1,6))
        self.assertEqual(term.frames[-1]['selected'],-1)
        self.assertEqual(term.frames[-1]['data']['selected_key'],'item:1')

    def test_numeric_shortcut_after_scroll_records_the_exact_action_target(self):
        state=RouteState('items','Items')
        term=_PanelTerm(['UI_SCROLL:5','2'])
        self.assertEqual(select_menu(term,'Items',_rows(),state=state,presentation='inventory_unified'),'item:6')
        self.assertEqual((state.selected,state.scroll),(6,5))

    def test_generic_menu_keeps_existing_hover_selection_behavior(self):
        state=RouteState('menu','Menu')
        term=_PanelTerm(['UI_HOVER:1','\r'])
        self.assertEqual(select_menu(term,'Menu',_rows(),state=state),'item:1')
        self.assertEqual(state.selected,1)


if __name__=='__main__':
    unittest.main()
