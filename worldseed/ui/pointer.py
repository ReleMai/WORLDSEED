"""Presentation-only pointer targets. Tokens are interpreted by existing widgets.
No simulation state is stored here, and hit regions are rebuilt every frame.
"""
class WindowCloseRequested(Exception):
    """Unwind a modal UI to the application save/exit boundary."""


class PointerUI:
    mouse_ui = True

    def _set_input_mode(self, mode):
        if getattr(self, '_input_mode', None) != mode:
            self._held_movement.clear()
            self._active_movement_key = None
            self._movement_next_repeat_ms = 0
        self._input_mode = mode

    def _ui_target(self, rect, token):
        self._pointer_targets.append((self.pg.Rect(rect), token))

    def _hit_token(self, pos):
        return next((token for rect,token in reversed(self._pointer_targets) if rect.collidepoint(pos)), None)

    def _button(self, rect, label, token):
        pg=self.pg;rect=pg.Rect(rect)
        hover=rect.collidepoint(self._last_mouse)
        pg.draw.rect(self.screen, (43,48,48) if hover else self._theme['panel2'], rect, border_radius=5)
        pg.draw.rect(self.screen,self._theme['accent'] if hover else self._theme['edge_hi'],rect,1,border_radius=5)
        text=self.small_font.render(self._fit_ui_text(label,self.small_font,rect.width-12),True,self._theme['text'])
        self.screen.blit(text,text.get_rect(center=rect.center))
        self._ui_target(rect,token)

    def _ui_navigation(self, *, confirm=False, extra=None, back=True):
        w,h=self.screen.get_size();y=h-52
        buttons=[('Back','ESC')] if back else []
        if confirm:buttons.append(('Continue','\r'))
        else:buttons.extend([('Previous','PGUP'),('Next','PGDN')])
        if extra:buttons.append(extra)
        for i,(label,token) in enumerate(buttons):
            self._button((36+i*112,y,104,30),label,token)

    def menu_page_size(self, presentation=''):
        w,h=self.screen.get_size();usable=max(80,h-245)
        if presentation=='inventory_items':
            grid_w=w-72-max(280,min(360,(w-72)//3))-16
            return (4 if grid_w>=560 else 3)*max(1,usable//127)
        if presentation=='crafting_categories':return 3*max(1,usable//108)
        if presentation=='crafting_designs':return 3
        if presentation in ('crafting_recipes','crafting_experiments'):return max(1,min(6,usable//98))
        if presentation=='crafting_component_choices':return max(1,min(5,usable//117))
        if presentation:return max(1,min(5,usable//78))
        return max(1,usable//34)

    def document_page_size(self):
        return max(3,(self.screen.get_height()-220)//self.char_h)

    def present_text_entry(self, text):
        self.present(text)
        self._set_input_mode('text')
        self._ui_navigation(confirm=True)
        self.pg.display.flip()

    def present_allocation(self,title,rows,selected,remaining):
        capacity=self.menu_page_size();start=(selected//capacity)*capacity
        self.present_menu(title,rows[start:start+capacity],selected-start,
                          subtitle=f'Points remaining: {remaining}',page_start=start,total=len(rows))
        targets=list(self._pointer_targets)
        for rect,token in targets:
            if token.startswith('UI_SELECT:'):
                i=int(token.split(':')[1])+start
                self._button((rect.right-100,rect.y,44,rect.h),'-',f'UI_MINUS:{i}')
                self._button((rect.right-50,rect.y,44,rect.h),'+',f'UI_PLUS:{i}')
        self._ui_navigation(extra=('Continue','\r'))
        self.pg.display.flip()
        return start
