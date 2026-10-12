from __future__ import annotations

import importlib.util
import math
import re
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from worldseed.core.coords import WorldPos
from worldseed.content.item_catalog import ITEM_TYPE_LABELS
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.presentation.visuals import VisualRegistry
from worldseed.presentation.weather_fx import WeatherFxRenderer
from worldseed.presentation.local_terrain import (
    CONTEXTUAL_WATER_DISPLAY_IDS, DIRECTIONS_8, contextual_display_id,
    configure_terrain_catalog, edge_overlay_signature, is_blendable_land,
    transition_profile, transition_signature,
)
from worldseed.systems.state import pos_key
from worldseed.ui.layout import centered_tile_grid
from worldseed.ui.terminal import pause_realtime_callback

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


from worldseed.ui.pointer import PointerUI, WindowCloseRequested


from worldseed.ui.item_browser import ItemPanelMixin
from worldseed.ui.crafting_browser import CraftingBrowserMixin
from worldseed.ui.workbench_panels import WorkbenchPanelsMixin
from worldseed.ui.salvage_panel import SalvagePanelMixin


class PygameTerminal(ItemPanelMixin, CraftingBrowserMixin, WorkbenchPanelsMixin, SalvagePanelMixin, PointerUI):
    """WORLDSEED's dedicated game-window backend.

    It intentionally exposes the same small interface as the ANSI Terminal so
    existing menus remain usable while the world view migrates to sprites.
    Pygame is imported lazily; the module can still be compiled/tested without
    pygame-ce installed.
    """

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("pygame") is not None

    def __init__(self, width: int = 1280, height: int = 800) -> None:
        if not self.available():
            raise RuntimeError("pygame-ce is not installed. Install with: pip install pygame-ce")
        import pygame
        self.pg = pygame
        self._weather_fx = WeatherFxRenderer(pygame)
        self._weather_animation_context = None
        self._weather_animation_phase = None
        self._weather_static_snapshot = None
        self.width = width
        self.height = height
        self.screen = None
        self.clock = None
        self.font = None
        self.small_font = None
        self.title_font = None
        self.char_w = 9
        self.char_h = 18
        self._sprite_cache: dict[tuple[str, int, int], Any] = {}
        self._terrain_transition_cache: dict[tuple[Any, ...], Any] = {}
        self._terrain_transition_masks: dict[tuple[str, int], Any] = {}
        self._terrain_catalog_token = None
        self._regional_terrain_assets = None
        self._scanline_cache: dict[tuple[int,int], Any] = {}
        self._overlay_cache: dict[tuple[str,int], Any] = {}
        self._water_current_cache = {}
        self._base_layer_cache: dict[tuple[Any, ...], Any] = {}
        self._base_scroll_state: tuple[Any, ...] | None = None
        self._resource_view_cache: dict[tuple[Any, ...], dict[tuple[int,int,int], tuple[Any, Any]]] = {}
        self._resource_cell_cache: dict[tuple[Any, ...], tuple[Any, Any] | None] = {}
        self._entity_spatial_cache_key = None
        self._entity_spatial_cache = None
        self._hover_context: dict[str, Any] | None = None
        self._hover_map_snapshot = None
        self._hover_rect = None
        self._hover_tile_rect = None
        self._hover_cell = None
        self._interior_context = None
        self._interior_placing = None
        self._scanlines_enabled = False
        self._visuals = VisualRegistry.load_default()
        self._character_sprite_paths = frozenset(self._visuals.player_paths("male") + self._visuals.player_paths("female") + self._visuals.npc_paths())
        self._camera: tuple[int, int, int] | None = None
        self._last_mouse = (0, 0)
        self._hud_tooltips = []
        self._hud_tooltip_hover = None
        self._hud_tooltip_since = 0
        self._hud_tooltip_backdrop = None
        self._hud_tooltip_rect = None
        self._hud_tooltip_bounds = None
        self._menu_backdrop_cache = {}
        self._menu_ambient_rects = ()
        self._menu_header_base = None
        self._menu_cursor_rect = None
        self._menu_cursor_backdrop = None
        self._menu_animation_phase = None
        self._menu_nav_rect = None
        self._atlas_dragging = False
        self._atlas_drag_moved = False
        self._atlas_drag_last = (0, 0)
        self._tile_px = 28
        self._input_repeat_armed = True
        self._held_movement: dict[int, int] = {}
        self._active_movement_key: int | None = None
        self._movement_next_repeat_ms = 0
        self._movement_initial_delay_ms = 165
        self._movement_repeat_ms = 72
        self._input_mode = 'world'
        self._pointer_targets = []
        # RC14 Dev37: graphical inventory/storage are floating retained panels
        # instead of full-window modal pages.  Geometry is presentation-only;
        # simulation commands remain authoritative.
        self._floating_panels: dict[str, dict[str, int]] = {}
        self._floating_backdrop = None
        self._floating_panel_id: str | None = None
        self._floating_panel_parent: str | None = None
        self._floating_panel_stack = []
        self._crafting_tab_tooltip = None
        self._ui_window_dragging: str | None = None
        self._ui_window_resizing: str | None = None
        self._ui_window_pointer_last = (0, 0)
        self._current_presentation = ''
        self._inventory_desc_scroll=0
        self._inventory_desc_item=''
        self._inventory_desc_max=0
        self._inventory_desc_rect=None
        self._inventory_desc_track=None
        self._world_activity_tab = 'activity'
        self._activity_footer_context = None
        self._realtime_callback = None
        self._free_movement_callback = None
        self._free_movement_last_ms = 0
        self._movement_redraw_last_ms = 0
        self._movement_redraw_pending = False
        self._combat_active_callback = None
        self._ui_context: dict[str, Any] | None = None
        self._context_menu_origin = (0, 0)
        # Context overlays retain only the pixels under the popup.  This lets
        # water/weather continue animating behind the menu without baking the
        # menu into the world frame or copying the full window every tick.
        self._context_backdrop = None
        self._context_overlay_rect = None
        self._context_menu_state = None
        self._context_opening = False
        self._discovery_pot_center = None
        self._last_combat_effect_uid = 0
        self._theme = {
            "bg": (13, 16, 18),
            "panel": (22, 26, 29),
            "panel2": (28, 33, 37),
            "edge": (66, 77, 81),
            "edge_hi": (122, 139, 139),
            "text": (222, 226, 220),
            "muted": (150, 160, 157),
            "accent": (195, 154, 77),
            "danger": (190, 76, 69),
            "good": (101, 158, 99),
        }

    def enter(self) -> None:
        pg = self.pg
        pg.init()
        pg.display.set_caption("WORLDSEED")
        self.screen = pg.display.set_mode((self.width, self.height), pg.RESIZABLE)
        self.clock = pg.time.Clock()
        pg.event.set_allowed([pg.QUIT, pg.VIDEORESIZE, getattr(pg, 'WINDOWRESIZED', pg.NOEVENT), getattr(pg,'WINDOWFOCUSLOST',pg.NOEVENT), pg.MOUSEMOTION, pg.MOUSEWHEEL, pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP, pg.KEYDOWN, pg.KEYUP])
        # Movement repeat is generated by WORLDSEED, not SDL/OS. This keeps one
        # paced movement intent in flight and prevents queued repeats from being
        # replayed after a slow render frame or after the key is released.
        pg.key.set_repeat()
        self._input_repeat_armed = True
        self._held_movement.clear()
        self._active_movement_key = None
        self._movement_next_repeat_ms = 0
        self._free_movement_last_ms = pg.time.get_ticks()
        self._movement_redraw_last_ms = 0
        self._movement_redraw_pending = False
        self._rebuild_fonts()
        pg.mouse.set_visible(True)
        # Reuse a generated asset as a recognizable app icon.
        icon_path = self._visuals.special("player")
        if icon_path and icon_path.exists():
            try: pg.display.set_icon(pg.image.load(str(icon_path)))
            except Exception: pass

    def restore(self) -> None:
        try:
            self.pg.mouse.set_visible(True)
            self.pg.quit()
        except Exception:
            pass

    def set_realtime_callback(self, callback) -> None:
        self._realtime_callback = callback

    def set_free_movement_callback(self, callback) -> None:
        self._free_movement_callback = callback
        self._free_movement_last_ms = self.pg.time.get_ticks() if callback else 0
        self._movement_redraw_last_ms = 0
        self._movement_redraw_pending = False

    def pause_realtime(self):
        return pause_realtime_callback(self)

    def set_combat_callback(self, callback) -> None:
        self._combat_active_callback = callback

    def _pump_realtime(self) -> bool:
        if getattr(self, '_realtime_pause_depth', 0):
            return False
        callback=self._realtime_callback
        return bool(callback and callback())

    def _pump_free_movement(self, now_ms: int | None = None) -> bool:
        callback=self._free_movement_callback
        if callback is None:
            return False
        now=int(self.pg.time.get_ticks() if now_ms is None else now_ms)
        if (getattr(self,'_realtime_pause_depth',0) or self._input_mode!='world'
                or self._interior_context is not None
                or (self._combat_active_callback and self._combat_active_callback())):
            self._free_movement_last_ms=now
            return False
        if not self._free_movement_last_ms:
            self._free_movement_last_ms=now
            return False
        elapsed=max(0,now-self._free_movement_last_ms)
        if elapsed<16:
            return False
        self._free_movement_last_ms=now
        dt=min(0.10,elapsed/1000.0)
        held=self._held_movement if self._active_movement_key is not None else {}
        pg=self.pg
        dx=int(any(k in held for k in (pg.K_d,pg.K_RIGHT)))-int(any(k in held for k in (pg.K_a,pg.K_LEFT)))
        dy=int(any(k in held for k in (pg.K_s,pg.K_DOWN)))-int(any(k in held for k in (pg.K_w,pg.K_UP)))
        sprint=bool(pg.key.get_mods() & pg.KMOD_SHIFT)
        changed=bool(callback(dt,dx,dy,sprint))
        if changed:
            self._entity_spatial_cache_key=None
            self._movement_redraw_pending=True
        if not self._movement_redraw_pending:
            return False
        # Physics keeps its 16-ms cadence; expensive full-scene redraws do
        # not. On large viewports this keeps the input loop responsive while
        # fractional motion still advances at the correct wall-clock speed.
        area=self.screen.get_width()*self.screen.get_height() if self.screen else 0
        interval=50 if area>1_600_000 else 33
        last=self._movement_redraw_last_ms
        if last and now-last<interval:
            return False
        self._movement_redraw_pending=False
        self._movement_redraw_last_ms=now
        return True

    def _rebuild_fonts(self) -> None:
        pg = self.pg
        # Consolas is common on Windows; SysFont falls back cross-platform.
        self.font = pg.font.SysFont("Consolas,DejaVu Sans Mono,Liberation Mono", 17)
        self.small_font = pg.font.SysFont("Consolas,DejaVu Sans Mono,Liberation Mono", 14)
        self.title_font = pg.font.SysFont("Consolas,DejaVu Sans Mono,Liberation Mono", 21, bold=True)
        self.char_w = max(8, self.font.size("M")[0])
        self.char_h = max(16, self.font.get_linesize())

    def size(self) -> tuple[int, int]:
        if self.screen is None:
            return 100, 30
        w, h = self.screen.get_size()
        # Menus are laid out in virtual terminal cells. Reserve window chrome.
        return max(60, (w - 36) // self.char_w), max(18, (h - 46) // self.char_h)

    def _resize(self, w: int, h: int) -> None:
        new_size=(max(800, int(w)), max(520, int(h)))
        # pygame-ce/SDL2 resizes the surface automatically on Windows.
        # Re-entering set_mode for an already-applied WINDOWRESIZED event
        # recreates the display and can generate more resize events.
        current=self.pg.display.get_surface()
        if current is not None and current.get_size()==new_size:
            self.screen=current
        else:
            self.screen=self.pg.display.set_mode(new_size,self.pg.RESIZABLE)
        if (self.width,self.height)==new_size and current is not None and current.get_size()==new_size:
            return
        self._pointer_targets.clear()
        self.width,self.height=new_size
        self._movement_redraw_last_ms=0
        self._movement_redraw_pending=False
        self._base_layer_cache.clear(); self._base_scroll_state=None; self._resource_view_cache.clear(); self._terrain_transition_cache.clear(); self._terrain_transition_masks.clear()
        self._hover_context=None; self._hover_map_snapshot=None; self._hover_rect=None; self._hover_tile_rect=None; self._hover_cell=None
        self._interior_context = None
        self._menu_backdrop_cache.clear();self._menu_cursor_rect=None;self._menu_cursor_backdrop=None

    def discard_pending_input(self) -> None:
        """Discard startup keys and prevent a held key from repeating into play.

        World preparation is synchronous and can last long enough for pygame's
        repeat timer to keep producing KEYDOWN events. Merely clearing the queue
        is not sufficient when Escape (or the confirmation key) is still held: a
        new repeat can arrive immediately afterward. Disable repeat at the world
        transition, clear queued presses, and re-arm repeat on the first genuinely
        new key press. QUIT/window events remain untouched.
        """
        try:
            self.pg.key.set_repeat()
            self._input_repeat_armed = False
            self._held_movement.clear()
            self._active_movement_key = None
            self._movement_next_repeat_ms = 0
            self._movement_redraw_pending = False
            self._movement_redraw_last_ms = 0
            self.pg.event.clear(self.pg.KEYDOWN)
            self.pg.event.clear(self.pg.KEYUP)
        except Exception:
            pass

    def read_key(self) -> str:
        pg = self.pg
        key_map = {
            pg.K_UP: "UP", pg.K_DOWN: "DOWN", pg.K_LEFT: "LEFT", pg.K_RIGHT: "RIGHT",
            pg.K_PAGEUP: "PGUP", pg.K_PAGEDOWN: "PGDN", pg.K_HOME: "HOME", pg.K_END: "END",
            pg.K_ESCAPE: "ESC", pg.K_RETURN: "\r", pg.K_KP_ENTER: "\r", pg.K_BACKSPACE: "\b",
            pg.K_TAB: "\t", pg.K_F1: "F1", pg.K_F2: "F2", pg.K_F3: "F3",
        }
        # Canonical WASD contract retained: pg.K_w,pg.K_a,pg.K_s,pg.K_d
        movement_keys = {
            pg.K_UP: "UP", pg.K_DOWN: "DOWN", pg.K_LEFT: "LEFT", pg.K_RIGHT: "RIGHT",
            pg.K_w: "w", pg.K_a: "a", pg.K_s: "s", pg.K_d: "d",
        }

        def _activate_movement(key: int, now: int) -> str:
            self._held_movement[key] = now
            self._active_movement_key = key
            self._movement_next_repeat_ms = now + (35 if self._interior_context else self._movement_initial_delay_ms)
            return _movement_token()

        def _movement_token() -> str:
            if not self._interior_context:
                return movement_keys[self._active_movement_key]
            held = self._held_movement
            dx = int(any(k in held for k in (pg.K_d, pg.K_RIGHT))) - int(any(k in held for k in (pg.K_a, pg.K_LEFT)))
            dy = int(any(k in held for k in (pg.K_s, pg.K_DOWN))) - int(any(k in held for k in (pg.K_w, pg.K_UP)))
            return f'INTERIOR_MOVE:{dx}:{dy}'

        def _release_movement(key: int) -> None:
            self._held_movement.pop(key, None)
            if key != self._active_movement_key:
                return
            if self._held_movement:
                # If two directions are held, resume the most recently pressed
                # remaining direction without replaying time accumulated while
                # another key was active.
                self._active_movement_key = max(self._held_movement, key=self._held_movement.get)
                self._movement_next_repeat_ms = pg.time.get_ticks() + self._movement_repeat_ms
            else:
                self._active_movement_key = None
                self._movement_next_repeat_ms = 0

        while True:
            now = pg.time.get_ticks()

            # Service already-queued input/window events before advancing
            # realtime or continuous movement. On a maximized/high-cost frame,
            # rendering can take longer than the 16 ms movement cadence. If the
            # movement pump runs first and returns UI_REDRAW every pass, KEYUP
            # can remain queued indefinitely and the player keeps walking until
            # collision makes the movement callback return False.
            event = pg.event.poll()
            if event.type == pg.NOEVENT:
                # Prioritize queued input, then game/simulation presentation.
                # Weather has a separate idle animation loop; running its
                # full-screen compositor before an already-due movement redraw
                # makes a maximized frame paint the same scene twice.
                if self._pump_realtime():
                    return 'UI_REDRAW'
                if self._pump_free_movement(now):
                    return 'UI_REDRAW'
                if not (self._held_movement and self._input_mode=='world'):
                    self._animate_idle_effects(now)
                if self._combat_active_callback and self._combat_active_callback():
                    # Retain pressed keys until KEYUP so queued duplicates cannot
                    # turn the walk into a fight into several unchosen exchanges.
                    self._active_movement_key = None
                    self._movement_next_repeat_ms = 0
                    self._free_movement_last_ms=now
                wait_ms = 50
                if self._free_movement_callback is not None and self._input_mode=='world' and self._interior_context is None:
                    elapsed=max(0,now-self._free_movement_last_ms)
                    wait_ms=max(1,min(50,16-elapsed))
                elif self._active_movement_key is not None:
                    wait_ms = max(1, min(50, self._movement_next_repeat_ms - now))
                try:
                    event = pg.event.wait(wait_ms)
                except TypeError:
                    # Older pygame builds have no timeout overload. Poll with a
                    # short delay so releases still preempt synthetic repeat.
                    event = pg.event.poll()
                    if event.type == pg.NOEVENT:
                        pg.time.wait(wait_ms)

            if event.type == pg.NOEVENT:
                now = pg.time.get_ticks()
                if self._active_movement_key is not None and now >= self._movement_next_repeat_ms:
                    if self._free_movement_callback is not None and self._interior_context is None:
                        continue
                    # Never catch up missed repeats. A slow frame produces one
                    # fresh step, then schedules the next from *now*.
                    self._movement_next_repeat_ms = now + (35 if self._interior_context else self._movement_repeat_ms)
                    return _movement_token()
                continue
            if event.type == pg.QUIT:
                # Window close is a system quit event, not the gameplay Q key.
                # Returning a dedicated token prevents an ordinary Q press from
                # being interpreted as "save and immediately terminate".
                if self._input_mode != 'world':raise WindowCloseRequested()
                return "QUIT"
            if event.type == pg.VIDEORESIZE:
                self._resize(event.w, event.h)
                return 'RESIZE'
            if hasattr(pg, 'WINDOWRESIZED') and event.type == pg.WINDOWRESIZED:
                self._resize(getattr(event, 'x', self.width), getattr(event, 'y', self.height))
                return 'RESIZE'
            if event.type == pg.KEYUP:
                if event.key in movement_keys:
                    was_held=event.key in self._held_movement
                    _release_movement(event.key)
                    # A 30/20-Hz display can have a pending fractional
                    # position update when the key is released. Paint that
                    # final position once without moving another step.
                    if was_held and self._movement_redraw_pending:
                        self._movement_redraw_pending=False
                        self._movement_redraw_last_ms=pg.time.get_ticks()
                        return 'UI_REDRAW'
                continue
            if event.type == pg.MOUSEMOTION:
                self._last_mouse = event.pos
                pending = pg.event.get(pg.MOUSEMOTION)
                if pending:
                    self._last_mouse = pending[-1].pos
                if getattr(self,'_panel_scroll_drag',None):
                    return self._panel_scroll_pointer(self._panel_scroll_drag)
                if self._input_mode in ('ui','text'):self._animate_menu_effects(pg.time.get_ticks(),force=True)
                self._update_hud_tooltip_hover(pg.time.get_ticks())
                if self._ui_window_dragging or self._ui_window_resizing:
                    panel_id=self._ui_window_dragging or self._ui_window_resizing
                    state=self._floating_panels.get(str(panel_id))
                    if state:
                        last=self._ui_window_pointer_last
                        dx=self._last_mouse[0]-last[0];dy=self._last_mouse[1]-last[1]
                        self._ui_window_pointer_last=self._last_mouse
                        sw,sh=self.screen.get_size()
                        if self._ui_window_dragging:
                            state['x']=max(8,min(sw-state['w']-8,state['x']+dx))
                            state['y']=max(8,min(sh-state['h']-8,state['y']+dy))
                        else:
                            min_w,min_h=self._floating_panel_minimum(str(panel_id))
                            state['w']=max(min_w,min(sw-state['x']-8,state['w']+dx))
                            state['h']=max(min_h,min(sh-state['y']-8,state['h']+dy))
                        return 'UI_REDRAW'
                    continue
                if getattr(self,'_atlas_dragging',False):
                    last=getattr(self,'_atlas_drag_last',self._last_mouse)
                    dx=self._last_mouse[0]-last[0];dy=self._last_mouse[1]-last[1]
                    self._atlas_drag_last=self._last_mouse
                    if dx or dy:return f'ATLAS:drag:{dx}:{dy}'
                    continue
                if self._interior_context:
                    from worldseed.ui.interior_view import refresh_hover
                    refresh_hover(self)
                else:
                    self._refresh_hover_only()
                if self._input_mode=='target' and getattr(self,'_combat_targeting',False) and self._hover_context:
                    ctx=self._hover_context;rect=ctx['used']
                    if rect.collidepoint(self._last_mouse):
                        x=ctx['left']+(self._last_mouse[0]-ctx.get('grid_x',rect.x))//ctx['tile_px']
                        y=ctx['top']+(self._last_mouse[1]-ctx.get('grid_y',rect.y))//ctx['tile_px']
                        return f'UI_TARGET_HOVER:{x}:{y}'
                token=self._hit_token(self._last_mouse)
                pointer=pg.SYSTEM_CURSOR_HAND if token else pg.SYSTEM_CURSOR_ARROW
                if pointer!=getattr(self,'_last_pointer_cursor',None):
                    try:pg.mouse.set_cursor(pointer)
                    except pg.error:pass
                    self._last_pointer_cursor=pointer
                if self._input_mode=='ui' and self._current_presentation in ('inventory_unified','crafting_unified','container_inventory','workshop_station','discovery_pot','salvaging_unified'):
                    if self._ui_context is None and token!=getattr(self,'_panel_hover_token',None):
                        self._panel_hover_token=token
                        return 'UI_REDRAW'
                elif self._input_mode=='ui' and token and token.startswith('UI_SELECT:'):
                    if self._ui_context is None:return token.replace('UI_SELECT:', 'UI_HOVER:')
                if self._input_mode=='ui' and token and token.startswith('UI_ACTION:tab:'):
                    return 'UI_REDRAW'
                if self._input_mode=='ui' and self._current_presentation=='npc_dialogue':
                    topic_hover=token if token and token.startswith(('UI_ACTION:topic:','UI_ACTION:path:')) else None
                    if topic_hover!=getattr(self,'_dialogue_topic_hover',None):
                        self._dialogue_topic_hover=topic_hover
                        return 'UI_REDRAW'
                continue
            if event.type == pg.MOUSEWHEEL:
                if self._input_mode != 'world':
                    view=getattr(self,'_panel_detail_view',None)
                    if self._current_presentation in ('inventory_unified','crafting_unified','workshop_station','discovery_pot','salvaging_unified') and view and view[1].collidepoint(self._last_mouse) and event.y:
                        key,rect,maximum=view
                        self._panel_detail_states[key]=max(0,min(maximum,self._panel_detail_states.get(key,0)-event.y*48))
                        return 'UI_REDRAW'
                    if self._current_presentation in ('inventory_unified','crafting_unified','container_inventory','workshop_station','discovery_pot','salvaging_unified') and event.y:
                        return 'UI_WHEEL:'+str(-event.y*self.menu_grid_columns(self._current_presentation))
                    desc=getattr(self,'_inventory_desc_rect',None)
                    if self._current_presentation=='inventory_unified' and desc and desc.collidepoint(self._last_mouse) and event.y:
                        max_scroll=max(0,self._inventory_desc_max)
                        self._inventory_desc_scroll=max(0,min(max_scroll,self._inventory_desc_scroll-(3 if event.y>0 else -3)))
                        return 'UI_REDRAW'
                    if event.y:return 'PGUP' if event.y>0 else 'PGDN'
                    continue
                # Mouse wheel controls local-world zoom.
                if event.y > 0:
                    self._tile_px = min(56, self._tile_px + 4)
                elif event.y < 0:
                    self._tile_px = max(16, self._tile_px - 4)
                else:
                    continue
                self._sprite_cache.clear(); self._base_layer_cache.clear(); self._base_scroll_state=None; self._resource_view_cache.clear(); self._terrain_transition_cache.clear(); self._terrain_transition_masks.clear()
                return 'RESIZE'
            if event.type == pg.MOUSEBUTTONDOWN:
                self._last_mouse=getattr(event,'pos',self._last_mouse)
                if (event.button==1 and self._current_presentation=='inventory_unified'
                        and self._input_mode!='world'):
                    track=getattr(self,'_inventory_desc_track',None)
                    if track is not None and track.collidepoint(self._last_mouse):
                        ratio=(self._last_mouse[1]-track.y)/max(1,track.h)
                        self._inventory_desc_scroll=max(0,min(self._inventory_desc_max,
                            round(ratio*self._inventory_desc_max)))
                        return 'UI_REDRAW'
                if event.button==1:
                    track_token=self._hit_token(self._last_mouse)
                    if track_token in ('UI_SCROLL_TRACK','UI_DETAIL_TRACK'):
                        self._panel_scroll_drag=track_token
                        return self._panel_scroll_pointer(track_token)
                if event.button==1:
                    tab_token=self._hit_token(self._last_mouse)
                    if tab_token in ('FOOTER_TAB:activity','FOOTER_TAB:combat'):
                        self._world_activity_tab=tab_token.split(':',1)[1]
                        footer=self._activity_footer_context
                        if footer is not None:
                            rect,message,sim=footer
                            self._draw_footer(rect,message,sim)
                            pg.display.update(rect)
                        continue
                placing=getattr(self,'_homestead_placement',None)
                if placing and self._input_mode=='world':
                    if event.button==3:
                        self._homestead_placement=None
                        return 'UI_BLUEPRINT_CANCEL'
                    if event.button==1:
                        cell=self._blueprint_cursor_cell(self._last_mouse)
                        if cell is not None:
                            return f"UI_BLUEPRINT_PLACE:{cell[0]}:{cell[1]}:{placing['orientation']}"
                        continue
                if event.button==1:
                    token=self._hit_token(self._last_mouse)
                    if token and token.startswith('UI_WINDOW_DRAG:'):
                        self._ui_window_dragging=token.split(':',1)[1]
                        self._ui_window_resizing=None
                        self._ui_window_pointer_last=self._last_mouse
                        continue
                    if token and token.startswith('UI_WINDOW_RESIZE:'):
                        self._ui_window_resizing=token.split(':',1)[1]
                        self._ui_window_dragging=None
                        self._ui_window_pointer_last=self._last_mouse
                        continue
                    if token and token.startswith('UI_SELECT:') and self._input_mode=='ui':
                        mods=pg.key.get_mods()
                        if mods & pg.KMOD_SHIFT and self._current_presentation in ('inventory_unified','container_inventory'):
                            self._ui_context=None
                            return token.replace('UI_SELECT:','UI_SHIFT_SELECT:')
                        self._ui_context=None
                        if self._current_presentation=='world_context':
                            # A world context menu is a transient overlay. Restore
                            # the exact underlying world before the selected
                            # command opens another panel (for example Storage),
                            # otherwise the popup gets baked into that panel's
                            # retained backdrop.
                            self._restore_context_overlay(clear=True,update=True)
                    if token and token.startswith('UI_ACTION:'):
                        self._ui_context=None
                    if token=='ATLAS_DRAG_ZONE':
                        self._atlas_dragging=True
                        self._atlas_drag_moved=False
                        self._atlas_drag_last=self._last_mouse
                        return 'ATLAS:drag_start'
                    if token:return token
                    if self._input_mode=='world' and self._interior_context and self._interior_placing:
                        from worldseed.ui.interior_view import pointer_units
                        point=pointer_units(self,self._last_mouse)
                        if point is not None:return f'INTERIOR_PLACE:{point[0]}:{point[1]}'
                    if self._current_presentation=='world_context' and self._input_mode=='ui':
                        self._restore_context_overlay(clear=True,update=True)
                        return 'ESC'
                    if self._input_mode=='target' and self._hover_context:
                        ctx=self._hover_context;rect=ctx['used']
                        if rect.collidepoint(self._last_mouse):
                            x=ctx['left']+(self._last_mouse[0]-ctx.get('grid_x',rect.x))//ctx['tile_px']
                            y=ctx['top']+(self._last_mouse[1]-ctx.get('grid_y',rect.y))//ctx['tile_px']
                            return f'UI_WORLD:{x}:{y}'
                if event.button==3:
                    token=self._hit_token(self._last_mouse)
                    if self._input_mode!='world':
                        if self._current_presentation=='world_context':
                            self._restore_context_overlay(clear=True,update=True)
                            return 'ESC'
                        if self._current_presentation=='discovery_pot' and token and token.startswith('UI_ACTION:remove_slot:'):return token
                        # Right click inside graphical UI is contextual, never
                        # an implicit Back/Escape action.
                        if token and token.startswith('UI_SELECT:'):
                            try:idx=int(token.split(':',1)[1])
                            except ValueError:continue
                            self._ui_context={'presentation':self._current_presentation,'index':idx,'pos':self._last_mouse}
                            return f'UI_CONTEXT:{idx}'
                        if self._ui_context is not None:
                            self._ui_context=None
                            return 'UI_REDRAW'
                        continue
                    if self._interior_context:
                        from worldseed.ui.interior_view import pointer_units, pointer_object
                        point=pointer_units(self,self._last_mouse)
                        obj=pointer_object(self,self._last_mouse)
                        if point is not None or obj is not None:
                            self._context_menu_origin=self._last_mouse
                            self._context_backdrop=None;self._context_overlay_rect=None
                            self._context_menu_state=None;self._context_opening=True
                            if obj is not None:return f'INTERIOR_OBJECT:{obj["kind"]}:{obj["uid"]}'
                            return f'INTERIOR_CONTEXT:{point[0]}:{point[1]}'
                    elif self._hover_context:
                        ctx=self._hover_context;rect=ctx['used']
                        if rect.collidepoint(self._last_mouse):
                            x=ctx['left']+(self._last_mouse[0]-ctx.get('grid_x',rect.x))//ctx['tile_px']
                            y=ctx['top']+(self._last_mouse[1]-ctx.get('grid_y',rect.y))//ctx['tile_px']
                            self._context_menu_origin=self._last_mouse
                            self._context_backdrop=None
                            self._context_overlay_rect=None
                            self._context_menu_state=None
                            self._context_opening=True
                            if ctx.get('shell_hit_regions'):
                                from worldseed.ui.exterior_view import shell_at_pointer
                                hit=shell_at_pointer(ctx,self._last_mouse)
                                if hit is not None:
                                    shell,part=hit
                                    return f'UI_BUILDING_MENU:{part}:{shell.uid}'
                            return f'UI_WORLD_MENU:{x}:{y}'
                continue
            if event.type == pg.MOUSEBUTTONUP:
                self._last_mouse=getattr(event,'pos',self._last_mouse)
                if event.button==1 and getattr(self,'_panel_scroll_drag',None):
                    self._panel_scroll_drag=None
                    return 'UI_REDRAW'
                if event.button==1 and (self._ui_window_dragging or self._ui_window_resizing):
                    self._ui_window_dragging=None;self._ui_window_resizing=None
                    return 'UI_REDRAW'
                if event.button==1 and getattr(self,'_atlas_dragging',False):
                    moved=bool(getattr(self,'_atlas_drag_moved',False))
                    self._atlas_dragging=False
                    return 'ATLAS:drag_end' if moved else 'ATLAS_INSPECT'
                continue
            if event.type == getattr(pg,'WINDOWFOCUSLOST',-1):
                self._panel_scroll_drag=None
                self._held_movement.clear();self._active_movement_key=None
                self._movement_next_repeat_ms=0
                self._free_movement_last_ms=pg.time.get_ticks()
                if self._movement_redraw_pending:
                    self._movement_redraw_pending=False
                    return 'UI_REDRAW'
                continue
            if event.type == pg.KEYDOWN:
                if self._input_mode=='world' and getattr(self,'_homestead_placement',None):
                    if event.key==pg.K_ESCAPE:
                        self._homestead_placement=None
                        return 'UI_BLUEPRINT_CANCEL'
                    if event.key==pg.K_r:
                        self._homestead_placement['orientation']=(self._homestead_placement['orientation']+1)%4
                        self._refresh_hover_only(force=True)
                        continue
                    if event.key not in movement_keys and event.key not in (
                            pg.K_EQUALS,pg.K_PLUS,pg.K_KP_PLUS,pg.K_MINUS,pg.K_KP_MINUS,pg.K_0):
                        continue
                if self._input_mode!='world':
                    if event.key in key_map:
                        if event.key==pg.K_ESCAPE and self._current_presentation=='world_context':
                            self._restore_context_overlay(clear=True,update=True)
                        return key_map[event.key]
                    if self._input_mode!='text' and event.key in (pg.K_w,pg.K_a,pg.K_s,pg.K_d):
                        if self._current_presentation in {
                            'inventory_unified','container_inventory','crafting_unified',
                            'workshop_station','discovery_pot','crafting_index','salvaging','salvaging_unified'
                        }:
                            return movement_keys[event.key]
                        continue
                    if event.unicode:return event.unicode
                    continue
                if not self._input_repeat_armed:
                    # Keep SDL repeat disabled permanently. Re-arming here now
                    # means only that fresh post-loading keyboard input is valid.
                    self._input_repeat_armed = True
                if event.key in movement_keys:
                    # Ignore any duplicate/repeat KEYDOWN already queued by the
                    # platform or injected before repeat was disabled. Held
                    # movement is paced solely by the timer above.
                    if event.key in self._held_movement or getattr(event,'repeat',False):
                        continue
                    token=_activate_movement(event.key,pg.time.get_ticks())
                    if self._free_movement_callback is not None and self._interior_context is None:
                        self._free_movement_last_ms=pg.time.get_ticks()
                        continue
                    return token
                if event.key in key_map:
                    return key_map[event.key]
                if event.key in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS):
                    self._tile_px = min(56, self._tile_px + 4)
                    self._sprite_cache.clear(); self._base_layer_cache.clear(); self._base_scroll_state=None; self._resource_view_cache.clear(); self._terrain_transition_cache.clear(); self._terrain_transition_masks.clear()
                    return 'RESIZE'
                if event.key in (pg.K_MINUS, pg.K_KP_MINUS):
                    self._tile_px = max(16, self._tile_px - 4)
                    self._sprite_cache.clear(); self._base_layer_cache.clear(); self._base_scroll_state=None; self._resource_view_cache.clear(); self._terrain_transition_cache.clear(); self._terrain_transition_masks.clear()
                    return 'RESIZE'
                if event.key == pg.K_0:
                    self._tile_px = 28
                    self._sprite_cache.clear(); self._base_layer_cache.clear(); self._base_scroll_state=None; self._resource_view_cache.clear(); self._terrain_transition_cache.clear(); self._terrain_transition_masks.clear()
                    return 'RESIZE'
                if event.unicode:
                    return event.unicode

    def _menu_scene(self, size):
        """Cached painted backdrop; the small light motes animate separately."""
        cached=self._menu_backdrop_cache.get(size)
        if cached is not None:return cached
        pg=self.pg;w,h=size
        scene=pg.Surface(size)
        for yy in range(h):
            t=yy/max(1,h-1)
            color=(int(14+8*t),int(23+12*t),int(25+7*t))
            pg.draw.line(scene,color,(0,yy),(w,yy))
        horizon=int(h*.59)
        pg.draw.polygon(scene,(29,45,43),[(0,horizon),(w//8,horizon-80),(w//4,horizon-22),(w//3,horizon-130),(w//2,horizon-30),(2*w//3,horizon-125),(5*w//6,horizon-45),(w,horizon-100),(w,h)])
        pg.draw.polygon(scene,(19,35,33),[(0,horizon+80),(w//7,horizon-18),(w//4,horizon+74),(w//2,horizon-20),(3*w//4,horizon+65),(w,horizon-15),(w,h)])
        for i in range(22):
            xx=(i*197+71)%max(1,w); yy=horizon+18+(i*71)%max(1,h-horizon+15)
            height=30+(i*31)%90
            pg.draw.line(scene,(13,28,27),(xx,yy),(xx,yy-height),2)
            pg.draw.polygon(scene,(13,30,28),[(xx-18,yy-height//3),(xx,yy-height-17),(xx+18,yy-height//3)])
        pg.draw.line(scene,(79,91,71),(0,horizon+22),(w,horizon+22),1)
        self._menu_backdrop_cache[size]=scene
        return scene

    def _animate_menu_effects(self, now, *, force=False):
        if self.screen is None or self._input_mode not in ('ui','text'):return
        # Atlas and other static UI surfaces share input mode with menus but
        # have no animated menu backdrop. Painting a cursor into their saved
        # frame makes a mouse move alter the map while input is pending.
        if getattr(self, '_static_atlas_view', False) or (self._menu_header_base is None and not self._menu_ambient_rects):
            self.pg.mouse.set_visible(True)
            return
        self.pg.mouse.set_visible(False)
        phase=int(now)//80
        if not force and phase==self._menu_animation_phase:return
        self._menu_animation_phase=phase
        pg=self.pg;dirty=[]
        if self._menu_cursor_rect is not None and self._menu_cursor_backdrop is not None:
            self.screen.blit(self._menu_cursor_backdrop,self._menu_cursor_rect.topleft)
            dirty.append(self._menu_cursor_rect)
        if self._menu_header_base is not None:
            header=pg.Rect(18,18,self._menu_header_base.get_width(),self._menu_header_base.get_height())
            self.screen.blit(self._menu_header_base,header.topleft)
            for i in range(10):
                x=header.x+((i*173+phase*2)%max(1,header.width));y=header.y+6+(i*11)%20
                if x<header.right-8:pg.draw.circle(self.screen,(174,143,86),(x,y),1+(i%2))
            dirty.append(header)
        for rect in self._menu_ambient_rects:
            if rect.width<=0 or rect.height<=0:continue
            scene=self._menu_scene((self.screen.get_width()-36,self.screen.get_height()-75))
            self.screen.blit(scene,rect.topleft,rect.move(-18,-57))
            for i in range(13):
                x=rect.x+(i*83+phase*(1+i%2))%rect.width
                y=rect.y+(i*101-phase*(1+i%3))%rect.height
                pg.draw.circle(self.screen,(101,110,72) if i%3 else (175,135,65),(x,y),1+(i%4==0))
            dirty.append(rect)
        mx,my=self._last_mouse
        if self.screen.get_rect().collidepoint((mx,my)):
            cursor=pg.Rect(mx-8,my-8,36,36).clip(self.screen.get_rect())
            self._menu_cursor_rect=cursor
            self._menu_cursor_backdrop=self.screen.subsurface(cursor).copy()
            pg.draw.circle(self.screen,(159,126,66),(mx+6,my+6),10+(phase%3),1)
            pg.draw.polygon(self.screen,(223,192,115),[(mx,my),(mx+3,my+17),(mx+7,my+12),(mx+12,my+14)],0)
            pg.draw.lines(self.screen,(35,28,20),True,[(mx,my),(mx+3,my+17),(mx+7,my+12),(mx+12,my+14)],1)
            pg.draw.circle(self.screen,(244,224,164),(mx+6,my+6),2)
            dirty.append(cursor)
        else:self._menu_cursor_rect=None;self._menu_cursor_backdrop=None
        if dirty:pg.display.update(dirty)

    def _draw_chrome(self, title: str = "WORLDSEED") -> tuple[int, int, int, int]:
        pg = self.pg; screen = self.screen; assert screen is not None
        self._static_atlas_view = 'ATLAS' in title
        self._pointer_targets.clear()
        self._hud_tooltips.clear()
        self._hud_tooltip_hover = None
        self._hud_tooltip_rect = None
        self._hud_tooltip_backdrop = None
        self._menu_cursor_rect=None;self._menu_cursor_backdrop=None
        self._menu_ambient_rects=();self._menu_nav_rect=None;self._menu_animation_phase=None
        mode=('target' if getattr(self,'_drawing_target',False) else 'world') if title in ('WORLDSEED // LOCAL','WORLDSEED // INTERIOR') else 'ui'
        self._set_input_mode(mode)
        pg.mouse.set_visible(mode not in ('ui','text'))
        if mode in ('world','target'):
            self._floating_backdrop=None
            self._floating_panel_id=None
            self._floating_panel_parent=None
            self._floating_panel_stack.clear()
            self._ui_context=None
            self._context_backdrop=None
            self._context_overlay_rect=None
            self._context_menu_state=None
        self._hover_context = None
        self._hover_map_snapshot = None
        self._hover_rect = None
        self._hover_tile_rect = None
        self._hover_cell = None
        w, h = screen.get_size(); th = self._theme
        screen.fill(th["bg"])
        # beveled application frame
        pg.draw.rect(screen, th["panel"], (10, 10, w-20, h-20), border_radius=5)
        pg.draw.rect(screen, th["edge"], (10, 10, w-20, h-20), width=1, border_radius=5)
        pg.draw.line(screen, th["edge_hi"], (12, 11), (w-13, 11), 1)
        pg.draw.rect(screen, th["panel2"], (18, 18, w-36, 31), border_radius=3)
        label = self.title_font.render(title, True, th["accent"])
        screen.blit(label, (29, 22))
        sub = self.small_font.render("LIVING WORLD // HYBRID DISPLAY", True, th["muted"])
        screen.blit(sub, (w-sub.get_width()-29, 27))
        if mode=='ui':
            scene=self._menu_scene((w-36,h-75));screen.blit(scene,(18,57))
            self._menu_header_base=screen.subsurface(pg.Rect(18,18,w-36,31)).copy()
        else:self._menu_header_base=None
        return 18, 57, w-36, h-75

    def present_loading(self, phase: str, progress: float, detail: str = '', subtitle: str = 'PREPARING SEEDED WORLD') -> None:
        """Draw a responsive startup-generation screen.

        Generation is intentionally synchronous before play begins, but event
        pumping keeps the OS window responsive while terrain/resources are being
        prepared and persisted.
        """
        pg=self.pg;screen=self.screen
        if screen is None:return
        progress=max(0.0,min(1.0,float(progress)))
        try:pg.event.pump()
        except Exception:pass
        x,y,w,h=self._draw_chrome("WORLDSEED // WORLD GENERATION")
        pg.draw.rect(screen,(12,15,17),(x,y,w,h),border_radius=2)
        card_w=min(760,max(520,w-120));card_h=250
        card=pg.Rect(x+(w-card_w)//2,y+max(30,(h-card_h)//2),card_w,card_h)
        pg.draw.rect(screen,self._theme['panel2'],card,border_radius=6)
        pg.draw.rect(screen,self._theme['edge_hi'],card,1,border_radius=6)
        title=self.title_font.render('GENERATING WORLD',True,self._theme['accent']);screen.blit(title,(card.x+28,card.y+26))
        sub=self.small_font.render(subtitle,True,self._theme['muted']);screen.blit(sub,(card.x+28,card.y+59))
        phase_surf=self.font.render(str(phase),True,self._theme['text']);screen.blit(phase_surf,(card.x+28,card.y+98))
        if detail:
            ds=self.small_font.render(str(detail)[:84],True,self._theme['muted']);screen.blit(ds,(card.x+28,card.y+126))
        bar=pg.Rect(card.x+28,card.y+164,card.width-56,18)
        pg.draw.rect(screen,(44,50,53),bar,border_radius=5)
        fill=pg.Rect(bar.x,bar.y,int(bar.width*progress),bar.height)
        if fill.width>0:pg.draw.rect(screen,self._theme['accent'],fill,border_radius=5)
        pct=self.font.render(f'{int(progress*100):3d}%',True,self._theme['text']);screen.blit(pct,(bar.right-pct.get_width(),bar.bottom+13))
        note=self.small_font.render('Terrain and resource placement are being persisted so exploration starts from prepared data.',True,self._theme['muted'])
        screen.blit(note,(card.x+28,card.bottom-33))
        pg.display.flip()

    def present(self, text: str) -> None:
        """Render legacy terminal UI inside the custom game window."""
        # Console/menu screens do not own the gameplay hover context. Clearing
        # it prevents mouse motion from repainting a stale map over a menu.
        self._hover_context=None; self._hover_map_snapshot=None
        self._hover_rect=None; self._hover_tile_rect=None; self._hover_cell=None
        pg = self.pg; screen = self.screen
        if screen is None: return
        x, y, w, h = self._draw_chrome("WORLDSEED // CONSOLE")
        self._paint_menu_veil((x,y,w,h))
        lines = ANSI_RE.sub('', text).splitlines()
        top = y + 10
        for i, raw in enumerate(lines):
            if top + i*self.char_h > y+h-self.char_h: break
            # simple semantic colorization preserves readability without ANSI.
            color = self._theme["text"]
            if raw.startswith("+") or raw.startswith("|"): color = (185,194,190)
            if "[READY]" in raw: color = self._theme["good"]
            if "[NEEDS]" in raw or "MISSING" in raw: color = self._theme["danger"]
            surf = self.font.render(raw, True, color)
            screen.blit(surf, (x+11, top+i*self.char_h))
        self._ui_navigation(confirm=True)
        self._draw_scanlines((x,y,w,h))
        pg.display.flip()
        self.clock.tick(120)

    def _ui_domain(self, title: str) -> tuple[str, tuple[str, ...], str]:
        """Return graphical menu domain, tabs and active tab.

        This is presentation-only.  The widgets and simulation remain the
        authority for navigation and actions; the pygame layer simply gives
        their existing structured rows a native game-window skin.
        """
        upper=title.upper()
        if 'CRAFTING' in upper:
            tabs=('RECIPES','EXPERIMENT','MATERIALS','TECH TREE','DESIGNS')
            if 'EXPERIMENT' in upper or 'TRIAL' in upper:active='EXPERIMENT'
            elif 'MATERIAL' in upper:active='MATERIALS'
            elif 'TREE' in upper:active='TECH TREE'
            elif 'DESIGN' in upper:active='DESIGNS'
            else:active='RECIPES'
            return 'CRAFTING',tabs,active
        if 'INVENTORY' in upper or 'CARRIED ITEMS' in upper or 'PACK OVERVIEW' in upper:
            tabs=('PACK','ITEMS','STORAGE','EQUIPMENT','READ')
            if 'CARRIED' in upper or 'ITEM' in upper:active='ITEMS'
            elif 'STORAGE' in upper:active='STORAGE'
            elif 'EQUIPMENT' in upper:active='EQUIPMENT'
            elif 'READ' in upper:active='READ'
            else:active='PACK'
            return 'INVENTORY',tabs,active
        return title.split('//',1)[0].strip() or 'MENU',(),''

    def _fit_ui_text(self, text: str, font, max_width: int) -> str:
        text=str(text)
        if max_width <= 20 or font.size(text)[0] <= max_width:return text
        suffix='…';lo,hi=0,len(text)
        while lo<hi:
            mid=(lo+hi+1)//2
            if font.size(text[:mid]+suffix)[0] <= max_width:lo=mid
            else:hi=mid-1
        return text[:lo]+suffix

    def _paint_menu_veil(self, rect):
        veil=self.pg.Surface((rect[2],rect[3]),self.pg.SRCALPHA)
        veil.fill((15,20,21,204))
        self.screen.blit(veil,rect[:2])
        self.pg.draw.rect(self.screen,(94,92,67),rect,1,border_radius=4)

    def _draw_ui_tabs(self, title: str, x: int, y: int, w: int) -> int:
        # Read-only location label: navigation is provided by actual menu cards.
        domain,tabs,active=self._ui_domain(title)
        if not tabs:return y
        text=self.small_font.render(f'{domain} / {active}',True,self._theme['muted'])
        self.screen.blit(text,(x,y+2))
        return y+26

    def _semantic_row_color(self, text: str):
        upper=text.upper();th=self._theme
        if '[READY]' in upper or '[KNOWN]' in upper:return th['good']
        if '[NEEDS]' in upper or '[LOCKED]' in upper or 'MISSING' in upper:return th['danger']
        if '[TEST]' in upper:return th['accent']
        return th['text']

    def _feature_shell(self, domain: str, title: str, subtitle: str=''):
        pg=self.pg;screen=self.screen
        x,y,w,h=self._draw_chrome(f'WORLDSEED // {domain}')
        self._paint_menu_veil((x,y,w,h))
        cx=x+18;cy=y+14;cw=w-36
        heading=self.title_font.render(title,True,self._theme['text']);screen.blit(heading,(cx,cy));cy+=heading.get_height()+7
        if subtitle:
            sub=self.small_font.render(self._fit_ui_text(subtitle,self.small_font,cw),True,self._theme['muted'])
            screen.blit(sub,(cx,cy));cy+=21
        return x,y,w,h,cx,cy,cw

    def _floating_panel_minimum(self, panel_id: str) -> tuple[int,int]:
        if panel_id in ('homestead_styles','homestead_depot'):return (540,440)
        if panel_id=='crafting':return (740,500)
        return (760,500) if panel_id=='container_inventory' else (640,440)

    def _floating_panel_state(self, panel_id: str) -> dict[str,int]:
        sw,sh=self.screen.get_size()
        min_w,min_h=self._floating_panel_minimum(panel_id)
        min_w=min(min_w,max(1,sw-16));min_h=min(min_h,max(1,sh-16))
        home_ui=panel_id in ('homestead_styles','homestead_depot')
        default_w=min(sw-48,760 if home_ui else 1080 if panel_id in ('container_inventory','crafting') else 900)
        default_h=min(sh-48,580 if home_ui else 680 if panel_id in ('container_inventory','crafting') else 620)
        state=self._floating_panels.get(panel_id)
        if state is None:
            base_x=max(12,(sw-default_w)//2);base_y=max(12,(sh-default_h)//2)
            # A second gameplay panel is cascaded so the retained parent title
            # and edge remain visible instead of being hidden pixel-for-pixel.
            if self._floating_panel_parent not in (None,panel_id):
                parent=self._floating_panels.get(self._floating_panel_parent,{})
                base_x=int(parent.get('x',base_x))+38;base_y=int(parent.get('y',base_y))+34
            state={'x':base_x,'y':base_y,
                   'w':max(min_w,default_w),'h':max(min_h,default_h)}
            self._floating_panels[panel_id]=state
        state['w']=max(min_w,min(sw-16,state['w']));state['h']=max(min_h,min(sh-16,state['h']))
        state['x']=max(8,min(sw-state['w']-8,state['x']));state['y']=max(8,min(sh-state['h']-8,state['y']))
        return state

    def _suspend_world_hover_animation(self) -> None:
        """Detach world-only hover/animation state while an overlay owns input.

        The retained local-world animation snapshots can otherwise repaint the
        map during read_key() idle ticks, visually erasing a floating/context
        panel while its UI modal remains active.
        """
        self._hover_context=None;self._hover_map_snapshot=None
        self._hover_rect=None;self._hover_tile_rect=None;self._hover_cell=None

    def push_floating_panel(self) -> None:
        """Retain the active panel while a companion panel receives focus."""
        if self.screen is None:return
        self._floating_panel_stack.append((
            self._floating_panel_id,self.screen.copy(),self._floating_backdrop,
            self._floating_panel_parent,
        ))

    def pop_floating_panel(self) -> None:
        """Restore the prior focused panel without redrawing the world."""
        if not self._floating_panel_stack or self.screen is None:return
        panel_id,snapshot,backdrop,parent=self._floating_panel_stack.pop()
        self.screen.blit(snapshot,(0,0))
        self._floating_panel_id=panel_id;self._floating_backdrop=backdrop
        self._floating_panel_parent=parent

    def _floating_feature_shell(self, panel_id: str, domain: str, title: str, subtitle: str='', *, show_heading: bool=True):
        pg=self.pg;screen=self.screen;assert screen is not None
        self._suspend_world_hover_animation()
        if self._floating_backdrop is None or self._floating_panel_id!=panel_id:
            previous=self._floating_panel_id
            self._floating_backdrop=screen.copy()
            self._floating_panel_id=panel_id
            self._floating_panel_parent=previous if previous in {'inventory_unified','crafting'} else None
        screen.blit(self._floating_backdrop,(0,0))
        self._menu_cursor_rect=None;self._menu_cursor_backdrop=None
        self._pointer_targets.clear();self._set_input_mode('ui')
        state=self._floating_panel_state(panel_id)
        x,y,w,h=state['x'],state['y'],state['w'],state['h']
        shadow=pg.Rect(x+6,y+7,w,h);pg.draw.rect(screen,(0,0,0),shadow,border_radius=8)
        outer=pg.Rect(x,y,w,h)
        pg.draw.rect(screen,(18,23,24),outer,border_radius=8)
        pg.draw.rect(screen,(99,86,61),outer,2,border_radius=8)
        pg.draw.rect(screen,(31,38,37),outer.inflate(-10,-10),1,border_radius=5)
        titlebar=pg.Rect(x,y,w,42)
        pg.draw.rect(screen,self._theme['panel2'],titlebar,border_radius=8)
        pg.draw.line(screen,self._theme['edge'],(x,y+42),(x+w,y+42),1)
        pg.draw.line(screen,self._theme['accent'],(x+14,y+42),(x+min(w-14,150),y+42),2)
        self._ui_target(pg.Rect(x+8,y+4,w-58,34),f'UI_WINDOW_DRAG:{panel_id}')
        domain_s=self.small_font.render(domain.upper(),True,self._theme['accent']);screen.blit(domain_s,(x+14,y+7))
        title_x=x+14+domain_s.get_width()+16
        title_s=self.font.render(self._fit_ui_text(title,self.font,max(1,x+w-150-title_x)),True,self._theme['text']);screen.blit(title_s,(title_x,y+8))
        self._button((x+w-38,y+7,28,27),'×','ESC')
        grip=pg.Rect(x+w-20,y+h-20,14,14)
        pg.draw.line(screen,self._theme['edge_hi'],(grip.x+3,grip.bottom-2),(grip.right-2,grip.y+3),2)
        pg.draw.line(screen,self._theme['edge'],(grip.x+7,grip.bottom-2),(grip.right-2,grip.y+7),2)
        self._ui_target(grip,f'UI_WINDOW_RESIZE:{panel_id}')
        cx=x+16;cy=y+52;cw=w-32
        if show_heading:
            heading=self.title_font.render(self._fit_ui_text(title,self.title_font,cw),True,self._theme['text']);screen.blit(heading,(cx,cy));cy+=heading.get_height()+5
        if subtitle:
            sub=self.small_font.render(self._fit_ui_text(subtitle,self.small_font,cw),True,self._theme['muted']);screen.blit(sub,(cx,cy));cy+=19
        return x,y,w,h,cx,cy,cw

    def _draw_npc_portrait(self, spec, rect) -> None:
        """Paint the same composite face in every NPC panel, without world reads."""
        pg=self.pg;rect=pg.Rect(rect)
        pg.draw.rect(self.screen,(12,17,18),rect,border_radius=5)
        if spec is not None:
            from worldseed.presentation.portraits import PortraitComposer
            composer=getattr(self,'_portrait_composer',None)
            if composer is None:
                composer=self._portrait_composer=PortraitComposer(max_entries=96)
            portrait=composer.render(spec,size=min(rect.width,rect.height))
            self.screen.blit(portrait,portrait.get_rect(center=rect.center))
        pg.draw.rect(self.screen,self._theme['edge_hi'],rect,1,border_radius=5)
        self._npc_portrait_rect=rect

    def _draw_floating_footer(self, x:int,y:int,w:int,h:int, text:str='Drag title • Resize corner • Esc closes') -> None:
        self.pg.draw.line(self.screen,self._theme['edge'],(x+16,y+h-39),(x+w-16,y+h-39))
        s=self.small_font.render(self._fit_ui_text(text,self.small_font,w-44),True,self._theme['muted'])
        self.screen.blit(s,(x+16,y+h-27))

    def _storage_gauge(self, rect, used: float, capacity: float) -> None:
        pg=self.pg;ratio=max(0.,min(1.,used/max(.001,capacity)))
        pg.draw.rect(self.screen,(49,53,48),rect,border_radius=3)
        fill=pg.Rect(rect.x,rect.y,round(rect.width*ratio),rect.height)
        if fill.width:pg.draw.rect(self.screen,self._theme['danger'] if ratio>=.9 else self._theme['accent'],fill,border_radius=3)

    def _paint_action_popup(self, origin, rect, title: str, actions, *, opening: bool, subtitle: str='', selected: int=-1, register_targets: bool=True) -> None:
        """Paint cursor-born buttons; only the finished layout owns hit targets."""
        pg=self.pg;screen=self.screen;x,y,w,h=rect
        surface=pg.Surface((w,h),pg.SRCALPHA)
        pg.draw.rect(surface,(19,24,25),(0,0,w,h),border_radius=7)
        pg.draw.rect(surface,self._theme['accent'],(0,0,w,h),1,border_radius=7)
        header=62 if subtitle else 42
        pg.draw.rect(surface,(39,47,44),(6,6,w-12,header-12),border_radius=4)
        label=self.small_font.render(self._fit_ui_text(title,self.small_font,w-26),True,self._theme['accent'])
        surface.blit(label,(13,11))
        if subtitle:
            note=self.small_font.render(self._fit_ui_text(subtitle,self.small_font,w-26),True,self._theme['muted'])
            surface.blit(note,(13,31))
        for i,(name,_) in enumerate(actions):
            row=pg.Rect(7,header+i*36,w-14,32)
            active=i==selected or row.move(x,y).collidepoint(self._last_mouse)
            pg.draw.rect(surface,(52,60,54) if active else (29,36,35),row,border_radius=4)
            pg.draw.rect(surface,self._theme['accent'] if active else self._theme['edge'],row,1,border_radius=4)
            surf=self.small_font.render(self._fit_ui_text(name,self.small_font,w-32),True,self._theme['text'])
            surface.blit(surf,(row.x+10,row.centery-surf.get_height()//2))
        if opening:
            start=pg.time.get_ticks();base=screen.copy()
            while True:
                t=min(1.,(pg.time.get_ticks()-start)/145.)
                eased=1-(1-t)**3;scale=.28+.72*eased
                fw=max(1,round(w*scale));fh=max(1,round(h*scale))
                fx=round(origin[0]+(x-origin[0])*eased)
                fy=round(origin[1]+(y-origin[1])*eased)
                screen.blit(base,(0,0))
                screen.blit(pg.transform.smoothscale(surface,(fw,fh)),(fx,fy))
                pg.display.flip()
                if t>=1:break
                pg.event.pump();self.clock.tick(120)
        screen.blit(surface,(x,y))
        if register_targets:
            for i,(_,token) in enumerate(actions):
                self._ui_target(pg.Rect(x+7,y+header+i*36,w-14,32),token)

    def _draw_item_context_popup(self, rows, data: dict, selected: int) -> None:
        ctx=self._ui_context
        if not ctx or ctx.get('presentation')!=self._current_presentation or int(ctx.get('index',-1))!=selected:return
        pg=self.pg;screen=self.screen
        mx,my=ctx.get('pos',self._last_mouse)
        actions=[]
        if self._current_presentation=='inventory_unified':
            items=data.get('items',{});row=rows[selected] if rows and 0<=selected<len(rows) else None
            iid=getattr(row,'key','') if row else '';meta=items.get(iid,{})
            amount=max(1,min(int(data.get('action_amount',1)),max(1,int(meta.get('count',1)))))
            if meta.get('can_use'):actions.append(('Use','UI_ACTION:use'))
            actions.extend([(f'Drop x{amount}','UI_ACTION:drop'),('Set quantity to half','UI_ACTION:split')])
            if data.get('near_storage'):actions.append((f'Store x{amount}','UI_ACTION:store'))
        elif self._current_presentation=='container_inventory':
            entries=data.get('entries',{});row=rows[selected] if rows and 0<=selected<len(rows) else None
            meta=entries.get(getattr(row,'key','') if row else '',{})
            count=max(1,int(meta.get('count',1)))
            direction='Store all →' if meta.get('side')=='pack' else '← Take all'
            actions.extend([(direction,'UI_ACTION:quick_transfer'),('Transfer selected amount','UI_ACTION:transfer'),('Set quantity to half','UI_ACTION:split')])
        if not actions:return
        pw=max(216,max(self.small_font.size(label)[0] for label,_ in actions)+34);ph=48+len(actions)*36
        sw,sh=screen.get_size();px=max(8,min(mx+8,sw-pw-8));py=max(8,min(my+8,sh-ph-8))
        self._paint_action_popup((mx,my),(px,py,pw,ph),'ITEM ACTIONS',actions,opening=not ctx.get('opened',False))
        ctx['opened']=True

    def _restore_context_overlay(self, *, clear: bool, update: bool=False) -> None:
        rect=self._context_overlay_rect
        if self._context_backdrop is not None and rect is not None and self.screen is not None:
            self.screen.blit(self._context_backdrop,rect.topleft)
            if update:self.pg.display.update(rect)
        if clear:
            self._context_backdrop=None;self._context_overlay_rect=None;self._context_menu_state=None

    def _redraw_live_context_overlay(self) -> None:
        state=self._context_menu_state;rect=self._context_overlay_rect
        if not state or rect is None or self.screen is None:return
        # The world animation just repainted the underlying region. Capture the
        # new live pixels, then put the popup back without rebuilding hit targets.
        self._context_backdrop=self.screen.subsurface(rect).copy()
        self._paint_action_popup(state['origin'],rect,state['title'],state['actions'],
                                 opening=False,subtitle=state['subtitle'],selected=state['selected'],
                                 register_targets=False)
        self.pg.display.update(rect)

    def _present_context_menu(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        pg=self.pg;screen=self.screen;assert screen is not None
        # Remove the previous draw of this transient popup before laying it out
        # again.  Unlike floating windows, world context menus keep live world
        # animation state attached.
        self._restore_context_overlay(clear=False,update=False)
        self._pointer_targets.clear();self._set_input_mode('ui')
        labels=[getattr(r,'label',str(r)) for r in rows]
        width=max(260,min(430,max([self.small_font.size(x)[0] for x in labels]+[220])+42))
        height=(68 if subtitle else 48)+len(rows)*36
        sw,sh=screen.get_size();mx,my=self._context_menu_origin
        x=max(8,min(sw-width-8,mx+8));y=max(8,min(sh-height-8,my+8));rect=pg.Rect(x,y,width,height)
        actions=[(getattr(row,'label',str(row)),f'UI_SELECT:{i}') for i,row in enumerate(rows)]
        self._context_overlay_rect=rect
        self._context_backdrop=screen.subsurface(rect).copy()
        self._context_menu_state={'origin':(mx,my),'title':title,'actions':actions,'subtitle':subtitle,'selected':selected}
        self._paint_action_popup((mx,my),rect,title,actions,opening=self._context_opening,subtitle=subtitle,selected=selected)
        self._context_opening=False
        pg.display.flip();self.clock.tick(120)

    def _draw_feature_footer(self, x:int,y:int,w:int,h:int,footer:str) -> None:
        self._ui_navigation()

    def _draw_metric(self, rect, label: str, value: str, *, accent=None) -> None:
        pg=self.pg;accent=accent or self._theme['accent']
        pg.draw.rect(self.screen,self._theme['panel2'],rect,border_radius=6)
        pg.draw.rect(self.screen,self._theme['edge'],rect,width=1,border_radius=6)
        lab=self.small_font.render(label.upper(),True,self._theme['muted']);self.screen.blit(lab,(rect.x+10,rect.y+7))
        val=self.font.render(value,True,accent);self.screen.blit(val,(rect.x+10,rect.bottom-val.get_height()-7))

    def _draw_item_icon(self, item_id: str, rect, *, scale: float=0.92) -> None:
        ref=self._visuals.ref('items',item_id)
        path=self._visuals.resolve(ref)
        max_w=max(8,int(rect.width*scale));max_h=max(8,int(rect.height*scale))
        surf=self._load_sprite(path,max_w,max_h)
        if surf is not None:
            self.screen.blit(surf,(rect.centerx-surf.get_width()//2,rect.centery-surf.get_height()//2))

    def _draw_menu_card(self, rect, label: str, active: bool, *, detail: str='', badge: str='') -> None:
        pg=self.pg;th=self._theme
        if badge.isdigit():self._ui_target(rect,f'UI_SELECT:{int(badge)-1}')
        pg.draw.rect(self.screen,(39,42,40) if active else th['panel2'],rect,border_radius=6)
        pg.draw.rect(self.screen,th['accent'] if active else th['edge'],rect,width=2 if active else 1,border_radius=6)
        if active:pg.draw.rect(self.screen,th['accent'],(rect.x,rect.y,5,rect.h),border_radius=3)
        if badge:
            b=self.small_font.render(badge,True,th['accent'] if active else th['muted']);self.screen.blit(b,(rect.x+12,rect.y+8))
            tx=rect.x+44
        else:tx=rect.x+14
        f=self.font if rect.height>=42 else self.small_font
        lab=f.render(self._fit_ui_text(label,f,rect.right-tx-12),True,th['text']);self.screen.blit(lab,(tx,rect.y+8))
        if detail and rect.height>=50:
            det=self.small_font.render(self._fit_ui_text(detail,self.small_font,rect.right-tx-12),True,th['muted'])
            self.screen.blit(det,(tx,rect.bottom-det.get_height()-8))

    def present_feature_menu(self, presentation: str, title: str, rows, selected: int, *, subtitle: str='', breadcrumb: str='',
                             footer: str='', page_start: int=0, total: int|None=None, data: dict|None=None) -> None:
        data=data or {}
        self._current_presentation=presentation
        handlers={
            'inventory_home':self._present_inventory_home,
            'inventory_items':self._present_inventory_items,
            'inventory_unified':self._present_inventory_unified,
            'container_inventory':self._present_container_inventory,
            'crafting_unified':self._present_crafting_unified,
            'salvaging':self._present_salvaging,
            'salvaging_unified':self._present_salvaging_unified,
            'workshop_station':self._present_workshop_station,
            'discovery_pot':self._present_discovery_pot,
            'crafting_index':self._present_crafting_index,
            'inventory_item_actions':self._present_inventory_item_actions,
            'world_context':self._present_context_menu,
            'npc_profile':self._present_npc_profile,
            'npc_dialogue':self._present_npc_dialogue,
            'crafting_home':self._present_crafting_home,
            'crafting_categories':self._present_crafting_categories,
            'crafting_recipes':self._present_crafting_recipes,
            'crafting_experiments':self._present_crafting_experiments,
            'crafting_designs':self._present_crafting_designs,
            'crafting_component_choices':self._present_crafting_component_choices,
            'crafting_experiment_detail':self._present_crafting_recipe_detail,
            'crafting_recipe_detail':self._present_crafting_recipe_detail,
        }
        handler=handlers.get(presentation)
        if handler is None:
            return self.present_menu(title,rows,selected,subtitle=subtitle,breadcrumb=breadcrumb,footer=footer,page_start=page_start,total=total)
        handler(title,rows,selected,subtitle=subtitle,breadcrumb=breadcrumb,footer=footer,page_start=page_start,total=total,data=data)

    def present_feature_document(self, presentation: str, title: str, lines: list[str], *, footer: str='', breadcrumb: str='',
                                 data: dict|None=None, scroll_offset: int=0, page_rows: int=20, total_lines: int=0) -> None:
        data=data or {}
        if presentation=='inventory_item_detail':
            return self._present_inventory_item_detail(title,lines=lines,footer=footer,breadcrumb=breadcrumb,data=data,scroll_offset=scroll_offset)
        if presentation=='crafting_materials':
            return self._present_crafting_materials(title,footer=footer,breadcrumb=breadcrumb,data=data,scroll_offset=scroll_offset)
        if presentation=='crafting_tree':
            return self._present_crafting_tree(title,footer=footer,breadcrumb=breadcrumb,data=data,scroll_offset=scroll_offset)
        return self.present_document(title,lines,footer=footer,breadcrumb=breadcrumb)

    def _present_npc_profile(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        """Compact movable NPC profile with contextual tabs instead of a data dump."""
        data=data or {};pg=self.pg;screen=self.screen
        summary=data.get('summary',{});tabs=data.get('tabs',{});active=str(data.get('active_tab','overview'))
        x,y,w,h,cx,cy,cw=self._floating_feature_shell(
            'npc_profile','PERSON',str(summary.get('name',title)),show_heading=False
        )
        footer_h=45;body_bottom=y+h-footer_h
        top_h=64;gap=10
        self._draw_npc_portrait(data.get('portrait'),pg.Rect(cx,cy,top_h,top_h))
        # Four small facts provide orientation without repeating every social field.
        facts=[
            ('Age',str(summary.get('age') if summary.get('age') is not None else 'Unknown')),
            ('Role',str(summary.get('occupation','Unknown'))),
            ('Settlement',str(summary.get('settlement','Unknown'))),
            ('Now',str(summary.get('activity','Idle'))),
        ]
        facts_x=cx+top_h+gap;facts_w=cw-top_h-gap
        fw=max(1,(facts_w-gap*3)//4)
        for i,(label,value) in enumerate(facts):
            rect=pg.Rect(facts_x+i*(fw+gap),cy,fw,top_h)
            pg.draw.rect(screen,self._theme['panel'],rect,border_radius=6)
            pg.draw.rect(screen,self._theme['edge'],rect,1,border_radius=6)
            ls=self.small_font.render(self._fit_ui_text(label.upper(),self.small_font,rect.width-18),True,self._theme['muted']);screen.blit(ls,(rect.x+9,rect.y+8))
            vs=self.small_font.render(self._fit_ui_text(value,self.small_font,rect.width-18),True,self._theme['text'])
            screen.blit(vs,(rect.x+9,rect.y+31))
        body_y=cy+top_h+12
        tab_w=max(132,min(172,cw//4));tab_panel=pg.Rect(cx,body_y,tab_w,max(120,body_bottom-body_y-5))
        content=pg.Rect(tab_panel.right+12,body_y,cw-tab_w-12,tab_panel.height)
        for panel in (tab_panel,content):
            pg.draw.rect(screen,self._theme['panel'],panel,border_radius=7)
            pg.draw.rect(screen,self._theme['edge'],panel,1,border_radius=7)

        tab_y=tab_panel.y+10
        for i,row in enumerate(rows):
            rect=pg.Rect(tab_panel.x+8,tab_y,tab_panel.width-16,34)
            self._ui_target(rect,f'UI_SELECT:{i}')
            key=str(getattr(row,'key',''))
            is_active=(key==active)
            hovered=rect.collidepoint(self._last_mouse)
            pg.draw.rect(screen,(45,51,49) if is_active or hovered else (27,32,33),rect,border_radius=5)
            pg.draw.rect(screen,self._theme['accent'] if is_active else self._theme['edge'],rect,2 if is_active else 1,border_radius=5)
            label=str(getattr(row,'label',key))
            surf=self.small_font.render(self._fit_ui_text(label,self.small_font,rect.width-18),True,self._theme['text'] if is_active else self._theme['muted'])
            screen.blit(surf,(rect.x+9,rect.centery-surf.get_height()//2))
            tab_y+=40

        heading=self.font.render(active.replace('_',' ').upper(),True,self._theme['accent'])
        screen.blit(heading,(content.x+14,content.y+12))
        yy=content.y+44
        entries=list(tabs.get(active,()))
        if active=='overview':
            # The identity cards already own these facts. Keep the underlying
            # profile rows intact for the terminal backend and other callers.
            repeated={'age','occupation','settlement','current activity'}
            entries=[row for row in entries if str(row[0]).strip().casefold() not in repeated]
        rendered_traits=False
        if active in {'needs','relations'}:
            for row in entries[:9]:
                if yy+38>content.bottom-10:break
                if len(row)<3:
                    label,value=row[0],row[1] if len(row)>1 else ''
                    card=pg.Rect(content.x+10,yy-4,content.width-20,34)
                    pg.draw.rect(screen,(27,32,33),card,border_radius=4)
                    ls=self.small_font.render(self._fit_ui_text(str(label),self.small_font,max(90,card.width//3)),True,self._theme['muted'])
                    screen.blit(ls,(card.x+9,card.centery-ls.get_height()//2))
                    value_x=card.x+max(104,card.width//3)
                    vs=self.small_font.render(self._fit_ui_text(str(value),self.small_font,card.right-value_x-9),True,self._theme['text'])
                    screen.blit(vs,(value_x,card.centery-vs.get_height()//2));yy+=39;continue
                label,status,value=row
                name=self.small_font.render(str(label),True,self._theme['text'])
                stat=self.small_font.render(str(status).upper(),True,self._theme['muted'])
                screen.blit(name,(content.x+14,yy))
                screen.blit(stat,(content.right-stat.get_width()-14,yy))
                gauge=pg.Rect(content.x+14,yy+20,content.width-28,7)
                pg.draw.rect(screen,(47,52,50),gauge,border_radius=3)
                fill=pg.Rect(gauge.x,gauge.y,round(gauge.width*max(0,min(100,int(value)))/100),gauge.height)
                if fill.width:
                    pg.draw.rect(screen,self._theme['accent'] if int(value)<60 else self._theme['danger'],fill,border_radius=3)
                yy+=40
        else:
            for row in entries[:10]:
                if yy+38>content.bottom-10:break
                label,value=row[0],row[1] if len(row)>1 else ''
                card=pg.Rect(content.x+10,yy-4,content.width-20,34)
                pg.draw.rect(screen,(27,32,33),card,border_radius=4)
                ls=self.small_font.render(self._fit_ui_text(str(label),self.small_font,max(90,card.width//3)),True,self._theme['muted'])
                screen.blit(ls,(card.x+9,card.centery-ls.get_height()//2))
                value_x=card.x+max(104,card.width//3)
                vs=self.small_font.render(self._fit_ui_text(str(value),self.small_font,card.right-value_x-9),True,self._theme['text'])
                screen.blit(vs,(value_x,card.centery-vs.get_height()//2))
                rendered_traits=rendered_traits or str(label).strip().casefold()=='traits'
                yy+=39

        traits=list(summary.get('traits') or [])
        if traits and active=='overview' and not rendered_traits and yy+24<content.bottom:
            txt='Traits: '+', '.join(traits[:4])
            surf=self.small_font.render(self._fit_ui_text(txt,self.small_font,content.width-28),True,self._theme['muted'])
            screen.blit(surf,(content.x+14,content.bottom-27))
        self._draw_floating_footer(x,y,w,h,'Tabs show known information • Drag title • Resize corner • Esc closes')
        pg.display.flip();self.clock.tick(120)

    @staticmethod
    def _dialogue_rich_lines(spans, font, max_width: int):
        """Reflow structured speech without losing its topic or paragraph breaks.

        Each fragment is measured with the font used to paint it. Unspaced
        names and linked phrases may split across rows, retaining their topic
        on every visible fragment rather than making a single oversized target.
        """
        max_width=max(1,int(max_width));lines=[];line=[];used=0

        def finish():
            nonlocal line,used
            while line and line[-1]['text'].isspace():line.pop()
            lines.append(line);line=[];used=0

        def append(text,topic):
            nonlocal used
            line.append({'text':text,'topic':topic});used+=font.size(text)[0]

        for span in spans:
            text=str(span.get('text','') if isinstance(span,dict) else getattr(span,'text',''))
            topic=str(span.get('topic','') if isinstance(span,dict) else getattr(span,'topic',''))
            for token in re.findall(r'\r\n|[\r\n]|[^\S\r\n]+|[^\s]+',text):
                if token in ('\n','\r','\r\n'):
                    finish();continue
                if token.isspace():
                    if line and used+font.size(token)[0]<=max_width:append(token,'')
                    continue
                width=font.size(token)[0]
                if width<=max_width:
                    if line and used+width>max_width:finish()
                    append(token,topic);continue
                # A long word uses the remaining row before continuing on the
                # next. It is never shortened or given an off-panel hit region.
                part=''
                for char in token:
                    if font.size(part+char)[0]>max_width-used:
                        if part:append(part,topic);part=''
                        if line:finish()
                    part+=char
                if part:append(part,topic)
        if line:finish()
        return lines or [[]]

    def _draw_dialogue_path(self, rect, data, breadcrumb=''):
        """Bounded path chips; retained parents remain reachable with Esc."""
        pg=self.pg;path=list(data.get('path') or [])
        if not path:
            path=[{'index':i,'label':r.get('label',r.get('topic','Topic'))} for i,r in enumerate(data.get('thread') or [])]
            path.append({'index':len(path),'label':data.get('topic_label') or data.get('topic','Conversation').replace('_',' ').title()})
        if len(path)==1 and breadcrumb:
            path=[{'index':0,'label':breadcrumb},path[0]]
        # Show the root and newest parents when a deep path exceeds one row.
        # Full parent text is retained on its route, never truncated in history.
        chip_limit=max(42,min(160,rect.width//3));gap=13
        def chip_width(item):return min(chip_limit,self.small_font.size(str(item.get('label','Topic')))[0]+16)
        shown=list(path)
        while len(shown)>2 and sum(chip_width(item)+gap for item in shown)-gap>rect.width:
            del shown[1]
        collapsed=len(shown)<len(path)
        xx=rect.x
        for i,item in enumerate(shown):
            remaining=rect.right-xx
            if remaining<24:break
            width=min(chip_width(item),remaining)
            chip=pg.Rect(xx,rect.y,width,rect.height)
            current=item is path[-1]
            hover=chip.collidepoint(self._last_mouse)
            pg.draw.rect(self.screen,(45,51,45) if hover and not current else self._theme['panel2'],chip,border_radius=4)
            color=self._theme['text'] if current else self._theme['accent']
            label=self._fit_ui_text(str(item.get('label','Topic')),self.small_font,width-12)
            self.screen.blit(self.small_font.render(label,True,color),(chip.x+6,chip.y+4))
            if not current:self._ui_target(chip,f"UI_ACTION:path:{int(item.get('index',i))}")
            xx=chip.right+gap
            if i<len(shown)-1:
                arrow='…' if collapsed and i==0 else '›'
                self.screen.blit(self.small_font.render(arrow,True,self._theme['muted']),(chip.right+3,chip.y+4))

    def _present_npc_dialogue(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        """Nested spoken thread with inline topics and keyboard-equivalent replies."""
        data=data or {};pg=self.pg;screen=self.screen
        # Context and navigation have their own compact rows; the shell need
        # not repeat the longer instruction above every spoken paragraph.
        x,y,w,h,cx,cy,cw=self._floating_feature_shell(
            'npc_dialogue','CONVERSATION',str(data.get('speaker',title)),show_heading=False
        )
        self._button((x+w-130,y+7,82,27),'INSPECT','UI_ACTION:inspect')
        identity_h=64
        self._draw_npc_portrait(data.get('portrait'),pg.Rect(cx,cy,identity_h,identity_h))
        identity_x=cx+identity_h+12;identity_w=max(1,cw-identity_h-12)
        role=str(data.get('role','')).upper()
        context='  ·  '.join(str(v) for v in data.get('context',()) if str(v).casefold()!=role.casefold())
        role_w=identity_w
        if data.get('time_paused'):
            status=self.small_font.render('TIME PAUSED',True,self._theme['good'])
            screen.blit(status,(cx+cw-status.get_width(),cy+5))
            role_w=max(1,identity_w-status.get_width()-18)
        screen.blit(self.small_font.render(self._fit_ui_text(role or 'PERSON',self.small_font,role_w),True,self._theme['text']),(identity_x,cy+5))
        screen.blit(self.small_font.render(self._fit_ui_text(context,self.small_font,identity_w),True,self._theme['muted']),(identity_x,cy+25))
        relationship=data.get('relationship') or {}
        relationship_text='  ·  '.join(f'{str(k).title()} {int(v):+d}' for k,v in relationship.items())
        screen.blit(self.small_font.render(self._fit_ui_text(relationship_text,self.small_font,identity_w),True,self._theme['muted']),(identity_x,cy+45))
        self._draw_dialogue_path(pg.Rect(cx,cy+identity_h+6,cw,24),data,breadcrumb)
        body_y=cy+identity_h+36;body_bottom=y+h-46;gap=12
        rail_w=max(176,min(270,int(cw*.32)))
        if cw<500:rail_w=max(132,int(cw*.36))
        transcript=pg.Rect(cx,body_y,max(1,cw-rail_w-gap),max(1,body_bottom-body_y))
        choices=pg.Rect(transcript.right+gap,body_y,rail_w,transcript.height)
        for panel in (transcript,choices):
            pg.draw.rect(screen,self._theme['panel'],panel,border_radius=7);pg.draw.rect(screen,self._theme['edge'],panel,1,border_radius=7)

        # Ancestors are quiet nested excerpts. Their full speech stays on the
        # parent route; returning restores the exact text page and selection.
        yy=transcript.y+12;thread=list(data.get('thread') or [])
        max_parents=min(2,max(0,(transcript.height-190)//39))
        for depth,parent in enumerate(thread[-max_parents:] if max_parents else []):
            inset=10+depth*8;xx=transcript.x+inset
            pg.draw.line(screen,self._theme['edge_hi'],(xx,yy),(xx,yy+31),2)
            label=str(parent.get('label','Earlier topic'))
            excerpt=str(parent.get('text','')).replace('\n',' ')
            screen.blit(self.small_font.render(self._fit_ui_text(label,self.small_font,transcript.width-inset-22),True,self._theme['accent']),(xx+9,yy))
            screen.blit(self.small_font.render(self._fit_ui_text(excerpt,self.small_font,transcript.width-inset-22),True,self._theme['muted']),(xx+9,yy+17))
            yy+=39
        label=str(data.get('topic_label') or data.get('topic','Conversation').replace('_',' ').title())
        indent=min(20,len(thread)*5)
        text_x=transcript.x+14+indent;text_w=max(1,transcript.right-text_x-14)
        screen.blit(self.small_font.render(self._fit_ui_text(label.upper(),self.small_font,text_w),True,self._theme['accent']),(text_x,yy));yy+=26
        spans=list(data.get('spans') or [])
        if spans:
            if data.get('response'):spans=spans+[{'text':'\n\n'+str(data['response']),'topic':''}]
        else:spans=[{'text':str(data.get('response') or data.get('opening') or '...'),'topic':''}]
        lines=self._dialogue_rich_lines(spans,self.font,text_w)
        line_h=self.font.get_linesize()+5
        text_rect=pg.Rect(text_x,yy,text_w,max(1,transcript.bottom-43-yy))
        capacity=max(1,text_rect.height//line_h)
        pages=max(1,(len(lines)+capacity-1)//capacity)
        page=min(pages-1,max(0,int(data.get('transcript_page',0))))
        focused_topic=str(data.get('focused_topic') or '')
        if focused_topic and focused_topic!=data.get('_rendered_focused_topic'):
            for index,line in enumerate(lines):
                if any(fragment['topic']==focused_topic for fragment in line):
                    page=index//capacity;break
        data['_rendered_focused_topic']=focused_topic
        data['transcript_page']=page;data['transcript_pages']=pages
        self._dialogue_text_rect=text_rect;self._dialogue_page_count=pages
        self._dialogue_visible_page=page;self._dialogue_visible_lines=lines[page*capacity:(page+1)*capacity]
        old_clip=screen.get_clip();screen.set_clip(text_rect.clip(old_clip))
        for line in self._dialogue_visible_lines:
            xx=text_x
            for fragment in line:
                text=fragment['text'];topic=fragment['topic'];width=self.font.size(text)[0]
                box=pg.Rect(xx,yy,width,self.font.get_height()).clip(text_rect).clip(old_clip)
                linked=bool(topic and text.strip());hover=linked and box.collidepoint(self._last_mouse)
                focused=linked and topic==focused_topic
                if hover or focused:pg.draw.rect(screen,(58,62,45),box,border_radius=3)
                if focused:pg.draw.rect(screen,self._theme['accent'],box,1,border_radius=3)
                color=(235,204,134) if hover or focused else self._theme['accent'] if linked else self._theme['text']
                screen.blit(self.font.render(text,True,color),(xx,yy))
                if linked and box.width>0 and box.height>0:
                    pg.draw.line(screen,color,(box.x,box.bottom-2),(box.right-1,box.bottom-2),1)
                    self._ui_target(box,f'UI_ACTION:topic:{topic}')
                xx+=width
            yy+=line_h
        screen.set_clip(old_clip)
        if pages>1:
            bw=min(72,max(32,(transcript.width-92)//2))
            if page>0:self._button((transcript.x+10,transcript.bottom-34,bw,25),'Previous','UI_ACTION:transcript_previous')
            if page<pages-1:self._button((transcript.right-bw-10,transcript.bottom-34,bw,25),'Next','UI_ACTION:transcript_next')
            count=self.small_font.render(f'{page+1}/{pages}',True,self._theme['muted']);screen.blit(count,(transcript.centerx-count.get_width()//2,transcript.bottom-29))

        heading=self.small_font.render('TOPICS & REPLIES',True,self._theme['accent']);screen.blit(heading,(choices.x+10,choices.y+12))
        yy=choices.y+40
        actions={'gift':'+','trade':'$','attack':'!','inspect':'i','goodbye':'×','introduce':'+','back':'‹'}
        for i,row in enumerate(rows):
            if yy+34>choices.bottom-44:break
            key=str(getattr(row,'key',''));label=str(getattr(row,'label',row))
            rect=pg.Rect(choices.x+8,yy,choices.width-16,34);self._ui_target(rect,f'UI_SELECT:{i}')
            active=i==selected;hover=rect.collidepoint(self._last_mouse)
            pg.draw.rect(screen,(45,51,49) if active or hover else self._theme['panel2'],rect,border_radius=5)
            edge=self._theme['danger'] if key=='attack' else self._theme['accent'] if active else self._theme['edge']
            pg.draw.rect(screen,edge,rect,2 if active else 1,border_radius=5)
            badge=actions.get(key,'›');badge_color=self._theme['danger'] if key=='attack' else self._theme['muted'] if key in actions else self._theme['accent']
            screen.blit(self.small_font.render(badge,True,badge_color),(rect.x+8,rect.y+8))
            surf=self.small_font.render(self._fit_ui_text(label,self.small_font,rect.width-32),True,self._theme['text'])
            screen.blit(surf,(rect.x+24,rect.centery-surf.get_height()//2));yy+=38
        if total is not None and total>len(rows):
            bw=min(72,max(32,(choices.width-70)//2))
            self._button((choices.x+8,choices.bottom-34,bw,25),'Previous','PGUP')
            self._button((choices.right-bw-8,choices.bottom-34,bw,25),'Next','PGDN')
            count=self.small_font.render(f'{page_start+1}-{page_start+len(rows)}/{total}',True,self._theme['muted']);screen.blit(count,(choices.centerx-count.get_width()//2,choices.bottom-29))
        self._draw_floating_footer(x,y,w,h,'Click / Tab words • Enter opens • Arrows choose replies • Esc returns one topic')
        pg.display.flip();self.clock.tick(120)

    def _present_container_inventory(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        """Dual-pane visual storage transfer UI."""
        data=data or {};pg=self.pg;screen=self.screen
        entries=data.get('entries',{});container=data.get('container',{})
        x,y,w,h,cx,cy,cw=self._floating_feature_shell('container_inventory','STORAGE',str(container.get('name','CONTAINER')).upper(),subtitle)
        head_h=58;gap=10
        mass=float(container.get('mass_kg',0));mass_cap=max(.001,float(container.get('capacity_mass_kg',0) or .001))
        vol=float(container.get('volume_l',0));vol_cap=max(.001,float(container.get('capacity_volume_l',0) or .001))
        mw=(cw-gap*3)//4
        self._draw_metric(pg.Rect(cx,cy,mw,head_h),'Container mass',f'{mass:.1f}/{mass_cap:.1f} kg')
        self._draw_metric(pg.Rect(cx+(mw+gap),cy,mw,head_h),'Container volume',f'{vol:.1f}/{vol_cap:.1f} L')
        self._storage_gauge(pg.Rect(cx+10,cy+head_h-5,mw-20,4),mass,mass_cap)
        self._storage_gauge(pg.Rect(cx+mw+gap+10,cy+head_h-5,mw-20,4),vol,vol_cap)
        self._draw_metric(pg.Rect(cx+2*(mw+gap),cy,mw,head_h),'Stacks',str(container.get('stack_count',0)))
        kind=str(container.get('kind','built')).replace('_',' ').title()
        self._draw_metric(pg.Rect(cx+3*(mw+gap),cy,mw,head_h),'Type',kind)

        body_y=cy+head_h+10;body_bottom=y+h-48;body_h=max(180,body_bottom-body_y)
        detail_w=max(220,min(320,cw//4))
        grids_w=cw-detail_w-20;left_w=(grids_w-gap)//2
        pack_rect=pg.Rect(cx,body_y,left_w,body_h)
        cont_rect=pg.Rect(pack_rect.right+gap,body_y,grids_w-left_w-gap,body_h)
        detail=pg.Rect(cont_rect.right+gap,body_y,detail_w,body_h)
        for rr in (pack_rect,cont_rect,detail):
            pg.draw.rect(screen,self._theme['panel'],rr,border_radius=7)
            pg.draw.rect(screen,self._theme['edge'],rr,1,border_radius=7)

        def pane_title(rect,label,detail_text=''):
            t=self.font.render(label,True,self._theme['accent']);screen.blit(t,(rect.x+12,rect.y+10))
            if detail_text:
                s=self.small_font.render(self._fit_ui_text(detail_text,self.small_font,rect.width-24),True,self._theme['muted']);screen.blit(s,(rect.x+12,rect.y+32))
        pane_title(pack_rect,'BACKPACK',f"{data.get('pack',{}).get('item_count',0)} items")
        pane_title(cont_rect,'CONTAINER',f"{container.get('item_count',0)} items")

        side_rows={'pack':[],'container':[]}
        for i,row in enumerate(rows):
            key=getattr(row,'key','');meta=entries.get(key)
            if meta:side_rows.get(meta.get('side','pack'),side_rows['pack']).append((i,row,meta))

        def draw_side(rect,side):
            rows_here=side_rows[side]
            top=rect.y+58;cols=2;cg=7;cw_card=max(78,(rect.width-24-cg)//2);ch=98
            for local,(global_i,row,meta) in enumerate(rows_here):
                gx=local%cols;gy=local//cols
                card=pg.Rect(rect.x+12+gx*(cw_card+cg),top+gy*(ch+cg),cw_card,ch)
                if card.bottom>rect.bottom-12:break
                self._ui_target(card,f'UI_SELECT:{global_i}')
                active=(global_i==selected)
                hovered=card.collidepoint(self._last_mouse)
                pg.draw.rect(screen,(48,54,48) if active or hovered else (29,36,35),card,border_radius=6)
                pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],card,2 if active else 1,border_radius=6)
                pg.draw.rect(screen,(22,28,28),(card.x+6,card.y+5,card.width-12,48),border_radius=4)
                iid=str(meta.get('iid',''));icon=pg.Rect(card.x+6,card.y+5,card.width-12,48)
                self._draw_item_icon(iid,icon,scale=.88)
                nm=self.small_font.render(self._fit_ui_text(str(meta.get('name',iid)),self.small_font,card.width-12),True,self._theme['text']);screen.blit(nm,(card.x+6,card.y+57))
                q=self.small_font.render(f"x{meta.get('count',0)}",True,self._theme['accent']);screen.blit(q,(card.x+6,card.bottom-18))
            if not rows_here:
                msg=self.small_font.render('Empty',True,self._theme['muted']);screen.blit(msg,msg.get_rect(center=(rect.centerx,rect.y+96)))
        draw_side(pack_rect,'pack');draw_side(cont_rect,'container')

        selected_meta={}
        if rows:
            key=data.get('selected_key') or (getattr(rows[selected],'key','') if 0<=selected<len(rows) else '')
            selected_meta=entries.get(key,{})
        action_amount=max(1,int(data.get('action_amount',1)))
        yy=detail.y+12
        if selected_meta:
            iid=str(selected_meta.get('iid',''))
            icon=pg.Rect(detail.x+14,yy,detail.width-28,82);self._draw_item_icon(iid,icon,scale=.78);yy=icon.bottom+5
            name=self.font.render(self._fit_ui_text(str(selected_meta.get('name',iid)),self.font,detail.width-28),True,self._theme['accent']);screen.blit(name,(detail.x+14,yy));yy+=22
            side=str(selected_meta.get('side','pack'))
            src='BACKPACK' if side=='pack' else 'CONTAINER'
            srcs=self.small_font.render(src,True,self._theme['muted']);screen.blit(srcs,(detail.x+14,yy));yy+=19
            stat=self.small_font.render(f"x{selected_meta.get('count',0)} • {selected_meta.get('unit_mass_kg',0):.2f} kg ea",True,self._theme['text']);screen.blit(stat,(detail.x+14,yy));yy+=20
            for line in self._wrap_pixel_text(str(selected_meta.get('description','')),self.small_font,detail.width-28)[:2]:
                s=self.small_font.render(line,True,self._theme['muted']);screen.blit(s,(detail.x+14,yy));yy+=16
        else:
            msg=self.small_font.render('Select an item',True,self._theme['muted']);screen.blit(msg,(detail.x+14,yy));yy+=22

        controls_y=max(yy+8,detail.bottom-170)
        if selected_meta:
            count=max(1,int(selected_meta.get('count',1)));action_amount=min(action_amount,count)
            lab=self.small_font.render(f'AMOUNT {action_amount}/{count}',True,self._theme['text']);screen.blit(lab,(detail.x+14,controls_y+5))
            bx=detail.right-14-104
            self._button((bx,controls_y,30,27),'−','UI_ACTION:qty_down')
            self._button((bx+36,controls_y,30,27),'+','UI_ACTION:qty_up')
            self._button((bx+72,controls_y,32,27),'ALL','UI_ACTION:qty_all')
            controls_y+=34
            direction='Store →' if selected_meta.get('side')=='pack' else '← Take'
            self._button((detail.x+14,controls_y,detail.width-28,32),direction+' [T]','UI_ACTION:transfer')
            controls_y+=38
            self._button((detail.x+14,controls_y,detail.width-28,28),'Half stack [H]','UI_ACTION:split')
            controls_y+=34

        if container.get('movable'):
            move_y=min(controls_y,detail.bottom-(62 if container.get('kind')=='natural' else 32))
            bw=max(34,(detail.width-35)//4);bh=27;bx=detail.x+14
            for n,(label,token) in enumerate((
                ('←','UI_ACTION:move:-1:0'),('↑','UI_ACTION:move:0:-1'),
                ('↓','UI_ACTION:move:0:1'),('→','UI_ACTION:move:1:0'),
            )):
                self._button((bx+n*(bw+3),move_y,bw,bh),label,token)
        if container.get('kind')=='natural':
            self._button((detail.x+14,detail.bottom-34,detail.width-28,25),'Break apart [X]','UI_ACTION:destroy')

        if total is not None and total>len(rows):
            p=self.small_font.render(f'{page_start+1}-{min(total,page_start+len(rows))} / {total}',True,self._theme['muted']);screen.blit(p,(cont_rect.right-p.get_width()-10,cont_rect.bottom-20))
        self._draw_item_context_popup(rows,data,selected)
        self._draw_floating_footer(x,y,w,h,'Shift-click transfers full stack • Right-click actions • Drag title • Resize corner • Esc closes')
        pg.display.flip();self.clock.tick(120)

    def _present_inventory_home(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};pg=self.pg;screen=self.screen
        x,y,w,h,cx,cy,cw=self._feature_shell('INVENTORY','INVENTORY // PACK',subtitle)
        # left character/pack summary
        left_w=max(250,min(330,cw//3));left=pg.Rect(cx,cy,left_w,h-(cy-y)-48);right=pg.Rect(left.right+16,cy,cw-left_w-16,left.height)
        pg.draw.rect(screen,self._theme['panel'],left,border_radius=7);pg.draw.rect(screen,self._theme['edge'],left,1,border_radius=7)
        name=self.title_font.render(str(data.get('player_name','Wanderer')),True,self._theme['accent']);screen.blit(name,(left.x+16,left.y+14))
        sex=str(data.get('player_sex','male'));idx=int(data.get('player_sprite_index',0));path=self._visuals.player_path(sex,idx)
        preview=pg.Rect(left.x+18,left.y+54,left.width-36,min(190,left.height//3))
        pg.draw.rect(screen,(17,20,21),preview,border_radius=5);pg.draw.rect(screen,self._theme['edge'],preview,1,border_radius=5)
        sprite=self._load_sprite(path,preview.width-20,preview.height-16)
        if sprite:screen.blit(sprite,(preview.centerx-sprite.get_width()//2,preview.bottom-sprite.get_height()-8))
        metrics_y=preview.bottom+14;gap=8;mw=(left.width-40-gap)//2
        self._draw_metric(pg.Rect(left.x+16,metrics_y,mw,58),'Mass',f"{data.get('total_mass_kg',0):.1f} kg")
        self._draw_metric(pg.Rect(left.x+24+mw,metrics_y,mw,58),'Volume',f"{data.get('total_volume_l',0):.1f} L")
        metrics_y+=66
        self._draw_metric(pg.Rect(left.x+16,metrics_y,mw,58),'Stacks',str(data.get('stack_count',0)))
        self._draw_metric(pg.Rect(left.x+24+mw,metrics_y,mw,58),'Items',str(data.get('item_count',0)))
        yy=metrics_y+76
        lab=self.small_font.render('PACK CONTENTS',True,self._theme['muted']);screen.blit(lab,(left.x+16,yy));yy+=22
        cats=sorted((data.get('categories') or {}).items(),key=lambda kv:(-kv[1],kv[0]))[:5]
        maxv=max([v for _,v in cats] or [1])
        for cat,count in cats:
            txt=self.small_font.render(self._fit_ui_text(cat.replace('_',' ').title(),self.small_font,left.width-92),True,self._theme['text']);screen.blit(txt,(left.x+16,yy))
            c=self.small_font.render(str(count),True,self._theme['accent']);screen.blit(c,(left.right-c.get_width()-16,yy))
            bar=pg.Rect(left.x+16,yy+16,left.width-32,4);pg.draw.rect(screen,(43,47,46),bar,border_radius=2);pg.draw.rect(screen,self._theme['accent'],(bar.x,bar.y,int(bar.width*count/maxv),bar.height),border_radius=2);yy+=28
        # navigation cards
        pg.draw.rect(screen,self._theme['panel'],right,border_radius=7);pg.draw.rect(screen,self._theme['edge'],right,1,border_radius=7)
        head=self.small_font.render('INVENTORY SECTIONS',True,self._theme['muted']);screen.blit(head,(right.x+16,right.y+14))
        ry=right.y+42;available=right.bottom-ry-14;rh=max(54,min(72,(available-8*(len(rows)-1))//max(1,len(rows))))
        details=['Weight, volume and durable item summary','Grid view with item icons and stack details','Move goods to and from an adjacent container','Armor, worn gear, anatomy and wounds','Open readable books carried in your pack']
        for i,row in enumerate(rows):
            rect=pg.Rect(right.x+14,ry+i*(rh+8),right.width-28,rh);self._draw_menu_card(rect,getattr(row,'label',str(row)),i==selected,detail=details[i] if i<len(details) else '',badge=str(i+1))
        self._draw_feature_footer(x,y,w,h,footer);self._draw_scanlines((x,y,w,h));pg.display.flip();self.clock.tick(120)

    def _present_inventory_items(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};pg=self.pg;screen=self.screen;items=data.get('items',{})
        x,y,w,h,cx,cy,cw=self._feature_shell('INVENTORY','INVENTORY // ITEMS',subtitle)
        preview_w=max(280,min(360,cw//3));grid=pg.Rect(cx,cy,cw-preview_w-16,h-(cy-y)-48);detail=pg.Rect(grid.right+16,cy,preview_w,grid.height)
        pg.draw.rect(screen,self._theme['panel'],grid,border_radius=7);pg.draw.rect(screen,self._theme['edge'],grid,1,border_radius=7)
        pg.draw.rect(screen,self._theme['panel'],detail,border_radius=7);pg.draw.rect(screen,self._theme['edge'],detail,1,border_radius=7)
        cols=4 if grid.width>=560 else 3;gap=9;card_w=max(96,(grid.width-28-gap*(cols-1))//cols);card_h=118
        for i,row in enumerate(rows):
            gx=i%cols;gy=i//cols;rect=pg.Rect(grid.x+14+gx*(card_w+gap),grid.y+14+gy*(card_h+gap),card_w,card_h)
            if rect.bottom>grid.bottom-12:break
            self._ui_target(rect,f'UI_SELECT:{i}')
            active=i==selected;iid=getattr(row,'key','');meta=items.get(iid,{})
            pg.draw.rect(screen,(39,42,40) if active else self._theme['panel2'],rect,border_radius=6);pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,2 if active else 1,border_radius=6)
            icon=pg.Rect(rect.x+8,rect.y+8,rect.width-16,60);self._draw_item_icon(iid,icon)
            name=self.small_font.render(self._fit_ui_text(meta.get('name',iid),self.small_font,rect.width-16),True,self._theme['text']);screen.blit(name,(rect.x+8,rect.y+72))
            qty=self.small_font.render(f"x{meta.get('count',0)}",True,self._theme['accent']);screen.blit(qty,(rect.x+8,rect.bottom-20))
            mass=self.small_font.render(f"{meta.get('mass_kg',0):.1f}kg",True,self._theme['muted']);screen.blit(mass,(rect.right-mass.get_width()-8,rect.bottom-20))
        if rows:
            row=rows[max(0,min(selected,len(rows)-1))];iid=getattr(row,'key','');meta=items.get(iid,{})
            icon=pg.Rect(detail.x+24,detail.y+18,detail.width-48,150);pg.draw.rect(screen,(17,20,21),icon,border_radius=6);self._draw_item_icon(iid,icon,scale=.82)
            yy=icon.bottom+14
            name=self.title_font.render(self._fit_ui_text(meta.get('name',iid),self.title_font,detail.width-32),True,self._theme['accent']);screen.blit(name,(detail.x+16,yy));yy+=30
            cat=self.small_font.render(str(meta.get('category','misc')).replace('_',' ').upper(),True,self._theme['muted']);screen.blit(cat,(detail.x+16,yy));yy+=24
            stats=[('Stack',str(meta.get('count',0))),('Mass',f"{meta.get('mass_kg',0):.2f} kg"),('Volume',f"{meta.get('volume_l',0):.2f} L")]
            for lab,val in stats:
                ls=self.small_font.render(lab,True,self._theme['muted']);vs=self.small_font.render(val,True,self._theme['text']);screen.blit(ls,(detail.x+16,yy));screen.blit(vs,(detail.right-vs.get_width()-16,yy));yy+=21
            desc=str(meta.get('description','')).strip()
            if desc:
                for line in self._wrap_pixel_text(desc,self.small_font,detail.width-32)[:5]:
                    surf=self.small_font.render(line,True,self._theme['text']);screen.blit(surf,(detail.x+16,yy));yy+=18
        if total is not None:
            p=self.small_font.render(f'{page_start+1}-{min(total,page_start+len(rows))} / {total}',True,self._theme['muted']);screen.blit(p,(grid.right-p.get_width()-12,grid.bottom-24))
        self._draw_feature_footer(x,y,w,h,footer);self._draw_scanlines((x,y,w,h));pg.display.flip();self.clock.tick(120)

    def _present_inventory_item_actions(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};iid=data.get('item_id','');meta=(data.get('items') or {}).get(iid,{})
        pg=self.pg;screen=self.screen;x,y,w,h,cx,cy,cw=self._feature_shell('INVENTORY',str(meta.get('name','ITEM')).upper(),subtitle)
        left=pg.Rect(cx,cy,max(280,cw//2-8),h-(cy-y)-48);right=pg.Rect(left.right+16,cy,cw-left.width-16,left.height)
        for r in (left,right):pg.draw.rect(screen,self._theme['panel'],r,border_radius=7);pg.draw.rect(screen,self._theme['edge'],r,1,border_radius=7)
        icon=pg.Rect(left.x+24,left.y+18,left.width-48,min(220,left.height//2));pg.draw.rect(screen,(17,20,21),icon,border_radius=6);self._draw_item_icon(iid,icon,scale=.8)
        yy=icon.bottom+16
        for lab,val in [('Carried',str(meta.get('count',0))),('Total mass',f"{meta.get('mass_kg',0):.2f} kg"),('Total volume',f"{meta.get('volume_l',0):.2f} L")]:
            ls=self.small_font.render(lab,True,self._theme['muted']);vs=self.small_font.render(val,True,self._theme['text']);screen.blit(ls,(left.x+18,yy));screen.blit(vs,(left.right-vs.get_width()-18,yy));yy+=22
        desc=str(meta.get('description',''))
        for line in self._wrap_pixel_text(desc,self.small_font,left.width-36)[:4]:
            s=self.small_font.render(line,True,self._theme['muted']);screen.blit(s,(left.x+18,yy));yy+=18
        ry=right.y+18;rh=62
        for i,row in enumerate(rows):
            self._draw_menu_card(pg.Rect(right.x+14,ry+i*(rh+9),right.width-28,rh),getattr(row,'label',str(row)),i==selected,badge=str(i+1))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def menu_page_size(self,presentation:str='')->int:
        """Expose actual rendered row capacity to the shared paging widget."""
        if presentation=='inventory_unified':return self._inventory_browser_geometry()['capacity']
        if presentation=='crafting_unified':return self._crafting_browser_geometry()['capacity']
        if presentation=='discovery_pot':return self._discovery_browser_geometry()['capacity']
        if presentation=='workshop_station':return self._workshop_browser_geometry()['capacity']
        if presentation=='salvaging_unified':return self._salvage_browser_geometry()['capacity']
        if presentation not in {'workshop_station','salvaging'}:
            return super().menu_page_size(presentation)
        panel=self._floating_panel_state('crafting');height=panel['h']
        heading=self.title_font.get_height()+5
        if presentation=='crafting_unified':
            # Reserve the taller paged category strip even on its final page.
            return max(1,(height-48-52-heading-19-38-66-38-12)//72)
        if presentation=='salvaging':return max(1,(height-52-38-30-48-26)//55)
        if presentation=='workshop_station':return max(1,(height-48-52-heading-19-38-44-65)//67)
        return 1

    def _present_salvaging(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        """The workbench's salvage tab; every action is a UI token only."""
        data=data or {};mode=data.get('mode','catalogue');pg=self.pg;screen=self.screen
        x,y,w,h,cx,cy,cw=self._floating_feature_shell('crafting','WORKBENCH',title,show_heading=False)
        if mode=='catalogue':
            self._crafting_tabs(cx,cy,cw,'salvaging')
            self._button((cx+cw-100,cy,100,30),'SEARCH','UI_ACTION:search')
            cy+=38
        else:
            self._button((cx,cy,88,28),'‹ BACK','ESC')
            path=self._fit_ui_text(breadcrumb,self.small_font,cw-106)
            screen.blit(self.small_font.render(path,True,self._theme['muted']),(cx+100,cy+6));cy+=38
        status=(f"SALVAGING  Lv {data.get('skill_level',0)}  ·  XP {data.get('skill_xp',0)}"+(f"/{data['skill_threshold']}" if data.get('skill_threshold') else '') if mode!='session'
                else ('INSPECT ASSEMBLY' if data.get('phase')=='inspection' else f"DISASSEMBLY  {int(data.get('step',0))+1}/{data.get('stage_count',3)}  ·  Score {data.get('score',0)}"))
        screen.blit(self.small_font.render(status,True,self._theme['accent']),(cx,cy));cy+=30
        gap=12;left_w=int(cw*.47);bottom=y+h-48
        left=pg.Rect(cx,cy,left_w,max(1,bottom-cy));right=pg.Rect(left.right+gap,cy,cw-left_w-gap,left.height)
        for rect in (left,right):
            pg.draw.rect(screen,self._theme['panel'],rect,border_radius=6)
            pg.draw.rect(screen,self._theme['edge'],rect,1,border_radius=6)
        items=data.get('items',{});choices={row['id']:row for row in data.get('choices',())}
        row_y=left.y+12;row_h=49 if mode=='catalogue' else min(72,max(43,(left.height-24)//max(1,len(rows))-6))
        for index,row in enumerate(rows):
            rect=pg.Rect(left.x+10,row_y,left.width-20,row_h)
            if rect.bottom>left.bottom-10:break
            key=getattr(row,'key','');label=getattr(row,'label',str(row));active=index==selected
            pg.draw.rect(screen,(44,49,43) if active else self._theme['panel2'],rect,border_radius=5)
            pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,2 if active else 1,border_radius=5)
            text_x=rect.x+10
            if key in items:
                self._draw_item_icon(key,pg.Rect(rect.x+5,rect.y+5,39,39),scale=.9);text_x=rect.x+49
            screen.blit(self.small_font.render(self._fit_ui_text(label,self.small_font,rect.right-text_x-8),True,self._theme['text']),(text_x,rect.y+10))
            if mode=='session' and row_h>=62:
                detail=choices.get(key,{}).get('description','')
                screen.blit(self.small_font.render(self._fit_ui_text(detail,self.small_font,rect.width-20),True,self._theme['muted']),(rect.x+10,rect.y+35))
            self._ui_target(rect,f'UI_SELECT:{index}');row_y+=row_h+6
        if (total or len(rows))>len(rows):
            label=f'{page_start+1}–{page_start+len(rows)} / {total}  ·  Wheel / PgUp PgDn'
            screen.blit(self.small_font.render(self._fit_ui_text(label,self.small_font,left.width-20),True,self._theme['muted']),(left.x+10,left.bottom-22))
        text_y=right.y+14
        def write(value,color=None):
            nonlocal text_y
            for line in self._wrap_pixel_text(str(value),self.small_font,right.width-28):
                if text_y+18>right.bottom-12:return
                screen.blit(self.small_font.render(line,True,color or self._theme['text']),(right.x+14,text_y));text_y+=18
        def part(component,label,color):
            nonlocal text_y
            if text_y+30>right.bottom-12:return
            self._draw_item_icon(component['item_id'],pg.Rect(right.x+12,text_y,28,28))
            lines=self._wrap_pixel_text(label,self.small_font,right.width-58)
            for index,line in enumerate(lines):
                if text_y+index*18+18>right.bottom-12:break
                screen.blit(self.small_font.render(line,True,color),(right.x+48,text_y+index*18+4))
            text_y+=max(32,18*len(lines)+6)
        if mode=='catalogue':
            key=getattr(rows[max(0,min(selected,len(rows)-1))],'key','') if rows else ''
            item=items.get(key,{})
            if item:
                self._draw_item_icon(key,pg.Rect(right.x+14,text_y,58,58));text_y+=66
                write(item.get('name',''),self._theme['accent'])
                write(f"Carried: {item.get('count',0)}")
                write(item.get('reason') or 'Select to preview guaranteed parts, rare odds and learned crafting uses.',self._theme['muted'])
            else:write('Recover usable crafting parts from world finds, workshop offcuts, wild plants and butchered remains.')
            text_y+=12;write('Begin dismantles ONE item. Inspect its material cues, then choose a method at each of three stages.',self._theme['muted'])
            write('Escape keeps unfinished work. Use Resume to continue.',self._theme['muted'])
            if data.get('query'):write('Search: '+data['query'],self._theme['accent'])
        elif mode=='preview':
            write(data.get('name',''),self._theme['accent'])
            write(f"{str(data.get('method','')).replace('_',' ').title()} · {data.get('minutes',0)} min · Held {data.get('count',0)}",self._theme['muted'])
            text_y+=6
            for group in ('guaranteed','rare'):
                for component in data.get(group,()):
                    lo,hi=component.get('min',1),component.get('max',1);quantity=str(lo) if lo==hi else f'{lo}–{hi}'
                    chance=f" {component.get('chance_percent',0)}% base rare" if group=='rare' else ' guaranteed'
                    part(component,f"{component['name']} x{quantity} ·{chance}",self._theme['accent'] if group=='rare' else self._theme['good'])
                    uses=component.get('uses',())
                    if uses:write('Uses: '+', '.join(uses[:2]),self._theme['muted'])
            text_y+=6;write('Inspect shows the full component list and crafting uses.',self._theme['muted'])
            if data.get('reason'):write(data['reason'],self._theme['danger'])
        elif mode=='session':
            write(data.get('name',''),self._theme['accent']);text_y+=12
            if data.get('phase')!='inspection':
                for index in range(3):
                    bar=pg.Rect(right.x+14+index*(right.width-28)//3,text_y,(right.width-34)//3,9)
                    pg.draw.rect(screen,self._theme['good'] if index<int(data.get('step',0)) else (self._theme['accent'] if index==int(data.get('step',0)) else self._theme['edge']),bar,border_radius=3)
                text_y+=25
            write('MATERIAL CUE',self._theme['muted']);write(data.get('cue',''),self._theme['accent']);text_y+=12
            write(data.get('prompt',''));text_y+=12
            write('Choose a method using the cue. Careful recovery improves yield and rare-part odds.',self._theme['muted'])
        else:
            write('RECOVERED COMPONENTS',self._theme['accent'])
            for component in data.get('recovered',()):
                part(component,f"{component['name']} x{component['count']}"+(' · RARE' if component['rare'] else ''),self._theme['accent'] if component['rare'] else self._theme['good'])
            text_y+=12;write(f"Recovery {data.get('score',0)}/{data.get('max_score',6)}")
            write(f"Salvaging XP +{data.get('xp_gained',0)}")
            write('Parts enter your pack and can reveal further crafting techniques.',self._theme['muted'])
        self._draw_floating_footer(x,y,w,h,'Select with arrows / Enter or click • Wheel pages • Esc returns one level')
        self._draw_crafting_tab_tooltip();pg.display.flip();self.clock.tick(120)



    def _present_crafting_index(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};pg=self.pg;screen=self.screen
        x,y,w,h,cx,cy,cw=self._floating_feature_shell('crafting','WORKBENCH','ITEM DISCOVERIES',subtitle)
        self._button((x+w-128,y+7,78,27),'PACK','UI_ACTION:open_inventory')
        self._crafting_tabs(cx,cy,cw,'index');cy+=40
        panel=pg.Rect(cx,cy,cw,y+h-48-cy)
        pg.draw.rect(screen,self._theme['panel'],panel,border_radius=6)
        pg.draw.rect(screen,self._theme['edge'],panel,1,border_radius=6)
        name=str(data.get('item_name','Material'))
        heading=self.title_font.render(self._fit_ui_text(name,self.title_font,panel.width-28),True,self._theme['accent'])
        screen.blit(heading,(panel.x+14,panel.y+13))
        summary=self.small_font.render(f"{data.get('known',0)} discovered / {total or len(rows)} catalog recipes",True,self._theme['muted'])
        screen.blit(summary,(panel.x+14,panel.y+45))
        for i,row in enumerate(rows):
            rr=pg.Rect(panel.x+14,panel.y+75+i*40,panel.width-28,34)
            if rr.bottom>panel.bottom-14:break
            pg.draw.rect(screen,(46,49,40) if i==selected else self._theme['panel2'],rr,border_radius=5)
            pg.draw.rect(screen,self._theme['accent'] if i==selected else self._theme['edge'],rr,1,border_radius=5)
            label=self.small_font.render(self._fit_ui_text(getattr(row,'label',str(row)),self.small_font,rr.width-18),True,self._theme['text'])
            screen.blit(label,(rr.x+9,rr.y+8));self._ui_target(rr,f'UI_SELECT:{i}')
        self._draw_floating_footer(x,y,w,h,'The catalog lists possible results; combine items in the experiment grid to reveal them')
        self._draw_crafting_tab_tooltip()
        pg.display.flip();self.clock.tick(120)

    def animate_discovery_pot(self,items,recipe_name):
        """One-shot presentation effect after the simulation accepts a combination."""
        pg=self.pg;screen=self.screen
        if screen is None:return
        base=screen.copy();sw,sh=screen.get_size()
        cx,cy=self._discovery_pot_center or (sw//2,sh//2)
        start=pg.time.get_ticks()
        while True:
            t=min(1.,(pg.time.get_ticks()-start)/520.)
            screen.blit(base,(0,0))
            for i,item in enumerate(items):
                source=(cx-160+i*78,cy+130)
                dest=(cx,cy)
                eased=t*t*(3-2*t)
                px=int(source[0]+(dest[0]-source[0])*eased)
                py=int(source[1]+(dest[1]-source[1])*eased-22*math.sin(t*math.pi))
                self._draw_item_icon(item,pg.Rect(px-22,py-22,44,44))
            radius=max(6,int(30*t))
            pg.draw.circle(screen,self._theme['accent'],(cx,cy),radius,2)
            pg.display.flip()
            if t>=1:break
            pg.event.pump();self.clock.tick(60)
        note=self.title_font.render(self._fit_ui_text('DISCOVERED  '+recipe_name,self.title_font,sw-80),True,self._theme['accent'])
        screen.blit(note,note.get_rect(center=(cx,cy+105)));pg.display.flip()
        pg.time.wait(300)

    def _present_crafting_home(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};pg=self.pg;screen=self.screen
        x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING','CRAFTING // DISCOVERY WORKBENCH',subtitle)
        left_w=max(270,min(340,cw//3));left=pg.Rect(cx,cy,left_w,h-(cy-y)-48);right=pg.Rect(left.right+16,cy,cw-left_w-16,left.height)
        for r in (left,right):pg.draw.rect(screen,self._theme['panel'],r,border_radius=7);pg.draw.rect(screen,self._theme['edge'],r,1,border_radius=7)
        head=self.title_font.render('DISCOVERY',True,self._theme['accent']);screen.blit(head,(left.x+16,left.y+16))
        prog=float(data.get('progress',0));bar=pg.Rect(left.x+16,left.y+58,left.width-32,16);pg.draw.rect(screen,(44,48,46),bar,border_radius=5);pg.draw.rect(screen,self._theme['good'],(bar.x,bar.y,int(bar.width*max(0,min(1,prog))),bar.height),border_radius=5)
        val=self.font.render(f"{data.get('known_recipes',0)} / {data.get('total_recipes',0)} recipes",True,self._theme['text']);screen.blit(val,(left.x+16,bar.bottom+10))
        yy=bar.bottom+48;metric_w=(left.width-40)//2
        metrics=[('Ready tests',str(data.get('ready_experiments',0))),('Materials',str(data.get('known_materials',0))),('Experiments',str(data.get('experiments_run',0))),('Crafting',str(data.get('crafting_skill',0)))]
        for i,(lab,val) in enumerate(metrics):
            mx=left.x+16+(i%2)*(metric_w+8);my=yy+(i//2)*67;self._draw_metric(pg.Rect(mx,my,metric_w,58),lab,val,accent=self._theme['good'] if lab=='Crafting' else self._theme['accent'])
        tip_y=yy+146;tip=self.small_font.render('DISCOVERY LOOP',True,self._theme['muted']);screen.blit(tip,(left.x+16,tip_y));tip_y+=24
        for line in ('Handle new materials','Reveal simple techniques','Test material combinations','Craft components to open branches'):
            bullet=self.small_font.render('◆ '+line,True,self._theme['text']);screen.blit(bullet,(left.x+16,tip_y));tip_y+=23
        ry=right.y+16;rh=max(58,min(74,(right.height-32-8*(len(rows)-1))//max(1,len(rows))))
        for i,row in enumerate(rows):
            label=getattr(row,'label',str(row));detail=('Known techniques' if i==0 else 'Trial-and-error discoveries' if i==1 else 'Examined item knowledge' if i==2 else 'Recipe dependency graph' if i==3 else 'Build from chosen materials')
            self._draw_menu_card(pg.Rect(right.x+14,ry+i*(rh+8),right.width-28,rh),label,i==selected,detail=detail,badge=str(i+1))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _present_crafting_categories(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};pg=self.pg;screen=self.screen;x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING','DISCOVERED RECIPE CATEGORIES',subtitle)
        grid=pg.Rect(cx,cy,cw,h-(cy-y)-48);pg.draw.rect(screen,self._theme['panel'],grid,border_radius=7);pg.draw.rect(screen,self._theme['edge'],grid,1,border_radius=7)
        cols=3;gap=12;cw2=(grid.width-28-gap*(cols-1))//cols;ch=96
        for i,row in enumerate(rows):
            gx=i%cols;gy=i//cols;rect=pg.Rect(grid.x+14+gx*(cw2+gap),grid.y+14+gy*(ch+gap),cw2,ch)
            self._ui_target(rect,f'UI_SELECT:{i}')
            active=i==selected;key=getattr(row,'key','');count=(data.get('counts') or {}).get(key,0)
            pg.draw.rect(screen,(42,40,35) if active else self._theme['panel2'],rect,border_radius=7);pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,2 if active else 1,border_radius=7)
            label_text='Search recipes' if key=='__search__' else key.replace('_',' ').title()
            label=self.font.render(self._fit_ui_text(label_text,self.font,rect.width-24),True,self._theme['text']);screen.blit(label,(rect.x+12,rect.y+15))
            if key=='__search__':
                word=self.small_font.render('Technique, profession or output',True,self._theme['muted']);screen.blit(word,(rect.x+12,rect.bottom-word.get_height()-16))
            else:
                num=self.title_font.render(str(count),True,self._theme['accent']);screen.blit(num,(rect.x+12,rect.bottom-num.get_height()-13))
                word=self.small_font.render('discovered',True,self._theme['muted']);screen.blit(word,(rect.x+50,rect.bottom-word.get_height()-16))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _present_crafting_recipes(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};recipes=data.get('recipes',{});pg=self.pg;screen=self.screen;x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING',title,subtitle)
        list_w=max(430,int(cw*.58));lst=pg.Rect(cx,cy,list_w,h-(cy-y)-48);detail=pg.Rect(lst.right+16,cy,cw-list_w-16,lst.height)
        for r in (lst,detail):pg.draw.rect(screen,self._theme['panel'],r,border_radius=7);pg.draw.rect(screen,self._theme['edge'],r,1,border_radius=7)
        rh=max(72,min(92,(lst.height-28)//max(1,min(len(rows),6))))
        for i,row in enumerate(rows):
            rect=pg.Rect(lst.x+12,lst.y+12+i*(rh+6),lst.width-24,rh)
            if rect.bottom>lst.bottom-10:break
            self._ui_target(rect,f'UI_SELECT:{i}')
            rid=getattr(row,'key','');meta=recipes.get(rid,{});active=i==selected;ready=bool(meta.get('ready'))
            pg.draw.rect(screen,(41,43,39) if active else self._theme['panel2'],rect,border_radius=6);pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,2 if active else 1,border_radius=6)
            out=(meta.get('outputs') or [{}])[0];icon=pg.Rect(rect.x+8,rect.y+8,56,rect.height-16)
            if out.get('id'):self._draw_item_icon(out['id'],icon)
            badge='READY' if ready else 'NEEDS';bc=self._theme['good'] if ready else self._theme['danger'];bs=self.small_font.render(badge,True,bc);screen.blit(bs,(rect.right-bs.get_width()-10,rect.y+10))
            name=self.font.render(self._fit_ui_text(meta.get('name',rid),self.font,rect.width-160),True,self._theme['text']);screen.blit(name,(rect.x+72,rect.y+10))
            out_label=', '.join(f"{x.get('name','')} x{x.get('qty',1)}" for x in meta.get('outputs',[])[:2]);os=self.small_font.render(self._fit_ui_text(out_label,self.small_font,rect.width-160),True,self._theme['muted']);screen.blit(os,(rect.x+72,rect.y+36))
            ts=self.small_font.render(f"{meta.get('minutes',0)}m",True,self._theme['accent']);screen.blit(ts,(rect.x+72,rect.bottom-ts.get_height()-8))
        if rows:
            rid=getattr(rows[max(0,min(selected,len(rows)-1))],'key','');meta=recipes.get(rid,{})
            yy=detail.y+16;name=self.title_font.render(self._fit_ui_text(meta.get('name',rid),self.title_font,detail.width-32),True,self._theme['accent']);screen.blit(name,(detail.x+16,yy));yy+=32
            status='READY TO CRAFT' if meta.get('ready') else 'MISSING REQUIREMENTS';ss=self.small_font.render(status,True,self._theme['good'] if meta.get('ready') else self._theme['danger']);screen.blit(ss,(detail.x+16,yy));yy+=27
            desc=meta.get('description','')
            for line in self._wrap_pixel_text(desc,self.small_font,detail.width-32)[:4]:s=self.small_font.render(line,True,self._theme['text']);screen.blit(s,(detail.x+16,yy));yy+=18
            yy+=6;lab=self.small_font.render('MATERIALS',True,self._theme['muted']);screen.blit(lab,(detail.x+16,yy));yy+=21
            for inp in meta.get('inputs',[])[:7]:
                ok=inp.get('have',0)>=inp.get('need',0);ir=pg.Rect(detail.x+16,yy,34,28);self._draw_item_icon(inp.get('id',''),ir,scale=.82)
                s=self.small_font.render(f"{inp.get('name','')}  {inp.get('have',0)}/{inp.get('need',0)}",True,self._theme['text'] if ok else self._theme['danger']);screen.blit(s,(detail.x+54,yy+6));yy+=31
            yy+=4
            for labtxt,val in [('Time',f"{meta.get('minutes',0)} min"),('Skill',str(meta.get('skill','crafting')).replace('_',' ').title()),('Station',meta.get('station') or 'Hand craft')]:
                l=self.small_font.render(labtxt,True,self._theme['muted']);v=self.small_font.render(str(val),True,self._theme['text']);screen.blit(l,(detail.x+16,yy));screen.blit(v,(detail.right-v.get_width()-16,yy));yy+=21
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _present_crafting_experiments(self,title,rows,selected,**kwargs):
        data=kwargs.get('data') or {};recipes=data.get('recipes',{});clues=data.get('clues',{})
        # Reuse recipe browser with experiment-specific labels then overlay clue note.
        self._present_crafting_recipes(title,rows,selected,**kwargs)
        if self.screen is None or not rows:return
        pg=self.pg;rid=getattr(rows[max(0,min(selected,len(rows)-1))],'key','');meta=recipes.get(rid,{})
        note=self.small_font.render(f"Trial idea • {len(clues.get(rid,[]))} known material clue(s) • {15+int(meta.get('difficulty',0))*5}m experiment",True,self._theme['accent'])
        self.screen.blit(note,(38,58));pg.display.flip()

    def _present_crafting_designs(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};designs=data.get('designs',{});pg=self.pg;screen=self.screen;x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING','CRAFTING // COMPONENT DESIGNS',subtitle)
        panel=pg.Rect(cx,cy,cw,h-(cy-y)-48);pg.draw.rect(screen,self._theme['panel'],panel,border_radius=7);pg.draw.rect(screen,self._theme['edge'],panel,1,border_radius=7)
        cols=3;gap=14;card_w=(panel.width-28-gap*(cols-1))//cols;card_h=min(300,panel.height-28)
        for i,row in enumerate(rows):
            rect=pg.Rect(panel.x+14+(i%cols)*(card_w+gap),panel.y+14+(i//cols)*(card_h+gap),card_w,card_h)
            if rect.bottom>panel.bottom-12:break
            self._ui_target(rect,f'UI_SELECT:{i}')
            did=getattr(row,'key','');meta=designs.get(did,{});active=i==selected
            pg.draw.rect(screen,(42,40,35) if active else self._theme['panel2'],rect,border_radius=7);pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,2 if active else 1,border_radius=7)
            icon=pg.Rect(rect.x+18,rect.y+16,rect.width-36,125);self._draw_item_icon(meta.get('output_id',''),icon,scale=.8)
            name=self.title_font.render(self._fit_ui_text(meta.get('name',did),self.title_font,rect.width-28),True,self._theme['accent'] if active else self._theme['text']);screen.blit(name,(rect.x+14,rect.y+148))
            out=self.small_font.render(self._fit_ui_text('Creates '+str(meta.get('output_name','')),self.small_font,rect.width-28),True,self._theme['muted']);screen.blit(out,(rect.x+14,rect.y+180))
            yy=rect.y+210
            for slot in meta.get('slots',[])[:4]:
                s=self.small_font.render('◆ '+str(slot.get('name','')).replace('_',' ').title()+f"  ({len(slot.get('choices',[]))} choices)",True,self._theme['text']);screen.blit(s,(rect.x+14,yy));yy+=21
            t=self.small_font.render(f"Assembly time {meta.get('minutes',0)}m",True,self._theme['accent']);screen.blit(t,(rect.x+14,rect.bottom-t.get_height()-12))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _present_crafting_component_choices(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};designs=data.get('designs',{});did=data.get('design_id','');slot_name=data.get('slot','');design=designs.get(did,{})
        pg=self.pg;screen=self.screen;x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING',title,f"Choose material for {str(slot_name).replace('_',' ').title()}")
        left=pg.Rect(cx,cy,max(310,int(cw*.35)),h-(cy-y)-48);right=pg.Rect(left.right+16,cy,cw-left.width-16,left.height)
        for r in (left,right):pg.draw.rect(screen,self._theme['panel'],r,border_radius=7);pg.draw.rect(screen,self._theme['edge'],r,1,border_radius=7)
        out_id=design.get('output_id','');icon=pg.Rect(left.x+24,left.y+18,left.width-48,165);pg.draw.rect(screen,(17,20,21),icon,border_radius=6);self._draw_item_icon(out_id,icon,scale=.78)
        yy=icon.bottom+14;name=self.title_font.render(self._fit_ui_text(design.get('name','Design'),self.title_font,left.width-32),True,self._theme['accent']);screen.blit(name,(left.x+16,yy));yy+=30
        slots=design.get('slots',[]);cur=next((s for s in slots if s.get('name')==slot_name),{})
        lab=self.small_font.render(str(slot_name).replace('_',' ').upper(),True,self._theme['muted']);screen.blit(lab,(left.x+16,yy));yy+=24
        desc=self.small_font.render(f"{len(cur.get('choices',[]))} compatible materials",True,self._theme['text']);screen.blit(desc,(left.x+16,yy));yy+=26
        ry=right.y+14;rh=max(82,min(110,(right.height-28)//max(1,min(5,len(rows)))))
        choice_map={c.get('id'):c for c in cur.get('choices',[])}
        for i,row in enumerate(rows):
            rect=pg.Rect(right.x+14,ry+i*(rh+7),right.width-28,rh)
            if rect.bottom>right.bottom-12:break
            self._ui_target(rect,f'UI_SELECT:{i}')
            iid=getattr(row,'key','');meta=choice_map.get(iid,{});active=i==selected;ok=meta.get('have',0)>=meta.get('qty',0)
            pg.draw.rect(screen,(41,43,39) if active else self._theme['panel2'],rect,border_radius=6);pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,2 if active else 1,border_radius=6)
            ir=pg.Rect(rect.x+8,rect.y+8,70,rect.height-16);self._draw_item_icon(iid,ir,scale=.8)
            nm=self.font.render(self._fit_ui_text(meta.get('name',iid),self.font,rect.width-180),True,self._theme['text']);screen.blit(nm,(rect.x+88,rect.y+13))
            mat=self.small_font.render(str(meta.get('material','')),True,self._theme['muted']);screen.blit(mat,(rect.x+88,rect.y+39))
            need=self.small_font.render(f"have {meta.get('have',0)} / need {meta.get('qty',0)}",True,self._theme['good'] if ok else self._theme['danger']);screen.blit(need,(rect.x+88,rect.bottom-need.get_height()-11))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _present_crafting_recipe_detail(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};rid=data.get('recipe_id','');meta=(data.get('recipes') or {}).get(rid,{})
        pg=self.pg;screen=self.screen;x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING',meta.get('name',title),subtitle)
        left=pg.Rect(cx,cy,max(440,int(cw*.64)),h-(cy-y)-48);right=pg.Rect(left.right+16,cy,cw-left.width-16,left.height)
        for r in (left,right):pg.draw.rect(screen,self._theme['panel'],r,border_radius=7);pg.draw.rect(screen,self._theme['edge'],r,1,border_radius=7)
        yy=left.y+16;outs=meta.get('outputs',[]);main=outs[0] if outs else {}
        if main.get('id'):
            icon=pg.Rect(left.x+18,yy,120,120);pg.draw.rect(screen,(17,20,21),icon,border_radius=6);self._draw_item_icon(main['id'],icon,scale=.78)
        nx=left.x+154;name=self.title_font.render(self._fit_ui_text(meta.get('name','Recipe'),self.title_font,left.right-nx-18),True,self._theme['accent']);screen.blit(name,(nx,yy+6))
        status='READY TO CRAFT' if meta.get('ready') else 'REQUIREMENTS MISSING';st=self.small_font.render(status,True,self._theme['good'] if meta.get('ready') else self._theme['danger']);screen.blit(st,(nx,yy+38))
        desc_y=yy+66
        for line in self._wrap_pixel_text(meta.get('description',''),self.small_font,left.right-nx-18)[:4]:s=self.small_font.render(line,True,self._theme['text']);screen.blit(s,(nx,desc_y));desc_y+=18
        yy+=142;lab=self.small_font.render('MATERIAL REQUIREMENTS',True,self._theme['muted']);screen.blit(lab,(left.x+18,yy));yy+=23
        for inp in meta.get('inputs',[])[:8]:
            rr=pg.Rect(left.x+18,yy,44,34);self._draw_item_icon(inp.get('id',''),rr,scale=.82);ok=inp.get('have',0)>=inp.get('need',0)
            txt=self.font.render(f"{inp.get('name','')}  {inp.get('have',0)}/{inp.get('need',0)}",True,self._theme['text'] if ok else self._theme['danger']);screen.blit(txt,(left.x+70,yy+6));yy+=39
        yy+=5
        for labtxt,val in [('Base time',f"{meta.get('minutes',0)} min"),('Skill',str(meta.get('skill','crafting')).replace('_',' ').title()),('Difficulty',str(meta.get('difficulty',0))),('Station',meta.get('station') or 'Hand craft')]:
            l=self.small_font.render(labtxt,True,self._theme['muted']);v=self.small_font.render(str(val),True,self._theme['text']);screen.blit(l,(left.x+18,yy));screen.blit(v,(left.right-v.get_width()-18,yy));yy+=21
        ry=right.y+16
        for i,row in enumerate(rows):self._draw_menu_card(pg.Rect(right.x+12,ry+i*70,right.width-24,60),getattr(row,'label',str(row)),i==selected,badge=str(i+1))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _wrap_pixel_text(self, text: str, font, max_width: int) -> list[str]:
        words=str(text or '').split()
        if not words:return []
        max_width=max(1,max_width)
        # Break unspaced words too, so names/IDs cannot cross a panel boundary.
        chunks=[]
        for word in words:
            part=''
            for char in word:
                if part and font.size(part+char)[0]>max_width:
                    chunks.append(part);part=''
                part+=char
            if part:chunks.append(part)
        lines=[];cur=chunks[0]
        for word in chunks[1:]:
            trial=cur+' '+word
            if font.size(trial)[0]<=max_width:cur=trial
            else:lines.append(cur);cur=word
        lines.append(cur);return lines

    def _present_inventory_item_detail(self,title,*,lines=None,footer='',breadcrumb='',data=None,scroll_offset=0):
        data=data or {};iid=data.get('item_id','');meta=(data.get('items') or {}).get(iid,{})
        pg=self.pg;screen=self.screen;x,y,w,h,cx,cy,cw=self._feature_shell('INVENTORY',meta.get('name',title),meta.get('category','').replace('_',' ').title())
        left=pg.Rect(cx,cy,max(300,int(cw*.38)),h-(cy-y)-48);right=pg.Rect(left.right+16,cy,cw-left.width-16,left.height)
        for r in (left,right):pg.draw.rect(screen,self._theme['panel'],r,border_radius=7);pg.draw.rect(screen,self._theme['edge'],r,1,border_radius=7)
        icon=pg.Rect(left.x+22,left.y+18,left.width-44,min(250,left.height//2));pg.draw.rect(screen,(17,20,21),icon,border_radius=6);self._draw_item_icon(iid,icon,scale=.78)
        yy=icon.bottom+16
        metrics=[('Carried',str(meta.get('count',0))),('Unit mass',f"{meta.get('unit_mass_kg',0):.2f} kg"),('Stack mass',f"{meta.get('mass_kg',0):.2f} kg"),('Volume',f"{meta.get('volume_l',0):.2f} L")]
        for lab,val in metrics:
            l=self.small_font.render(lab,True,self._theme['muted']);v=self.small_font.render(val,True,self._theme['text']);screen.blit(l,(left.x+18,yy));screen.blit(v,(left.right-v.get_width()-18,yy));yy+=23
        if meta.get('equip_slot'):
            e=self.small_font.render('EQUIP SLOT  '+str(meta.get('equip_slot')).replace('_',' ').upper(),True,self._theme['accent']);screen.blit(e,(left.x+18,yy));yy+=24
        right_y=right.y+16
        desc=str(meta.get('description','')).strip()
        if desc:
            hd=self.small_font.render('DESCRIPTION',True,self._theme['muted']);screen.blit(hd,(right.x+16,right_y));right_y+=24
            for line in self._wrap_pixel_text(desc,self.font,right.width-32)[:7]:
                s=self.font.render(line,True,self._theme['text']);screen.blit(s,(right.x+16,right_y));right_y+=21
            right_y+=8
        roles=list(meta.get('roles') or []);tags=list(meta.get('tags') or [])
        if roles:
            hd=self.small_font.render('USES',True,self._theme['muted']);screen.blit(hd,(right.x+16,right_y));right_y+=22
            for role in roles[:8]:
                s=self.small_font.render('◆ '+str(role).replace('_',' ').title(),True,self._theme['text']);screen.blit(s,(right.x+16,right_y));right_y+=20
            right_y+=8
        if tags:
            hd=self.small_font.render('TAGS',True,self._theme['muted']);screen.blit(hd,(right.x+16,right_y));right_y+=21
            tx=right.x+16
            ty=right_y
            for tag in tags[:10]:
                label=str(tag).replace('_',' ');surf=self.small_font.render(label,True,self._theme['text']);tw=surf.get_width()+18
                if tx+tw>right.right-16:tx=right.x+16;ty+=28
                rr=pg.Rect(tx,ty,tw,23);pg.draw.rect(screen,self._theme['panel2'],rr,border_radius=10);pg.draw.rect(screen,self._theme['edge'],rr,1,border_radius=10);screen.blit(surf,(rr.x+9,rr.y+3));tx+=tw+7
            right_y=ty+31
        if lines:
            hd=self.small_font.render('DETAILS',True,self._theme['muted']);screen.blit(hd,(right.x+16,right_y));right_y+=22
            clean=[str(x).strip() for x in lines if str(x).strip()]
            for line in clean[scroll_offset:scroll_offset+max(3,(right.bottom-right_y-12)//18)]:
                s=self.small_font.render(self._fit_ui_text(line,self.small_font,right.width-32),True,self._theme['muted']);screen.blit(s,(right.x+16,right_y));right_y+=18
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _present_crafting_materials(self,title,*,footer='',breadcrumb='',data=None,scroll_offset=0):
        data=data or {};items=list((data.get('items') or {}).items());pg=self.pg;screen=self.screen
        x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING','CRAFTING // MATERIAL DISCOVERIES','Items you have handled become clues for future techniques.')
        panel=pg.Rect(cx,cy,cw,h-(cy-y)-48);pg.draw.rect(screen,self._theme['panel'],panel,border_radius=7);pg.draw.rect(screen,self._theme['edge'],panel,1,border_radius=7)
        cols=6 if panel.width>=900 else 5;gap=9;card_w=(panel.width-28-gap*(cols-1))//cols;card_h=106;rows_visible=max(1,(panel.height-28)//(card_h+gap));per=cols*rows_visible
        start=min(max(0,scroll_offset),max(0,len(items)-per))
        for j,(iid,meta) in enumerate(items[start:start+per]):
            gx=j%cols;gy=j//cols;rect=pg.Rect(panel.x+14+gx*(card_w+gap),panel.y+14+gy*(card_h+gap),card_w,card_h)
            pg.draw.rect(screen,self._theme['panel2'],rect,border_radius=6);pg.draw.rect(screen,self._theme['edge'],rect,1,border_radius=6)
            self._draw_item_icon(iid,pg.Rect(rect.x+8,rect.y+7,rect.width-16,56))
            nm=self.small_font.render(self._fit_ui_text(meta.get('name',iid),self.small_font,rect.width-14),True,self._theme['text']);screen.blit(nm,(rect.x+7,rect.y+65))
            mat=self.small_font.render(self._fit_ui_text(meta.get('material') or meta.get('category',''),self.small_font,rect.width-14),True,self._theme['muted']);screen.blit(mat,(rect.x+7,rect.bottom-mat.get_height()-6))
        count=self.small_font.render(f"{len(items)} discovered material/item types",True,self._theme['accent']);screen.blit(count,(panel.x+14,panel.bottom-23))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def _present_crafting_tree(self,title,*,footer='',breadcrumb='',data=None,scroll_offset=0):
        data=data or {};nodes=data.get('nodes',[]);pg=self.pg;screen=self.screen
        x,y,w,h,cx,cy,cw=self._feature_shell('CRAFTING','CRAFTING // DISCOVERY TECH TREE','Branches are revealed by materials, experiments, and crafted components.')
        panel=pg.Rect(cx,cy,cw,h-(cy-y)-48);pg.draw.rect(screen,self._theme['panel'],panel,border_radius=7);pg.draw.rect(screen,self._theme['edge'],panel,1,border_radius=7)
        # Compute a stable dependency depth for each recipe. Cycles collapse to depth zero.
        by_id={n['id']:n for n in nodes};memo={}
        def depth(rid,trail=()):
            if rid in memo:return memo[rid]
            if rid in trail:return 0
            n=by_id.get(rid,{});parents=[p for p in n.get('parents',[]) if p in by_id]
            d=0 if not parents else 1+max(depth(p,trail+(rid,)) for p in parents)
            memo[rid]=min(d,4);return memo[rid]
        ordered=sorted(nodes,key=lambda n:(depth(n['id']),n.get('category',''),n.get('name','')))
        cols=5;gap=16;col_w=max(150,(panel.width-32-gap*(cols-1))//cols);node_h=58
        lanes={d:[] for d in range(cols)}
        for n in ordered:lanes[depth(n['id'])].append(n)
        max_rows=max([len(v) for v in lanes.values()] or [1]);visible_rows=max(1,(panel.height-50)//(node_h+10));row_start=min(max(0,scroll_offset),max(0,max_rows-visible_rows))
        rects={}
        for d in range(cols):
            x0=panel.x+16+d*(col_w+gap);head=self.small_font.render(('FOUNDATION' if d==0 else f'TIER {d+1}'),True,self._theme['muted']);screen.blit(head,(x0,panel.y+10))
            for j,n in enumerate(lanes[d][row_start:row_start+visible_rows]):
                yy=panel.y+34+j*(node_h+10);rect=pg.Rect(x0,yy,col_w,node_h);rects[n['id']]=rect
        # connectors first
        for n in ordered:
            child=rects.get(n['id'])
            if not child:continue
            for parent in n.get('parents',[]):
                pr=rects.get(parent)
                if pr:pg.draw.aaline(screen,self._theme['edge_hi'],(pr.right,pr.centery),(child.left,child.centery))
        status_colors={'known':self._theme['good'],'experiment':self._theme['accent'],'knowledge':self._theme['danger'],'materials':(121,128,117),'locked':(100,106,104)}
        for n in ordered:
            rect=rects.get(n['id'])
            if not rect:continue
            color=status_colors.get(n.get('status','locked'),self._theme['edge']);pg.draw.rect(screen,self._theme['panel2'],rect,border_radius=5);pg.draw.rect(screen,color,rect,2,border_radius=5)
            out=(n.get('outputs') or [''])[0];icon=pg.Rect(rect.x+5,rect.y+7,42,42)
            if out:self._draw_item_icon(out,icon,scale=.85)
            name=self.small_font.render(self._fit_ui_text(n.get('name',''),self.small_font,rect.width-58),True,self._theme['text']);screen.blit(name,(rect.x+52,rect.y+10))
            st=self.small_font.render(n.get('status','locked').upper(),True,color);screen.blit(st,(rect.x+52,rect.bottom-st.get_height()-7))
        legend=f"KNOWN {data.get('known',0)} / {data.get('total',len(nodes))}   •   green known   •   gold experiment   •   gray/ red locked"
        ls=self.small_font.render(self._fit_ui_text(legend,self.small_font,panel.width-28),True,self._theme['muted']);screen.blit(ls,(panel.x+14,panel.bottom-20))
        self._draw_feature_footer(x,y,w,h,footer);pg.display.flip();self.clock.tick(120)

    def present_menu(self, title: str, rows, selected: int, *, subtitle: str='', breadcrumb: str='',
                     footer: str='', page_start: int=0, total: int|None=None) -> None:
        """Draw the retained menu widget as graphical cards.

        The calling widget still owns selection and input.  This method never
        mutates game state, which keeps the renderer/command boundary intact.
        """
        self._hover_context=None;self._hover_map_snapshot=None;self._hover_rect=None;self._hover_tile_rect=None;self._hover_cell=None
        pg=self.pg;screen=self.screen
        if screen is None:return
        domain,_,_=self._ui_domain(title)
        is_main=title.upper().startswith('WORLDSEED ')
        x,y,w,h=self._draw_chrome('WORLDSEED' if is_main else f'WORLDSEED // {domain}')
        panel_w=min(w-32,690 if is_main else 780)
        panel_h=min(h-24,max(285,145+len(rows)*39+(24 if subtitle else 0)+(20 if breadcrumb else 0)))
        panel=pg.Rect(x+(w-panel_w)//2,y+(h-panel_h)//2,panel_w,panel_h)
        self._menu_ambient_rects=(pg.Rect(x,y,max(0,panel.x-x-10),h),pg.Rect(panel.right+10,y,max(0,x+w-panel.right-10),h))
        shadow=pg.Surface((panel_w+16,panel_h+16),pg.SRCALPHA)
        pg.draw.rect(shadow,(0,0,0,110),shadow.get_rect(),border_radius=12)
        screen.blit(shadow,(panel.x-8,panel.y+5))
        pg.draw.rect(screen,(25,31,31),panel,border_radius=8)
        pg.draw.rect(screen,(119,105,72),panel,2,border_radius=8)
        pg.draw.rect(screen,(57,72,67),panel.inflate(-12,-12),1,border_radius=5)
        pg.draw.line(screen,self._theme['accent'],(panel.x+26,panel.y+8),(panel.right-26,panel.y+8),2)
        pad=29;cx=panel.x+pad;cy=panel.y+(27 if is_main else 21);cw=panel_w-pad*2
        # strong title hierarchy replaces the ASCII border/title line
        heading='WORLDSEED' if is_main else title
        title_font=self.title_font
        title_surf=title_font.render(heading,True,self._theme['accent'] if is_main else self._theme['text'])
        screen.blit(title_surf,(panel.centerx-title_surf.get_width()//2,cy));cy+=title_surf.get_height()+9
        cy=self._draw_ui_tabs(title,cx,cy,cw)
        if breadcrumb:
            crumb=self.small_font.render(self._fit_ui_text('‹ '+breadcrumb,self.small_font,cw),True,self._theme['muted']);screen.blit(crumb,(cx,cy));cy+=21
        if subtitle:
            sub=self.small_font.render(self._fit_ui_text(subtitle,self.small_font,cw),True,self._theme['muted'])
            screen.blit(sub,(panel.centerx-sub.get_width()//2,cy));cy+=23
        bottom=panel.bottom-54
        count=max(1,len(rows));available=max(1,bottom-cy)
        row_h=max(22,min(34,available//count))
        row_gap=4 if row_h>=28 else 2
        card_h=max(20,row_h-row_gap)
        for i,row in enumerate(rows):
            if cy+card_h>bottom:break
            is_sel=i==selected;rect=pg.Rect(cx,cy,cw,card_h)
            self._ui_target(rect,f'UI_SELECT:{i}')
            fill=(35,40,43) if is_sel else self._theme['panel2']
            pg.draw.rect(screen,fill,rect,border_radius=5)
            pg.draw.rect(screen,self._theme['accent'] if is_sel else self._theme['edge'],rect,width=2 if is_sel else 1,border_radius=5)
            if is_sel:pg.draw.rect(screen,self._theme['accent'],(rect.x,rect.y,4,rect.h),border_radius=2)
            badge=f'{page_start+i+1}'
            badge_s=self.small_font.render(badge,True,self._theme['accent'] if is_sel else self._theme['muted'])
            screen.blit(badge_s,(rect.x+13,rect.centery-badge_s.get_height()//2))
            label=getattr(row,'label',str(row));hint=getattr(row,'hint','')
            text_color=self._semantic_row_color(label) if not is_sel else self._theme['text']
            font=self.font if card_h>=27 else self.small_font
            left=rect.x+48;maxw=rect.right-left-14
            surf=font.render(self._fit_ui_text(label,font,maxw),True,text_color);screen.blit(surf,(left,rect.centery-surf.get_height()//2-(5 if hint and card_h>=32 else 0)))
            if is_sel and hint and card_h>=32:
                hs=self.small_font.render(self._fit_ui_text(hint,self.small_font,maxw),True,self._theme['muted']);screen.blit(hs,(left,rect.bottom-hs.get_height()-3))
            cy+=row_h
        if total is not None and total>len(rows):
            page=self.small_font.render(f'{page_start+1}-{min(total,page_start+len(rows))} / {total}',True,self._theme['muted'])
            screen.blit(page,(panel.right-page.get_width()-20,panel.bottom-29))
        if is_main:
            motto=self.small_font.render('SEED  ·  SURVIVE  ·  SHAPE THE WORLD',True,self._theme['muted'])
            screen.blit(motto,(panel.centerx-motto.get_width()//2,panel.bottom-34))
        self._menu_nav_rect=panel
        if not is_main:self._ui_navigation(back=not footer or 'Esc back' in footer,paging=bool(total is not None and total>len(rows)))
        self._draw_scanlines((x,y,w,h));pg.display.flip();self.clock.tick(120)

    def present_sprite_gallery(self, title: str, *, sex: str, selected: int, labels: list[str] | tuple[str, ...], subtitle: str='', footer: str='') -> None:
        """Draw a graphical survivor-appearance picker with sprite thumbnails."""
        self._hover_context=None;self._hover_map_snapshot=None;self._hover_rect=None;self._hover_tile_rect=None;self._hover_cell=None
        pg=self.pg;screen=self.screen
        if screen is None:return
        x,y,w,h=self._draw_chrome('WORLDSEED // CHARACTER CREATION')
        self._paint_menu_veil((x,y,w,h))
        pad=18;cx=x+pad;cy=y+14;cw=w-pad*2
        heading=self.title_font.render(title,True,self._theme['text']);screen.blit(heading,(cx,cy));cy+=heading.get_height()+8
        if subtitle:
            sub=self.small_font.render(self._fit_ui_text(subtitle,self.small_font,cw),True,self._theme['muted'])
            screen.blit(sub,(cx,cy));cy+=22
        tabs=[('male','Male'),('female','Female')]
        tx=cx
        for key,label in tabs:
            rect=pg.Rect(tx,cy,112,28);active=(sex==key)
            self._ui_target(rect,f'UI_SEX:{key}')
            pg.draw.rect(screen,self._theme['panel2'] if active else self._theme['panel'],rect,border_radius=5)
            pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,width=2 if active else 1,border_radius=5)
            surf=self.small_font.render(label,True,self._theme['text'] if active else self._theme['muted'])
            screen.blit(surf,(rect.centerx-surf.get_width()//2,rect.centery-surf.get_height()//2))
            tx+=rect.width+8
        cy+=40

        left_w=max(220,min(290,cw//3))
        preview=pg.Rect(cx,cy,left_w,max(260,h-(cy-y)-66))
        grid=pg.Rect(preview.right+16,cy,cw-left_w-16,max(260,h-(cy-y)-66))
        pg.draw.rect(screen,self._theme['panel'],preview,border_radius=6)
        pg.draw.rect(screen,self._theme['edge'],preview,width=1,border_radius=6)
        pg.draw.rect(screen,self._theme['panel'],grid,border_radius=6)
        pg.draw.rect(screen,self._theme['edge'],grid,width=1,border_radius=6)

        paths=self._visuals.player_paths(sex)
        selected=max(0,min(selected,max(0,len(paths)-1)))
        label=labels[selected] if selected < len(labels) else f'Look {selected+1:02d}'
        meta=self.small_font.render(f'{sex.title()} survivor set',True,self._theme['muted'])
        screen.blit(meta,(preview.x+16,preview.y+14))
        name=self.title_font.render(label,True,self._theme['accent'])
        screen.blit(name,(preview.x+16,preview.y+36))
        card=pg.Rect(preview.x+22,preview.y+78,preview.width-44,preview.height-136)
        pg.draw.rect(screen,(18,21,23),card,border_radius=5)
        pg.draw.rect(screen,self._theme['edge_hi'],card,width=1,border_radius=5)
        sprite=self._load_sprite(paths[selected] if paths else None, card.width-18, card.height-18)
        if sprite is not None:
            screen.blit(sprite,(card.centerx-sprite.get_width()//2,card.centery-sprite.get_height()//2))
        line1=self.font.render(f'Appearance {selected+1:02d} / {max(1,len(paths))}',True,self._theme['text'])
        screen.blit(line1,(preview.x+16,preview.bottom-48))
        line2=self.small_font.render(self._fit_ui_text('Appearance saved with character.',self.small_font,preview.width-32),True,self._theme['muted'])
        screen.blit(line2,(preview.x+16,preview.bottom-26))

        cols=5;rows=2;gap=10
        avail_w=grid.width-24-gap*(cols-1)
        cell_w=max(50,avail_w//cols)
        cell_h=max(108,min(150,(grid.height-24-gap*(rows-1))//rows))
        start_x=grid.x+(grid.width-(cell_w*cols+gap*(cols-1)))//2
        start_y=grid.y+16
        for i in range(min(10,len(paths))):
            gx=i%cols;gy=i//cols
            rect=pg.Rect(start_x+gx*(cell_w+gap),start_y+gy*(cell_h+gap),cell_w,cell_h)
            self._ui_target(rect,f'UI_APPEARANCE:{i}')
            active=(i==selected)
            pg.draw.rect(screen,self._theme['panel2'] if active else (18,21,23),rect,border_radius=6)
            pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rect,width=2 if active else 1,border_radius=6)
            thumb_box=pg.Rect(rect.x+8,rect.y+8,rect.width-16,rect.height-38)
            thumb=self._load_sprite(paths[i],thumb_box.width,thumb_box.height)
            if thumb is not None:
                screen.blit(thumb,(thumb_box.centerx-thumb.get_width()//2,thumb_box.bottom-thumb.get_height()))
            idx_s=self.small_font.render(f'{i+1:02d}',True,self._theme['accent'] if active else self._theme['muted'])
            screen.blit(idx_s,(rect.x+8,rect.y+6))
            lab=self.small_font.render(self._fit_ui_text(labels[i] if i < len(labels) else f'Look {i+1:02d}',self.small_font,rect.width-16),True,self._theme['text'] if active else self._theme['muted'])
            screen.blit(lab,(rect.centerx-lab.get_width()//2,rect.bottom-lab.get_height()-8))

        self._ui_navigation(confirm=True)
        self._draw_scanlines((x,y,w,h));pg.display.flip();self.clock.tick(120)

    def present_document(self, title: str, lines: list[str], *, footer: str='', breadcrumb: str='') -> None:
        """Graphical pager used by inventory/crafting detail and tree views."""
        self._hover_context=None;self._hover_map_snapshot=None;self._hover_rect=None;self._hover_tile_rect=None;self._hover_cell=None
        pg=self.pg;screen=self.screen
        if screen is None:return
        domain,_,_=self._ui_domain(title)
        x,y,w,h=self._draw_chrome(f'WORLDSEED // {domain}')
        self._paint_menu_veil((x,y,w,h))
        pad=18;cx=x+pad;cy=y+14;cw=w-pad*2
        heading=self.title_font.render(title,True,self._theme['text']);screen.blit(heading,(cx,cy));cy+=heading.get_height()+9
        cy=self._draw_ui_tabs(title,cx,cy,cw)
        if breadcrumb:
            crumb=self.small_font.render(self._fit_ui_text('‹ '+breadcrumb,self.small_font,cw),True,self._theme['muted']);screen.blit(crumb,(cx,cy));cy+=21
        content=pg.Rect(cx,cy,cw,max(40,y+h-46-cy));pg.draw.rect(screen,self._theme['panel'],content,border_radius=5);pg.draw.rect(screen,self._theme['edge'],content,width=1,border_radius=5)
        yy=content.y+10
        for raw in lines:
            if yy+self.char_h>content.bottom-7:break
            raw_text=str(raw) if raw else ''
            indented=raw_text.startswith('  ')
            text=raw_text.strip()
            if not text:yy+=max(8,self.char_h//2);continue
            is_section=(text.upper()==text and 2<=len(text)<=48 and not text.startswith('['))
            color=self._semantic_row_color(text)
            font=self.font
            if is_section:
                color=self._theme['accent'];font=self.small_font
                if yy>content.y+12:pg.draw.line(screen,self._theme['edge'],(content.x+10,yy-4),(content.right-10,yy-4),1)
            elif indented:color=self._theme['muted']
            surf=font.render(self._fit_ui_text(text,font,content.w-24),True,color);screen.blit(surf,(content.x+12,yy));yy+=max(self.char_h,font.get_linesize())
        self._ui_navigation()
        self._draw_scanlines((x,y,w,h));pg.display.flip();self.clock.tick(120)

    def _draw_scanlines(self, rect) -> None:
        # Full-window alpha scanlines are intentionally disabled by default in
        # the performance renderer. They cost a large blended blit every frame
        # while adding no gameplay information.
        if not self._scanlines_enabled:return
        x,y,w,h=rect;key=(w,h)
        overlay=self._scanline_cache.get(key)
        if overlay is None:
            overlay=self.pg.Surface((w,h), self.pg.SRCALPHA)
            for yy in range(0,h,4):self.pg.draw.line(overlay,(0,0,0,11),(0,yy),(w,yy))
            self._scanline_cache[key]=overlay
        self.screen.blit(overlay,(x,y))

    def _animate_idle_water(self, now):
        # No world queries, simulation ticks, or terrain generation here.
        if not self._hover_context or self._hover_map_snapshot is None:return
        phase=(now//160)%8
        if phase==getattr(self,'_water_animation_phase',None):return
        self._water_animation_phase=phase
        cells=getattr(self,'_water_animation_cells',())
        if not cells:return
        live_context=bool(self._current_presentation=='world_context' and self._context_menu_state and self._context_backdrop is not None)
        if live_context:self._restore_context_overlay(clear=False,update=False)
        self._restore_hover_damage()
        used=self._hover_context['used'];size=self._hover_context['tile_px']
        dirty=[]
        for rect,base,display,dx,dy,speed in cells:
            self.screen.blit(base,rect.topleft)
            self.screen.blit(self._animated_water_overlay(display,size,phase,dx,dy,speed),rect.topleft)
            self._hover_map_snapshot.blit(self.screen,rect.move(-used.x,-used.y).topleft,rect)
            dirty.append(rect)
        self._refresh_hover_only(force=True,update_display=False)
        self.pg.display.update(dirty+([self._hover_rect] if self._hover_rect else []))
        if live_context:self._redraw_live_context_overlay()

    def _animate_idle_effects(self, now):
        menu_pointer=self._input_mode in ('ui','text')
        if menu_pointer and self._menu_header_base is not None:
            self._animate_menu_effects(now)
            return
        if menu_pointer and self._menu_cursor_rect is not None and self._menu_cursor_backdrop is not None:
            self.screen.blit(self._menu_cursor_backdrop,self._menu_cursor_rect.topleft)
            self._menu_cursor_rect=None;self._menu_cursor_backdrop=None
        if not menu_pointer:self._tick_hud_tooltip(now)
        ctx=getattr(self,'_weather_animation_context',None)
        static=getattr(self,'_weather_static_snapshot',None)
        # Include the previous sample so a completed fade paints its final frame.
        transitioning = (self._weather_fx.lighting_transition_active(now) or
                         self._weather_fx.lighting_transition_active(
                             getattr(self, '_weather_last_frame_ms', now)))
        active = bool(ctx and static is not None and self._hover_context and
                      (self._weather_fx.has_animated_effects(ctx) or transitioning))
        if active:
            # Weather surfaces cover the entire view and can dominate a
            # maximized software-rendered frame. Keep animation wall-clock
            # based, but cap refresh frequency by actual drawable pixel area.
            used=self._hover_context['used']
            area=used.width*used.height
            interval=100 if area>1_600_000 else 66 if area>800_000 else 33
            phase=int(now)//interval
            if phase == getattr(self, '_weather_animation_phase', None):
                if menu_pointer:self._animate_menu_effects(now,force=True)
                return
            self._weather_animation_phase = phase
            self._weather_last_frame_ms = now
            live_context=bool(self._current_presentation=='world_context' and self._context_menu_state and self._context_backdrop is not None)
            if live_context:self._restore_context_overlay(clear=False,update=False)
            self._restore_hover_damage()
            used=self._hover_context['used']
            self.screen.blit(static,used.topleft)
            self._weather_fx.draw_lighting(self.screen,used,ctx['lighting'],elapsed_ms=now)
            self._weather_fx.draw_fire_glows(self.screen,used,ctx['fire_rects'],ctx['lighting'])
            self._weather_fx.draw_atmosphere(
                self.screen,used,ctx['seed'],ctx,world_left=int(ctx.get('left',0)),
                world_top=int(ctx.get('top',0)),tile_px=int(ctx.get('tile_px',28)),elapsed_ms=int(now),
                game_minute=ctx.get('minute',720),lighting=ctx['lighting'])
            self.pg.draw.rect(self.screen,(78,91,91),used,1)
            self._hover_map_snapshot=self.screen.subsurface(used).copy()
            self._hover_rect=None;self._hover_tile_rect=None
            self._refresh_hover_only(force=True,update_display=False)
            self.pg.display.update([used]+([self._hover_rect] if self._hover_rect else []))
            if live_context:self._redraw_live_context_overlay()
            if menu_pointer:self._animate_menu_effects(now,force=True)
            return
        if ctx and (bool(ctx.get('night',False)) or int(ctx.get('wetness',0))>=8):
            if menu_pointer:self._animate_menu_effects(now,force=True)
            return
        self._animate_idle_water(now)
        if menu_pointer:self._animate_menu_effects(now,force=True)
    def _fluid_overlay(self,tile_px:int):
        key=("water",tile_px);overlay=self._overlay_cache.get(key)
        if overlay is None:
            overlay=self.pg.Surface((tile_px,tile_px),self.pg.SRCALPHA);overlay.fill((45,103,137,110));self._overlay_cache[key]=overlay
        return overlay

    def _animated_water_overlay(self, display_id:str, tile_px:int, phase:int,
                                flow_dx:int=0, flow_dy:int=0, flow_speed:int=0):
        speed_band=0 if flow_speed < 28 else 1 if flow_speed < 58 else 2
        key=("water_dyn",display_id,tile_px,phase,flow_dx,flow_dy,speed_band); overlay=self._overlay_cache.get(key)
        if overlay is not None:return overlay
        pg=self.pg
        overlay=pg.Surface((tile_px,tile_px),pg.SRCALPHA)
        if display_id=='render:ocean_deep':
            primary=(232,238,239,14); secondary=(140,188,214,12); bands=3
        elif display_id=='render:ocean_shallow':
            primary=(241,240,228,20); secondary=(188,212,214,14); bands=4
        elif display_id=='render:estuary_mix':
            primary=(224,230,210,17); secondary=(170,196,168,13); bands=4
        elif display_id=='render:freshwater_deep':
            primary=(222,236,242,15); secondary=(152,203,217,12); bands=4
        else:  # render:freshwater_shallow
            primary=(236,236,221,18); secondary=(193,205,177,15); bands=5
        import math
        # Sparse, smooth wavelets replace the diagonal crosshatch/grid.
        # Cached by direction/speed/phase; wall clock drives visual time only.
        horizontal=abs(flow_dx)>=abs(flow_dy)
        sign=flow_dx if horizontal else flow_dy
        sign=sign or 1
        for lane in range(2):
            points=[]
            for along in range(-2,tile_px+3):
                cross=(lane+0.5)*tile_px/2 + math.sin(along/max(3,tile_px)*math.tau+phase*math.tau/8)*tile_px*.045
                cross=(cross+sign*phase*tile_px/32)%tile_px
                points.append((along,cross) if horizontal else (cross,along))
            pg.draw.aalines(overlay,(*primary[:3],18 if speed_band<2 else 28),False,points)
        if len(self._overlay_cache)>4096:self._overlay_cache.clear()
        self._overlay_cache[key]=overlay
        return overlay

    def _load_sprite(self, path: Path | None, max_w: int, max_h: int, *, smooth: bool = False):
        if path is None: return None
        key=(str(path),max_w,max_h,smooth)
        if key in self._sprite_cache: return self._sprite_cache[key]
        pg=self.pg
        try:
            surf=pg.image.load(str(path)).convert_alpha()
            scale=min(max_w/max(1,surf.get_width()),max_h/max(1,surf.get_height()))
            size=(max(1,int(surf.get_width()*scale)),max(1,int(surf.get_height()*scale)))
            surf=pg.transform.smoothscale(surf,size) if smooth or path in self._character_sprite_paths else pg.transform.scale(surf,size)
            self._sprite_cache[key]=surf
            return surf
        except Exception:
            return None

    def _load_terrain_sprite(self, path: Path | None, size: int):
        """Load terrain with a tiny overscan so source-edge halos never form grid seams.

        Terrain art is authored as edge-to-edge material. Smooth resampling used
        to sample the outermost PNG pixels directly; a bright/transparent export
        edge could therefore become a one-pixel white line around every world
        cell. Scaling slightly past the target and cropping back to the requested
        size keeps the material continuous without changing simulation geometry.
        """
        if path is None:return None
        key=(f'terrain-v3:{path}',size,size)
        if key in self._sprite_cache:return self._sprite_cache[key]
        try:
            source=self.pg.image.load(str(path)).convert_alpha()
            # Trim only the authored image's outer export edge.  Cropping in
            # source space avoids the heavy zoom that output-space overscan
            # would cause at 16-56 px gameplay sizes.
            trim=max(1,min(4,min(source.get_width(),source.get_height())//128))
            if source.get_width()>trim*2+2 and source.get_height()>trim*2+2:
                source=source.subsurface((trim,trim,source.get_width()-trim*2,source.get_height()-trim*2)).copy()
            surf=self.pg.transform.smoothscale(source,(size,size))
            self._sprite_cache[key]=surf
            return surf
        except Exception:
            return None

    def _draw_sprite_bottom(self, path: Path | None, cell_rect, max_h_mult: float=1.45, alpha: int=255, *, width_mult: float=1.35, smooth: bool=False) -> None:
        pg=self.pg
        max_w=int(cell_rect.width*width_mult); max_h=int(cell_rect.height*max_h_mult)
        surf=self._load_sprite(path,max_w,max_h,smooth=smooth)
        if surf is None: return
        if alpha != 255:
            surf=surf.copy(); surf.set_alpha(alpha)
        x=cell_rect.centerx-surf.get_width()//2; y=cell_rect.bottom-surf.get_height()
        self.screen.blit(surf,(x,y))

    def _load_atlas_frame(self, path: Path, column: int, row: int, frame_size: int,
                          max_w: int, max_h: int, *, smooth: bool=True):
        """Load one frame from a presentation atlas and cache the scaled result."""
        key=('atlas-frame',str(path),column,row,frame_size,max_w,max_h,smooth)
        cached=self._sprite_cache.get(key)
        if cached is not None:return cached
        source_key=('atlas-source',str(path))
        source=self._sprite_cache.get(source_key)
        try:
            if source is None:
                source=self.pg.image.load(str(path)).convert_alpha()
                self._sprite_cache[source_key]=source
            frame=self.pg.Rect(column*frame_size,row*frame_size,frame_size,frame_size)
            if frame.right>source.get_width() or frame.bottom>source.get_height():return None
            surf=source.subsurface(frame).copy()
            scale=min(max_w/max(1,surf.get_width()),max_h/max(1,surf.get_height()))
            size=(max(1,int(surf.get_width()*scale)),max(1,int(surf.get_height()*scale)))
            surf=self.pg.transform.smoothscale(surf,size) if smooth else self.pg.transform.scale(surf,size)
            self._sprite_cache[key]=surf
            return surf
        except Exception:
            return None

    def _settlement_piece_sprite_path(self,piece):
        """Resolve authored settlement fixtures/roofs/floors where suitable."""
        if piece is None:return None
        tags=set(getattr(piece,'tags',()) or ())|set(getattr(piece,'room_tags',()) or ())
        cat=str(getattr(piece,'category',''));mat=str(getattr(piece,'material',''));pid=str(getattr(piece,'id',''))
        sid=None
        direct=self._visuals.ref('settlement_pieces',pid)
        direct_path=self._visuals.resolve(direct)
        if direct_path is not None:return direct_path
        if cat=='roof':sid='core:stone_roof' if any(token in mat for token in ('stone','slate','clay')) else 'core:wood_roof'
        elif cat=='floor' and ('plank' in mat or 'wood' in mat):sid='core:wood_floor'
        elif 'bed' in tags:sid='core:bed'
        elif {'forge','anvil','bellows'} & tags:sid='core:forge'
        elif 'butchery' in tags or 'butcher' in pid:sid='core:butcher_table'
        elif 'tanning' in tags:sid='core:tanning_frame'
        elif 'drying' in tags:sid='core:drying_rack'
        elif 'hearth' in tags or 'fire' in tags or 'oven' in tags or 'kiln' in tags:sid='core:stone_hearth'
        elif 'storage' in tags or 'chest' in pid:sid='core:wood_chest'
        elif 'bridge' in tags or 'bridge' in pid:sid='core:bridge'
        elif 'support' in tags or 'fence' in tags:sid='core:support_beam'
        elif cat in {'furniture','workshop','agriculture','mine','decoration','civic'} and str(getattr(piece,'layer',''))!='ground':
            sid='core:workbench' if ({'workshop','station','desk','table','bench'} & tags) else 'core:stone_pillar'
        return self._visuals.resolve(self._visuals.ref('structures',sid)) if sid else None

    @staticmethod
    def _settlement_palette(piece):
        cat=str(getattr(piece,'category',''));mat=str(getattr(piece,'material',''));tags=set(getattr(piece,'tags',()) or ())
        if cat=='road':
            if 'cobble_road' in tags or 'stone_road' in tags or 'market_square' in tags or mat=='stone':
                return (111,108,101),(145,141,133),(76,76,73)
            if 'gravel_road' in tags or mat=='gravel':
                return (121,116,105),(150,144,131),(84,81,74)
            if 'plank_road' in tags or 'dock_walk' in tags or mat=='wood':
                return (116,85,54),(150,113,71),(77,56,37)
            return (116,88,60),(145,111,76),(80,59,41)
        if cat=='floor':
            if 'stone' in mat:return (116,116,111),(145,144,138),(79,81,79)
            if 'clay' in mat:return (136,91,65),(165,116,85),(98,64,47)
            if 'packed' in mat or 'earth' in mat:return (108,85,59),(139,109,77),(75,57,41)
            return (108,81,52),(143,108,70),(72,53,35)
        if cat=='roof':
            if any(token in mat for token in ('stone','slate','clay')):
                return (91,91,87),(132,130,122),(55,57,56)
            if 'thatch' in mat:
                return (126,103,61),(165,138,83),(78,62,38)
            return (101,67,40),(145,99,59),(59,39,27)
        if cat in {'wall','opening'}:
            if 'stone' in mat or 'iron' in mat:return (126,125,120),(159,157,150),(74,76,74)
            if 'wattle' in mat:return (112,91,65),(145,119,86),(72,57,40)
            return (124,90,56),(163,119,75),(78,56,36)
        return (118,98,72),(146,123,94),(82,65,47)

    def _settlement_connection_bits(self,key,cell,settlement_by,registry,*,ground=False):
        wx,wy,wz=key;bits=0
        current_piece=registry.settlement_pieces.get(cell.ground_piece_id if ground else cell.structure_piece_id)
        current_cat=str(getattr(current_piece,'category','')) if current_piece else ''
        if not ground:
            from worldseed.ui.fence_view import is_fence, connection_bits
            if is_fence(current_piece):
                return connection_bits(key,settlement_by,registry)
        for bit,dx,dy in ((1,0,-1),(2,1,0),(4,0,1),(8,-1,0)):
            other=settlement_by.get((wx+dx,wy+dy,wz))
            if other is None:continue
            if ground:
                other_piece=registry.settlement_pieces.get(other.ground_piece_id)
                other_cat=str(getattr(other_piece,'category','')) if other_piece else ''
                door_bridge=cell.structure_piece_role in {'entrance','interior_door'} or other.structure_piece_role in {'entrance','interior_door'}
                connected=(
                    current_cat=='road' and other_cat=='road'
                    or current_cat=='floor' and other_cat=='floor' and bool(cell.structure_id) and cell.structure_id==other.structure_id
                    or door_bridge and current_cat in {'floor','road'} and other_cat in {'floor','road'}
                )
            else:
                connected=bool(
                    other.structure_piece_id and cell.structure_id and cell.structure_id==other.structure_id
                    and other.structure_piece_role in {'wall','partition','entrance','interior_door'}
                )
            if connected:bits|=bit
        return bits

    def _settlement_material_overlay(self, surf, piece, size: int, opacity: int) -> None:
        """Clip an authored material to the connected surface's actual silhouette."""
        if piece is None:return
        category=str(getattr(piece,'category',''))
        material=str(getattr(piece,'material',''))
        path=self._visuals.settlement_material_path(category,material,getattr(piece,'tags',()),str(getattr(piece,'id','')))
        if path is None:return
        texture=self._load_terrain_sprite(path,size)
        if texture is None:return
        pg=self.pg
        mask=pg.mask.from_surface(surf).to_surface(
            setcolor=(255,255,255,255),unsetcolor=(0,0,0,0)).convert_alpha()
        overlay=texture.copy()
        overlay.blit(mask,(0,0),special_flags=pg.BLEND_RGBA_MULT)
        overlay.set_alpha(opacity)
        surf.blit(overlay,(0,0))

    @staticmethod
    def _placed_building_piece(structure_id: str):
        """Present player-built shells through the same material renderer as towns."""
        materials={
            'core:wood_wall':('wall','timber'),
            'core:stone_wall':('wall','stone'),
            'core:reed_screen':('wall','wattle'),
            'core:door':('opening','wood'),
            'core:wood_floor':('floor','plank'),
            'core:wood_roof':('roof','wood'),
            'core:stone_roof':('roof','stone'),
        }
        choice=materials.get(structure_id)
        if choice is None:return None
        category,material=choice
        return SimpleNamespace(id=structure_id,category=category,material=material,tags=())

    def _placed_building_bits(self,key,structure_by,piece):
        x,y,z=key;bits=0
        for bit,dx,dy in ((1,0,-1),(2,1,0),(4,0,1),(8,-1,0)):
            other=structure_by.get((x+dx,y+dy,z))
            neighbor=self._placed_building_piece(other.structure_id) if other else None
            if neighbor is None:continue
            if piece.category in {'wall','opening'}:
                connected=neighbor.category in {'wall','opening'}
            else:
                connected=(neighbor.category==piece.category)
            if connected:bits|=bit
        return bits

    def _settlement_ground_surface(self,piece,size:int,bits:int=0):
        """Connected floor/road material with bevels only on exposed boundaries."""
        if piece is None:return None
        key=('settlement-ground-v4',str(getattr(piece,'id','')),int(size),int(bits))
        cached=self._sprite_cache.get(key)
        if cached is not None:return cached
        pg=self.pg;cat=str(getattr(piece,'category',''));mat=str(getattr(piece,'material',''));tags=set(getattr(piece,'tags',()) or ())
        base,hi,lo=self._settlement_palette(piece);surf=pg.Surface((size,size),pg.SRCALPHA)
        if cat=='road':
            pid=str(getattr(piece,'id',''))
            span=(.48 if 'footpath' in pid else .56 if 'alley' in pid else
                  .84 if 'cart_road' in pid or 'market_square' in tags else
                  .78 if 'stone' in mat or 'cobble_road' in tags else .66)
            width=min(size,max(5,int(size*span)));half=width//2;mid=size//2
            shadow=pg.Surface((size,size),pg.SRCALPHA)
            pg.draw.circle(shadow,(*lo,95),(mid+1,mid+1),half+1)
            for bit,rect in (
                (1,(mid-half+1,0,width,mid+2)),(2,(mid,mid-half+1,size-mid,width)),
                (4,(mid-half+1,mid,width,size-mid)),(8,(0,mid-half+1,mid+2,width)),
            ):
                if bits&bit:pg.draw.rect(shadow,(*lo,95),rect)
            surf.blit(shadow,(0,0))
            pg.draw.circle(surf,(*base,242),(mid,mid),half)
            if bits&1:pg.draw.rect(surf,(*base,242),(mid-half,0,width,mid+1))
            if bits&2:pg.draw.rect(surf,(*base,242),(mid,mid-half,size-mid,width))
            if bits&4:pg.draw.rect(surf,(*base,242),(mid-half,mid,width,size-mid))
            if bits&8:pg.draw.rect(surf,(*base,242),(0,mid-half,mid+1,width))
            if bits==0:pg.draw.rect(surf,(*base,242),(mid-half,0,width,size))
            if 'stone' in mat or 'cobble_road' in tags or 'market_square' in tags:
                step=max(5,size//4)
                for y in range(2,size,step):
                    off=step//2 if (y//step)%2 else 0
                    for x in range(-off,size,step):
                        sx=max(0,min(size-1,x+step//2));sy=max(0,min(size-1,y+step//2))
                        if surf.get_at((sx,sy))[3]:pg.draw.rect(surf,(*lo,135),(x,y,step,step),1)
            elif 'wood' in mat or 'plank_road' in tags or 'dock_walk' in tags:
                step=max(4,size//6)
                for y in range(step//2,size,step):
                    pg.draw.line(surf,(*lo,130),(0,y),(size-1,y),1)
                    if y+1<size:pg.draw.line(surf,(*hi,50),(0,y+1),(size-1,y+1),1)
            else:
                for i in range(max(7,size//2)):
                    x=(i*17+7)%size;y=(i*29+11)%size
                    if surf.get_at((x,y))[3]:pg.draw.circle(surf,(*hi,90),(x,y),1)
        elif cat=='floor' or str(getattr(piece,'layer',''))=='ground':
            surf.fill((*base,255))
            authored=self._settlement_piece_sprite_path(piece)
            if authored is not None:
                tex=self._load_terrain_sprite(authored,size)
                if tex is not None:
                    tex=tex.copy();tex.set_alpha(58);surf.blit(tex,(0,0))
            if 'stone' in mat:
                step=max(6,size//4)
                for y in range(0,size,step):
                    off=step//2 if (y//step)%2 else 0
                    pg.draw.line(surf,(*lo,100),(0,y),(size-1,y),1)
                    for x in range(-off,size,step):
                        pg.draw.line(surf,(*lo,90),(x,y),(x,min(size-1,y+step)),1)
                for i in range(max(3,size//9)):
                    x=(i*13+5)%size;y=(i*19+3)%size;pg.draw.circle(surf,(*hi,35),(x,y),1)
            elif 'wood' in mat or 'plank' in mat:
                board=max(4,size//6)
                for y in range(board,size,board):
                    pg.draw.line(surf,(*lo,105),(0,y),(size-1,y),1)
                    if y+1<size:pg.draw.line(surf,(*hi,38),(0,y+1),(size-1,y+1),1)
                for row,y in enumerate(range(0,size,board)):
                    joint=(row*11+size//3)%max(2,size)
                    pg.draw.line(surf,(*lo,90),(joint,y),(joint,min(size-1,y+board)),1)
            elif 'clay' in mat:
                step=max(6,size//4)
                for y in range(step,size,step):pg.draw.line(surf,(*lo,95),(1,y),(size-2,y),1)
            else:
                for i in range(max(8,size//2)):
                    x=(i*13+3)%size;y=(i*19+5)%size;pg.draw.circle(surf,(*hi,55),(x,y),1)
            # Thin bevels mark only the actual room perimeter; connected floor
            # cells share one plane and never receive a per-tile frame.
            edge=max(1,size//18)
            if not bits&1:
                pg.draw.rect(surf,(*lo,120),(0,0,size,edge));pg.draw.line(surf,(*hi,55),(0,edge),(size-1,edge),1)
            if not bits&2:pg.draw.rect(surf,(*lo,115),(size-edge,0,edge,size))
            if not bits&4:pg.draw.rect(surf,(*lo,150),(0,size-edge,size,edge))
            if not bits&8:
                pg.draw.rect(surf,(*lo,105),(0,0,edge,size));pg.draw.line(surf,(*hi,45),(edge,0),(edge,size-1),1)
        else:return None
        self._settlement_material_overlay(surf,piece,size,215 if cat=='road' else 225)
        self._sprite_cache[key]=surf;return surf

    def _settlement_wall_surface(self,piece,size:int,bits:int,role:str='wall'):
        """Connected top-down wall/door art with material depth and clean joins."""
        from worldseed.ui.fence_view import is_fence, fence_surface
        if is_fence(piece):
            return fence_surface(self,piece,size,bits)
        key=('settlement-wall-v4',str(getattr(piece,'id','')),int(size),int(bits),str(role))
        cached=self._sprite_cache.get(key)
        if cached is not None:return cached
        pg=self.pg;base,hi,lo=self._settlement_palette(piece);surf=pg.Surface((size,size),pg.SRCALPHA)
        mat=str(getattr(piece,'material',''));mid=size//2;th=max(4,size//4);half=th//2
        door=role in {'entrance','interior_door'} or str(getattr(piece,'category',''))=='opening'
        horizontal=(bool(bits&2)+bool(bits&8))>=(bool(bits&1)+bool(bits&4))
        def wall_rect(rect):
            x,y,w,h=rect
            pg.draw.rect(surf,(*lo,125),(x+1,y+2,w,h),border_radius=max(1,th//4))
            pg.draw.rect(surf,(*base,255),rect,border_radius=max(1,th//5))
            if w>=h:
                pg.draw.line(surf,(*hi,205),(x,max(0,y)),(min(size-1,x+w-1),max(0,y)),1)
                pg.draw.line(surf,(*lo,205),(x,min(size-1,y+h-1)),(min(size-1,x+w-1),min(size-1,y+h-1)),1)
            else:
                pg.draw.line(surf,(*hi,205),(max(0,x),y),(max(0,x),min(size-1,y+h-1)),1)
                pg.draw.line(surf,(*lo,205),(min(size-1,x+w-1),y),(min(size-1,x+w-1),min(size-1,y+h-1)),1)
        if door:
            gap=max(th+2,int(size*.38));g0=mid-gap//2;g1=mid+gap//2
            if horizontal:
                wall_rect((0,mid-half,max(1,g0),th));wall_rect((g1,mid-half,max(1,size-g1),th))
                pg.draw.rect(surf,(*lo,255),(g0-1,mid-half-1,3,th+2))
                pg.draw.rect(surf,(*hi,255),(g1-1,mid-half-1,3,th+2))
                leaf=pg.Rect(g0+2,mid-half+2,max(3,gap-5),max(3,th-4))
                pg.draw.rect(surf,(*base,245),leaf,border_radius=1);pg.draw.rect(surf,(*lo,230),leaf,1,border_radius=1)
                pg.draw.circle(surf,(*hi,255),(max(leaf.left+1,leaf.right-3),leaf.centery),1)
            else:
                wall_rect((mid-half,0,th,max(1,g0)));wall_rect((mid-half,g1,th,max(1,size-g1)))
                pg.draw.rect(surf,(*lo,255),(mid-half-1,g0-1,th+2,3))
                pg.draw.rect(surf,(*hi,255),(mid-half-1,g1-1,th+2,3))
                leaf=pg.Rect(mid-half+2,g0+2,max(3,th-4),max(3,gap-5))
                pg.draw.rect(surf,(*base,245),leaf,border_radius=1);pg.draw.rect(surf,(*lo,230),leaf,1,border_radius=1)
                pg.draw.circle(surf,(*hi,255),(leaf.centerx,max(leaf.top+1,leaf.bottom-3)),1)
        else:
            wall_rect((mid-half,mid-half,th,th))
            if bits&1:wall_rect((mid-half,0,th,mid+1))
            if bits&2:wall_rect((mid,mid-half,size-mid,th))
            if bits&4:wall_rect((mid-half,mid,th,size-mid))
            if bits&8:wall_rect((0,mid-half,mid+1,th))
            if bits==0:wall_rect((mid-half,size//7,th,size-2*(size//7)))
            # Junction cap hides branch overlap and gives corners/posts a
            # deliberate architectural read instead of a chunky tile center.
            if bin(bits).count('1')!=2 or ((bits&1 or bits&4) and (bits&2 or bits&8)):
                cap=max(th+1,int(th*1.15));cr=pg.Rect(mid-cap//2,mid-cap//2,cap,cap)
                pg.draw.rect(surf,(*base,255),cr,border_radius=max(1,cap//5));pg.draw.rect(surf,(*hi,185),cr,1,border_radius=max(1,cap//5))
            if 'stone' in mat:
                step=max(4,size//6)
                for x in range(step//2,size,step):
                    if surf.get_at((x,mid))[3]:pg.draw.line(surf,(*lo,75),(x,mid-half),(x,mid+half),1)
            else:
                grain_y=max(0,mid-half+2)
                if horizontal or bits in (2,8,10):
                    pg.draw.line(surf,(*lo,65),(1,grain_y),(size-2,grain_y),1)
                else:
                    grain_x=max(0,mid-half+2);pg.draw.line(surf,(*lo,65),(grain_x,1),(grain_x,size-2),1)
        self._settlement_material_overlay(surf,piece,size,205 if door else 180)
        self._sprite_cache[key]=surf;return surf

    def _settlement_roof_bits(self,key,cell,settlement_by):
        wx,wy,wz=key;bits=0
        if not cell.structure_id or not cell.roof_piece_id:return 0
        for bit,dx,dy in ((1,0,-1),(2,1,0),(4,0,1),(8,-1,0)):
            other=settlement_by.get((wx+dx,wy+dy,wz))
            if other is not None and other.structure_id==cell.structure_id and other.roof_piece_id:
                bits|=bit
        return bits

    def _settlement_roof_surface(self,piece,size:int,bits:int):
        """Continuous roof field: shared edges disappear; eaves remain visible."""
        if piece is None:return None
        key=('settlement-roof-v2',str(getattr(piece,'id','')),int(size),int(bits))
        cached=self._sprite_cache.get(key)
        if cached is not None:return cached
        pg=self.pg;base,hi,lo=self._settlement_palette(piece);mat=str(getattr(piece,'material',''))
        surf=pg.Surface((size,size),pg.SRCALPHA);surf.fill((*base,255))
        if any(token in mat for token in ('stone','slate','clay')):
            row=max(4,size//6)
            for y in range(row,size,row):
                pg.draw.line(surf,(*lo,110),(0,y),(size-1,y),1)
                off=(row//2) if (y//row)%2 else 0
                for x in range(off,size,row):
                    pg.draw.line(surf,(*lo,80),(x,max(0,y-row)),(x,y),1)
        else:
            row=max(3,size//7)
            for y in range(row,size,row):
                pg.draw.line(surf,(*lo,105),(0,y),(size-1,y),1)
                if y+1<size:pg.draw.line(surf,(*hi,40),(0,y+1),(size-1,y+1),1)
            for i in range(max(3,size//9)):
                x=(i*17+5)%size;pg.draw.line(surf,(*hi,35),(x,2),(x,min(size-3,2+size//3)),1)
        edge=max(2,size//10)
        # Connected roof cells are a single visual mass. Only the outside
        # perimeter receives eaves/shadow, removing the former brown tile grid.
        if not bits&1:
            pg.draw.rect(surf,(*hi,115),(0,0,size,max(1,edge//2)))
            pg.draw.rect(surf,(*lo,120),(0,max(1,edge//2),size,1))
        if not bits&2:pg.draw.rect(surf,(*lo,120),(size-edge,0,edge,size))
        if not bits&4:
            pg.draw.rect(surf,(*lo,190),(0,size-edge,size,edge))
            pg.draw.line(surf,(25,25,23,120),(0,size-1),(size-1,size-1),1)
        if not bits&8:pg.draw.rect(surf,(*lo,100),(0,0,edge,size))
        self._settlement_material_overlay(surf,piece,size,225)
        self._sprite_cache[key]=surf;return surf

    def _draw_settlement_yard_piece(self,piece,rect)->bool:
        """Draw authored profession-yard props without requiring bitmap assets."""
        if piece is None:return False
        tags=set(getattr(piece,'tags',()) or ());pid=str(getattr(piece,'id',''))
        pg=self.pg;size=rect.width;cx=rect.centerx;bottom=rect.bottom
        if 'clutter' in tags:
            # Small passable overlays: they communicate occupancy and profession
            # without claiming an entire collision cell.
            wood=(126,89,52);wood_hi=(174,132,82);dark=(65,55,46)
            fiber=(177,151,102);cloth=(132,112,151);clay=(167,102,72)
            metal=(101,106,108);stone=(132,132,126);green=(104,139,84)
            pad=max(3,size//7);base_y=rect.bottom-pad
            if {'flour_sacks','yarn','laundry','fish_basket'} & tags:
                for i,(dx,dy) in enumerate(((-5,1),(4,0),(0,-5))):
                    rr=pg.Rect(cx+dx-size//8,base_y+dy-size//4,size//4,size//4)
                    pg.draw.ellipse(self.screen,fiber,rr);pg.draw.ellipse(self.screen,dark,rr,1)
            elif {'tool_rack','mason_tools','hooks','net_rack','pottery_shelf','bread_rack','bottles'} & tags:
                pg.draw.line(self.screen,wood,(rect.left+pad,rect.top+pad),(rect.left+pad,base_y),2)
                pg.draw.line(self.screen,wood,(rect.right-pad,rect.top+pad),(rect.right-pad,base_y),2)
                for yy in (rect.top+size//3,rect.top+2*size//3):
                    pg.draw.line(self.screen,wood_hi,(rect.left+pad,yy),(rect.right-pad,yy),2)
                col=metal if {'tool_rack','mason_tools','hooks'} & tags else (green if 'bottles' in tags else fiber)
                for i in range(3):pg.draw.circle(self.screen,col,(rect.left+pad+4+i*max(4,size//5),rect.centery),max(1,size//14))
            elif {'metal_scrap','wood_offcuts','wood_shavings','stone_chips','hearth_wood'} & tags:
                col=metal if 'metal_scrap' in tags else (stone if 'stone_chips' in tags else wood)
                for i in range(7):
                    x=rect.left+pad+(i*11)%max(4,size-2*pad);y=base_y-(i*7)%max(5,size//3)
                    pg.draw.line(self.screen,col,(x,y),(min(rect.right-pad,x+max(2,size//6)),max(rect.top+pad,y-2)),max(1,size//16))
            elif {'cloth_roll','hide_stack'} & tags:
                col=cloth if 'cloth_roll' in tags else (137,94,67)
                for i in range(3):
                    rr=pg.Rect(rect.left+pad+i*max(3,size//7),base_y-size//3+i*2,size//3,size//7)
                    pg.draw.ellipse(self.screen,col,rr);pg.draw.ellipse(self.screen,dark,rr,1)
            elif {'clay_jars','crockery'} & tags:
                for i in range(3):
                    x=rect.left+pad+4+i*max(4,size//5);rr=pg.Rect(x,base_y-size//4-(i%2)*3,max(4,size//6),max(6,size//4))
                    pg.draw.ellipse(self.screen,clay,rr);pg.draw.ellipse(self.screen,dark,rr,1)
            elif {'kegs','buckets','bark_tub'} & tags:
                for i in range(2):
                    rr=pg.Rect(cx-size//4+i*size//5,base_y-size//3-i*2,size//3,size//3)
                    pg.draw.ellipse(self.screen,wood,rr);pg.draw.ellipse(self.screen,dark,rr,1)
                    pg.draw.line(self.screen,metal,(rr.left+2,rr.centery),(rr.right-2,rr.centery),1)
            elif 'herbs' in tags:
                for i in range(4):
                    x=rect.left+pad+i*max(3,size//6);pg.draw.line(self.screen,green,(x,rect.top+pad),(x+2,base_y-size//8),1)
                    pg.draw.ellipse(self.screen,green,(x-2,rect.centery,6,3))
            elif 'cutting_board' in tags:
                rr=pg.Rect(rect.left+pad,rect.centery-size//10,size-2*pad,size//4);pg.draw.rect(self.screen,wood,rr,border_radius=2);pg.draw.rect(self.screen,wood_hi,rr,1,border_radius=2)
            elif 'pantry' in tags:
                rr=pg.Rect(rect.left+pad,base_y-size//3,size-2*pad,size//3);pg.draw.rect(self.screen,wood,rr);pg.draw.rect(self.screen,dark,rr,1);pg.draw.line(self.screen,wood_hi,(rr.left,rr.top),(rr.right,rr.bottom),1)
            else:
                pg.draw.circle(self.screen,fiber,(cx,rect.centery),max(3,size//6));pg.draw.circle(self.screen,dark,(cx,rect.centery),max(3,size//6),1)
            return True
        if not ({'yard','trade_sign','well','woodpile','ore_pile','coal_bin','haystack','grain_sacks','barrel','smoke_rack','chopping_block'} & tags):
            return False
        wood=(126,89,52);wood_hi=(164,122,73);wood_lo=(77,51,31)
        stone=(118,119,114);stone_hi=(158,158,150);stone_lo=(69,71,69)
        straw=(181,151,72);straw_hi=(220,190,104);straw_lo=(111,86,42)
        iron=(91,96,101);coal=(43,45,47);ore=(135,112,91)
        shadow=(20,22,21,95)
        pad=max(2,size//8)
        if 'fence' in tags:
            y=rect.centery+size//7
            if 'gate' in tags:
                pg.draw.line(self.screen,wood_lo,(rect.left+pad,y),(rect.right-pad,y),max(2,size//10))
                pg.draw.line(self.screen,wood_hi,(rect.left+pad+2,y-2),(rect.right-pad-2,y-2),1)
                for x in (rect.left+pad,rect.right-pad):
                    pg.draw.line(self.screen,wood_lo,(x,rect.top+pad),(x,bottom-pad),max(2,size//9))
                pg.draw.line(self.screen,wood,(rect.left+pad+2,bottom-pad-2),(rect.right-pad-2,rect.top+pad+2),max(1,size//14))
            else:
                for x in (rect.left+pad,rect.right-pad):
                    pg.draw.line(self.screen,wood_lo,(x,rect.top+pad),(x,bottom-pad),max(2,size//9))
                    pg.draw.line(self.screen,wood_hi,(x-1,rect.top+pad),(x-1,bottom-pad-2),1)
                for off in (-size//9,size//9):
                    pg.draw.line(self.screen,wood,(rect.left+pad,y+off),(rect.right-pad,y+off),max(2,size//11))
            return True
        if 'trade_sign' in tags:
            post_x=rect.left+size//3
            pg.draw.line(self.screen,wood_lo,(post_x,rect.top+pad),(post_x,bottom-pad),max(2,size//9))
            board=pg.Rect(post_x,rect.top+pad,size//2,max(5,size//4))
            pg.draw.rect(self.screen,wood_lo,board.move(1,2),border_radius=2)
            pg.draw.rect(self.screen,wood,board,border_radius=2);pg.draw.rect(self.screen,wood_hi,board,1,border_radius=2)
            pg.draw.circle(self.screen,iron,(board.centerx,board.centery),max(1,size//16),1)
            return True
        if 'well' in tags:
            base=pg.Rect(rect.left+pad,rect.centery-size//8,size-2*pad,size//3)
            pg.draw.ellipse(self.screen,shadow,base.move(1,3))
            pg.draw.ellipse(self.screen,stone_lo,base);pg.draw.ellipse(self.screen,stone,base.inflate(-2,-2))
            inner=base.inflate(-max(4,size//4),-max(3,size//7))
            pg.draw.ellipse(self.screen,(38,61,66),inner)
            for x in (rect.left+pad+2,rect.right-pad-2):
                pg.draw.line(self.screen,wood_lo,(x,rect.top+pad),(x,rect.centery),max(2,size//11))
            pg.draw.line(self.screen,wood,(rect.left+pad,rect.top+pad),(rect.right-pad,rect.top+pad),max(2,size//12))
            return True
        if 'woodpile' in tags:
            y0=bottom-pad
            for row in range(3):
                count=4-row;yy=y0-row*max(3,size//7)
                for i in range(count):
                    x=rect.left+pad+i*max(4,(size-2*pad)//4)+row*2
                    r=max(2,size//10)
                    pg.draw.circle(self.screen,wood_lo,(x+r,yy-r),r)
                    pg.draw.circle(self.screen,wood_hi,(x+r,yy-r),max(1,r-1))
                    pg.draw.circle(self.screen,wood,(x+r,yy-r),max(1,r-2))
            return True
        if 'chopping_block' in tags:
            stump=pg.Rect(cx-size//5,rect.centery-size//8,size*2//5,size//3)
            pg.draw.ellipse(self.screen,wood_lo,(stump.left,stump.top-3,stump.width,7))
            pg.draw.rect(self.screen,wood,stump);pg.draw.ellipse(self.screen,wood_hi,(stump.left,stump.top-3,stump.width,7))
            pg.draw.line(self.screen,wood_lo,(cx,stump.top-1),(cx+size//7,stump.top+size//9),1)
            return True
        if 'ore_pile' in tags:
            pts=[(cx-size//3,bottom-pad),(cx-size//4,rect.centery),(cx,rect.centery-size//6),(cx+size//3,bottom-pad)]
            pg.draw.polygon(self.screen,stone_lo,pts)
            for dx,dy,col in [(-7,4,ore),(2,7,stone_hi),(7,1,iron),(-1,-2,ore)]:
                pg.draw.circle(self.screen,col,(cx+dx*size//28,rect.centery+dy*size//28),max(2,size//11))
            return True
        if 'coal_bin' in tags:
            box=pg.Rect(rect.left+pad,rect.centery-size//8,size-2*pad,size//3)
            pg.draw.rect(self.screen,wood_lo,box);pg.draw.rect(self.screen,wood,box.inflate(-2,-2))
            for i in range(7):
                x=box.left+3+(i*11)%(max(4,box.width-6));y=box.top+2+(i*7)%(max(3,box.height//2))
                pg.draw.circle(self.screen,coal,(x,y),max(1,size//16))
            return True
        if 'haystack' in tags:
            mound=pg.Rect(rect.left+pad,rect.centery-size//5,size-2*pad,size//2)
            pg.draw.ellipse(self.screen,straw_lo,mound.move(1,2));pg.draw.ellipse(self.screen,straw,mound)
            for i in range(8):
                x=mound.left+2+(i*13)%(max(3,mound.width-4))
                pg.draw.line(self.screen,straw_hi,(x,mound.top+3),(min(mound.right-1,x+size//8),mound.bottom-3),1)
            return True
        if 'grain_sacks' in tags:
            for i,(dx,dy) in enumerate(((0,0),(size//5,2),(-size//6,3))):
                sack=pg.Rect(cx-size//7+dx,rect.centery-size//10+dy,size//4,size//3)
                pg.draw.ellipse(self.screen,straw_lo,sack);pg.draw.ellipse(self.screen,(174,145,96),sack.inflate(-2,-2))
                pg.draw.line(self.screen,straw_hi,(sack.left+2,sack.top+3),(sack.right-3,sack.top+3),1)
            return True
        if 'barrel' in tags:
            barrel=pg.Rect(cx-size//5,rect.centery-size//5,size*2//5,size//2)
            pg.draw.ellipse(self.screen,wood_lo,barrel);pg.draw.ellipse(self.screen,wood,barrel.inflate(-2,-1))
            for y in (barrel.top+size//8,barrel.bottom-size//8):
                pg.draw.line(self.screen,iron,(barrel.left+2,y),(barrel.right-2,y),max(1,size//18))
            return True
        if 'smoke_rack' in tags:
            left=rect.left+pad;right=rect.right-pad;top=rect.top+pad;low=bottom-pad
            pg.draw.line(self.screen,wood_lo,(left,low),(left+size//7,top),max(2,size//11))
            pg.draw.line(self.screen,wood_lo,(right,low),(right-size//7,top),max(2,size//11))
            pg.draw.line(self.screen,wood,(left+size//7,top),(right-size//7,top),max(2,size//12))
            for x in (cx-size//6,cx,cx+size//6):
                pg.draw.line(self.screen,wood_hi,(x,top),(x,rect.centery),1)
                pg.draw.ellipse(self.screen,(126,65,48),(x-size//12,rect.centery-size//14,size//6,size//4))
            return True
        return False

    def _draw_settlement_piece(self,piece,rect,*,roof:bool=False,fixture:bool=False):
        if piece is None:return
        if not roof and self._draw_settlement_yard_piece(piece,rect):return
        path=self._settlement_piece_sprite_path(piece)
        if path is not None:
            if roof:
                surf=self._load_terrain_sprite(path,rect.width)
                if surf:self.screen.blit(surf,rect.topleft)
            else:self._draw_sprite_bottom(path,rect,.95 if fixture else 1.05,width_mult=.9 if fixture else .95)
            return
        pg=self.pg;base,hi,lo=self._settlement_palette(piece);pad=max(3,rect.width//5);body=rect.inflate(-pad*2,-pad*2)
        pg.draw.rect(self.screen,(23,26,25),body.move(1,2),border_radius=max(1,rect.width//10));pg.draw.rect(self.screen,base,body,border_radius=max(1,rect.width//10));pg.draw.rect(self.screen,hi,body.inflate(-max(1,rect.width//8),-max(1,rect.width//8)),1,border_radius=max(1,rect.width//12));pg.draw.rect(self.screen,lo,body,1,border_radius=max(1,rect.width//10))

    def _resource_visual(self, feature_id: str, x: int, y: int, z: int):
        """Resolve a deterministic visual for a generated resource cell."""
        style=self._visuals.resource_style(feature_id)
        atlas=self._visuals.resource_atlas_path(feature_id)
        if atlas is not None:
            columns=max(1,int(style.get('atlas_columns',style.get('variants',1))))
            variants=max(1,min(columns,int(style.get('variants',columns))))
            variant=self._stable_variant(f"{feature_id}:{x}:{y}:{z}",variants)
            return ('atlas',atlas,variant,int(style.get('atlas_row',0)),int(style.get('atlas_frame',128)))
        ref=self._visuals.ref('resources',feature_id)
        variant=self._stable_variant(f"{feature_id}:{x}:{y}:{z}",len(ref.paths)) if ref.paths else 0
        return self._visuals.resolve(ref,variant)

    def _draw_resource_feature(self, feature, visual, rect):
        style = self._visuals.resource_style(feature.feature_id)
        growth = 0.65 if feature.stage == 'sapling' and style else 1.0
        height=float(style.get('height', 1.7))*growth
        width=float(style.get('width', 1.35))*growth
        alpha=190 if feature.stage == 'sapling' else 255
        smooth=bool(style.get('smooth', False))
        if isinstance(visual,tuple) and visual and visual[0]=='atlas':
            _,path,column,row,frame_size=visual
            surf=self._load_atlas_frame(path,column,row,frame_size,int(rect.width*width),int(rect.height*height),smooth=smooth)
            if surf is None:return
            if alpha!=255:
                surf=surf.copy();surf.set_alpha(alpha)
            self.screen.blit(surf,(rect.centerx-surf.get_width()//2,rect.bottom-surf.get_height()))
            return
        self._draw_sprite_bottom(visual,rect,height,alpha,width_mult=width,smooth=smooth)

    def _terrain_transition_mask(self, direction: str, tile_px: int, center_id: str, neighbor_id: str):
        """Feather mask for local terrain autotiling in all 8 directions."""
        base_depth, max_alpha = transition_profile(center_id, neighbor_id)
        depth=max(3,min(int(tile_px*(base_depth/28.0)),max(5,tile_px//2)))
        key=(direction,tile_px,depth,max_alpha); cached=self._terrain_transition_masks.get(key)
        if cached is not None:return cached
        pg=self.pg; mask=pg.Surface((tile_px,tile_px),pg.SRCALPHA)
        if direction in ('north','south','west','east'):
            for i in range(depth):
                alpha=max(0,int(max_alpha*(depth-i)/depth)); color=(255,255,255,alpha)
                if direction=='north': pg.draw.line(mask,color,(0,i),(tile_px-1,i))
                elif direction=='south':
                    y=tile_px-1-i; pg.draw.line(mask,color,(0,y),(tile_px-1,y))
                elif direction=='west': pg.draw.line(mask,color,(i,0),(i,tile_px-1))
                else:
                    x=tile_px-1-i; pg.draw.line(mask,color,(x,0),(x,tile_px-1))
        else:
            radius=max(4,min(depth+2,max(6,tile_px//2)))
            corner_alpha=max(56,int(max_alpha*0.72))
            ax=0 if 'west' in direction else tile_px-1
            ay=0 if 'north' in direction else tile_px-1
            for y in range(tile_px):
                for x in range(tile_px):
                    dx=abs(x-ax);dy=abs(y-ay);dist=(dx*dx+dy*dy)**0.5
                    if dist<=radius:
                        alpha=max(0,int((1.0-dist/radius)*corner_alpha))
                        if alpha:mask.set_at((x,y),(255,255,255,alpha))
        self._terrain_transition_masks[key]=mask
        return mask

    def _material_phase(self, terrain_id, x, y):
        styles=self._visuals.manifest.get('terrain_materials',{}) if self._visuals else {}
        span=max(1,min(16,int(styles.get(terrain_id,{}).get('span_cells',1))))
        return (span,x%span,y%span) if span>1 else (1,0,0)

    def _ground_material(self, terrain_id, path, size, x, y):
        span,cx,cy=self._material_phase(terrain_id,x,y)
        if span==1:return self._load_terrain_sprite(path,size)
        key=('ground',str(path),size,span,cx,cy)
        cached=self._sprite_cache.get(key)
        if cached is not None:return cached
        material_key=('continuous-ground',str(path),size,span)
        source=self._sprite_cache.get(material_key)
        if source is None:
            # Crossfade an overlapping border once, retaining organic detail
            # without mirror symmetry or repeating a whole image in every cell.
            full=self._load_terrain_sprite(path,size*(span+2))
            if full is None:return None
            extent=size*span;overlap=size*2
            source=full.copy()
            for vertical in (False,True):
                strip=source.subsurface((0,extent,extent,overlap) if vertical else
                                        (extent,0,overlap,source.get_height())).copy()
                mask=self.pg.Surface(strip.get_size(),self.pg.SRCALPHA)
                for i in range(overlap):
                    alpha=255*(overlap-i)//overlap
                    if vertical:self.pg.draw.line(mask,(255,255,255,alpha),(0,i),(strip.get_width()-1,i))
                    else:self.pg.draw.line(mask,(255,255,255,alpha),(i,0),(i,strip.get_height()-1))
                strip.blit(mask,(0,0),special_flags=self.pg.BLEND_RGBA_MULT)
                source.blit(strip,(0,0))
            source=source.subsurface((0,0,extent,extent)).copy()
            self._sprite_cache[material_key]=source
        tile=source.subsurface((cx*size,cy*size,size,size)).copy()
        self._sprite_cache[key]=tile
        return tile

    def _terrain_surface(self, center_id: str, center_path: Path | None, neighbor_ids: dict[str,str|None], neighbor_paths: dict[str,Path|None], tile_px: int, *, world_x: int=0, world_y: int=0):
        """Compose a cached natural-terrain tile without altering world data."""
        if center_id == 'core:cave_mouth':
            # v7 cave art is an overlay rather than a baked square of ground.
            # Pick the most common neighboring blendable land material as its
            # contextual floor, then place the recessed rock opening above it.
            counts:dict[str,int]={}
            for nid in neighbor_ids.values():
                if is_blendable_land(nid):counts[nid]=counts.get(nid,0)+1
            ground_id=max(counts,key=lambda k:(counts[k],k)) if counts else None
            ground_path=next((neighbor_paths[d] for d,nid in neighbor_ids.items() if nid==ground_id and neighbor_paths.get(d)),None)
            key=('cave-mouth',str(center_path) if center_path else '',str(ground_path) if ground_path else '',tile_px)
            cached=self._terrain_transition_cache.get(key)
            if cached is not None:return cached
            overlay=self._load_terrain_sprite(center_path,tile_px)
            ground=self._load_terrain_sprite(ground_path,tile_px) if ground_path else None
            if overlay is None:return ground
            composed=ground.copy() if ground is not None else self.pg.Surface((tile_px,tile_px),self.pg.SRCALPHA)
            composed.blit(overlay,(0,0));self._terrain_transition_cache[key]=composed
            return composed
        signature=transition_signature(center_id,neighbor_ids)
        path_signature=tuple((direction, str(neighbor_paths.get(direction)) if neighbor_id is not None else None)
                             for direction, neighbor_id in signature)
        material_phase=self._material_phase(center_id,world_x,world_y)
        neighbor_phases=tuple(self._material_phase(neighbor_ids.get(d),world_x+dx,world_y+dy) for d,dx,dy in DIRECTIONS_8)
        key=(str(center_path) if center_path else '',signature,path_signature,tile_px,material_phase,neighbor_phases)
        cached=self._terrain_transition_cache.get(key)
        if cached is not None:return cached
        base=self._ground_material(center_id,center_path,tile_px,world_x,world_y)
        if base is None:return None
        if not any(value for _,value in signature):
            self._terrain_transition_cache[key]=base
            return base
        composed=base.copy()
        for direction,neighbor_id in signature:
            if neighbor_id is None:continue
            dx,dy=next((dx,dy) for d,dx,dy in DIRECTIONS_8 if d==direction)
            overlay=self._ground_material(neighbor_id,neighbor_paths.get(direction),tile_px,world_x+dx,world_y+dy)
            if overlay is None:continue
            masked=overlay.copy()
            masked.blit(self._terrain_transition_mask(direction,tile_px,center_id,neighbor_id),(0,0),special_flags=self.pg.BLEND_RGBA_MULT)
            composed.blit(masked,(0,0))
        self._terrain_transition_cache[key]=composed
        if len(self._terrain_transition_cache)>2048:
            self._terrain_transition_cache.clear()
        return composed

    def _edge_overlay_surface(self, kind: str, direction: str, tile_px: int):
        key=('edge',kind,direction,tile_px)
        cached=self._overlay_cache.get(key)
        if cached is not None:return cached
        pg=self.pg
        surf=pg.Surface((tile_px,tile_px),pg.SRCALPHA)
        if direction in ('north','south','west','east'):
            band=max(3,min(tile_px//3, 8 if 'shore' in kind or 'riverbank' in kind else 7))
            for i in range(band):
                t=i/max(1,band-1)
                if kind=='water_ocean_shore':
                    base=(206,223,216,max(12,int(72*(1-t))))
                elif kind=='water_estuary':
                    base=(154,171,131,max(10,int(58*(1-t))))
                elif kind=='water_river_edge':
                    base=(194,214,199,max(8,int(50*(1-t))))
                elif kind=='land_beach':
                    base=(169,152,108,max(10,int(74*(1-t))))
                elif kind=='land_rock_shore':
                    base=(78,87,95,max(10,int(60*(1-t))))
                elif kind=='land_shore':
                    base=(128,119,84,max(10,int(52*(1-t))))
                elif kind=='land_riverbank_bare':
                    base=(118,94,67,max(10,int(60*(1-t))))
                else:  # land_riverbank_soft
                    base=(98,104,70,max(10,int(54*(1-t))))
                if direction=='north':
                    y=i; pg.draw.line(surf,base,(0,y),(tile_px-1,y))
                elif direction=='south':
                    y=tile_px-1-i; pg.draw.line(surf,base,(0,y),(tile_px-1,y))
                elif direction=='west':
                    x=i; pg.draw.line(surf,base,(x,0),(x,tile_px-1))
                else:
                    x=tile_px-1-i; pg.draw.line(surf,base,(x,0),(x,tile_px-1))
            # Decorative edge accents.
            if kind.startswith('water_'):
                wave=(239,239,231,42 if kind=='water_ocean_shore' else 26)
                fixed=band//2+1
                if direction in ('north','south'):
                    y=fixed if direction=='north' else tile_px-1-fixed
                    pts=[(x, y + (1 if (x//4)%2==0 else -1)) for x in range(0,tile_px,4)]
                    pg.draw.lines(surf,wave,False,pts,1)
                else:
                    x=fixed if direction=='west' else tile_px-1-fixed
                    pts=[(x + (1 if (y//4)%2==0 else -1), y) for y in range(0,tile_px,4)]
                    pg.draw.lines(surf,wave,False,pts,1)
        else:
            radius=max(5,min(tile_px//2,8))
            corner_alpha=40
            ax=0 if 'west' in direction else tile_px-1
            ay=0 if 'north' in direction else tile_px-1
            color=(239,239,231,corner_alpha) if kind.startswith('water_') else (110,102,74,corner_alpha)
            for y in range(tile_px):
                for x in range(tile_px):
                    dx=abs(x-ax);dy=abs(y-ay);dist=(dx*dx+dy*dy)**0.5
                    if dist<=radius:
                        alpha=max(0,int((1.0-dist/radius)*color[3]))
                        if alpha:surf.set_at((x,y),(*color[:3],alpha))
        self._overlay_cache[key]=surf
        return surf

    def _draw_hover_tooltip(self, lines: list[str], anchor_pos: tuple[int, int], bounds):
        if not lines or self.screen is None:
            return None
        pg=self.pg; th=self._theme
        pad=8
        rendered=[]; width=0
        for i,line in enumerate(lines[:8]):
            font=self.font if i==0 else self.small_font
            color=th['accent'] if i==0 else th['text']
            surf=font.render(str(line),True,color)
            rendered.append(surf); width=max(width,surf.get_width())
        height=pad*2+sum(s.get_height() for s in rendered)+max(0,len(rendered)-1)*2
        x=anchor_pos[0]+14; y=anchor_pos[1]+14
        if x+width+pad*2 > bounds.right: x=anchor_pos[0]-width-pad*2-14
        if y+height > bounds.bottom: y=bounds.bottom-height-4
        x=max(bounds.left+4,x); y=max(bounds.top+4,y)
        rect=pg.Rect(x,y,width+pad*2,height)
        pg.draw.rect(self.screen,(18,22,24),rect,border_radius=4)
        pg.draw.rect(self.screen,th['edge_hi'],rect,1,border_radius=4)
        yy=y+pad
        for surf in rendered:
            self.screen.blit(surf,(x+pad,yy)); yy+=surf.get_height()+2
        return rect

    @staticmethod
    def _stable_variant(text: str, n: int) -> int:
        h=2166136261
        for b in text.encode('utf-8'):
            h ^= b; h=(h*16777619)&0xffffffff
        return h % max(1,n)

    def _npc_sprite_path(self, npc):
        paths=self._visuals.npc_paths(getattr(npc,'sex',None))
        return paths[self._stable_variant(npc.uid or npc.name,len(paths))] if paths else None

    def _terrain_variant_index(self, terrain_id: str, x: int, y: int, z: int, count: int) -> int:
        """Choose a deterministic alternative tile for repeated natural terrain."""
        if count <= 1:return 0
        return self._stable_variant(f"{terrain_id}:{x}:{y}:{z}", count)

    def _build_base_layer(self, world, known, z: int, left: int, top: int, cols: int, rows: int, tile_px: int):
        """Return terrain base while reusing the overlapping previous view.

        The camera normally moves one tile at a time. Rebuilding every terrain
        sprite for the newly shifted viewport made a held movement key render
        hundreds of redundant cells per step. Keep one scroll state, shift its
        pixels, and resolve only the newly exposed strip plus newly discovered
        cells. No simulation state is cached here.
        """
        pg=self.pg; special_unknown=self._visuals.special('unknown')
        stable=(id(world),z,cols,rows,tile_px,getattr(world,'revision',0))
        prev=self._base_scroll_state
        surf=None;rendered_known=set();old_left=old_top=None
        can_scroll=False
        if prev is not None:
            p_stable,old_left,old_top,old_surf,old_rendered=prev
            dx=left-old_left;dy=top-old_top
            can_scroll=p_stable==stable and abs(dx)<=1 and abs(dy)<=1
            if can_scroll:
                if dx==0 and dy==0:
                    surf=old_surf;rendered_known=set(old_rendered)
                else:
                    surf=pg.Surface((cols*tile_px,rows*tile_px),pg.SRCALPHA)
                    # New viewport moving east means old pixels move west.
                    surf.blit(old_surf,(-dx*tile_px,-dy*tile_px))
        if surf is None:
            surf=pg.Surface((cols*tile_px,rows*tile_px),pg.SRCALPHA)

        unknown=self._load_sprite(special_unknown,tile_px,tile_px)
        old_right=(old_left+cols-1) if can_scroll and old_left is not None else None
        old_bottom=(old_top+rows-1) if can_scroll and old_top is not None else None
        neighbor_cache={}
        display_cache={}

        def discovered_neighbor_ids(wx:int, wy:int):
            key=(wx,wy)
            cached=neighbor_cache.get(key)
            if cached is not None:return cached
            ids={}
            for direction,ndx,ndy in DIRECTIONS_8:
                nwx,nwy=wx+ndx,wy+ndy
                if pos_key(nwx,nwy,z) not in known:continue
                ids[direction]=world.tile_at(WorldPos(nwx,nwy,z)).terrain_id
            neighbor_cache[key]=ids
            return ids

        def display_id_for(wx:int, wy:int, terrain_id:str):
            key=(wx,wy,terrain_id)
            cached=display_cache.get(key)
            if cached is not None:return cached
            value=contextual_display_id(terrain_id, discovered_neighbor_ids(wx,wy) if terrain_id=='core:water' else {})
            display_cache[key]=value
            return value

        for sy in range(rows):
            wy=top+sy
            for sx in range(cols):
                wx=left+sx;pk=pos_key(wx,wy,z);rect=pg.Rect(sx*tile_px,sy*tile_px,tile_px,tile_px)
                copied=False
                if can_scroll and old_left is not None and old_top is not None:
                    copied=(old_left<=wx<=old_right and old_top<=wy<=old_bottom)
                    if copied and pk in old_rendered:
                        # A just-discovered neighbor changes this tile's edge
                        # blend. Redraw only those seam-adjacent copied cells;
                        # the rest of the scrolled surface remains reusable.
                        transition_dirty=False
                        for _,ndx,ndy in DIRECTIONS_8:
                            npk=pos_key(wx+ndx,wy+ndy,z)
                            if npk in known and npk not in old_rendered:
                                transition_dirty=True;break
                        if not transition_dirty:rendered_known.add(pk)
                if pk not in known:
                    if not copied:
                        if unknown:surf.blit(unknown,rect.topleft)
                        else:pg.draw.rect(surf,(8,10,12),rect)
                    continue
                if pk in rendered_known:
                    continue
                tile=world.tile_at(WorldPos(wx,wy,z))
                neighbor_ids=discovered_neighbor_ids(wx,wy)
                display_id=display_id_for(wx,wy,tile.terrain_id)
                terr_ref=self._visuals.ref('terrain',display_id,tile.terrain.glyph)
                terr_path=self._visuals.resolve(
                    terr_ref,
                    self._terrain_variant_index(display_id, wx, wy, z, len(terr_ref.paths)),
                )
                neighbor_paths={}
                # Blend only already-discovered neighboring cells. This gives
                # every natural terrain N/S/E/W + corner transitions without
                # revealing or generating geography through fog of war.
                for direction,ndx,ndy in DIRECTIONS_8:
                    nwx,nwy=wx+ndx,wy+ndy
                    if pos_key(nwx,nwy,z) not in known:continue
                    ntile=world.tile_at(WorldPos(nwx,nwy,z))
                    ndisplay=display_id_for(nwx,nwy,ntile.terrain_id)
                    nref=self._visuals.ref('terrain',ndisplay,ntile.terrain.glyph)
                    neighbor_paths[direction]=self._visuals.resolve(
                        nref,
                        self._terrain_variant_index(ndisplay, nwx, nwy, z, len(nref.paths)),
                    )
                terr=self._terrain_surface(tile.terrain_id,terr_path,neighbor_ids,neighbor_paths,tile_px,world_x=wx,world_y=wy)
                if terr:surf.blit(terr,rect.topleft)
                else:pg.draw.rect(surf,(52,65,50),rect)
                for direction,kind in edge_overlay_signature(tile.terrain_id, neighbor_ids):
                    if kind:
                        surf.blit(self._edge_overlay_surface(kind,direction,tile_px), rect.topleft)
                rendered_known.add(pk)
        self._base_scroll_state=(stable,left,top,surf,rendered_known)
        return surf

    def _spatial_state_views(self, sim, left:int, top:int, right:int, bottom:int, z:int):
        """Return only state objects in viewport-adjacent spatial buckets.

        Previously every game-frame scanned every realized NPC, creature,
        structure, crop, pile and fire in the whole explored world. The cost
        therefore rose permanently as exploration materialized more regions.
        Rebuild this presentation-only index only when hourly movers/counts can
        change, then query the few chunks intersecting the viewport.
        """
        state=sim.state
        collections=(
            ('creatures',state.creatures),('npcs',state.npcs),('structures',state.structures),
            ('containers',state.containers),('crops',state.crops),('fires',state.fires),('fluids',state.fluids),
            ('ground_piles',state.ground_piles),('carcasses',state.carcasses),
            ('animal_signs',state.animal_signs),('animal_homes',state.animal_homes),
        )
        key=(id(sim),sim.clock.minute//60)+tuple(len(v) for _,v in collections)
        if key!=self._entity_spatial_cache_key or self._entity_spatial_cache is None:
            index={name:{} for name,_ in collections}
            for name,mapping in collections:
                buckets=index[name]
                for obj in mapping.values():
                    if name=='containers' and getattr(obj,'interior_space_id',''):
                        continue
                    ox=int(getattr(obj,'x',0));oy=int(getattr(obj,'y',0));oz=int(getattr(obj,'z',0))
                    buckets.setdefault((ox//32,oy//32,oz),[]).append(obj)
            self._entity_spatial_cache_key=key;self._entity_spatial_cache=index
        index=self._entity_spatial_cache
        out={name:[] for name,_ in collections}
        for cy in range(top//32,bottom//32+1):
            for cx in range(left//32,right//32+1):
                bucket=(cx,cy,z)
                for name,_ in collections:
                    out[name].extend(index[name].get(bucket,()))
        return out

    def _resource_view(self, sim, known, z:int, left:int, top:int, cols:int, rows:int):
        # Cache resource projection by absolute world cell rather than viewport.
        # A one-tile camera move therefore resolves only the new edge instead of
        # asking ResourceSystem about every visible coordinate again.
        revision=(id(sim),sim.resources.revision,sim.clock.minute//1440,
                  len(sim.state.structures),len(sim.state.containers),
                  len(sim.state.crops),len(sim.state.soils))
        out={}
        for sy in range(rows):
            wy=top+sy
            for sx in range(cols):
                wx=left+sx;pk=pos_key(wx,wy,z)
                if pk not in known:continue
                ckey=revision+(wx,wy,z)
                if ckey not in self._resource_cell_cache:
                    fv=sim.resources.feature_at(WorldPos(wx,wy,z))
                    if fv and fv.stage!='depleted':
                        visual=self._resource_visual(fv.feature_id,wx,wy,z)
                        self._resource_cell_cache[ckey]=(fv,visual)
                    else:self._resource_cell_cache[ckey]=None
                    if len(self._resource_cell_cache)>20000:
                        # Old revision/day entries are reconstructable and cheap
                        # to discard wholesale; do not let exploration grow UI
                        # cache state without bound.
                        current={k:v for k,v in self._resource_cell_cache.items() if k[:len(revision)]==revision}
                        self._resource_cell_cache=current if len(current)<16000 else {}
                cached=self._resource_cell_cache.get(ckey)
                if cached is not None:out[(wx,wy,z)]=cached
        return out

    def _hover_lines_for(self, wx:int, wy:int, pixel=None):
        ctx=self._hover_context
        if not ctx:return []
        # Full static exterior art is an object, not permission to inspect the
        # undiscovered terrain, people or goods underneath its roof pixels.
        painted_hit_testing = pixel is not None and 'shell_hit_regions' in ctx
        if painted_hit_testing:
            from worldseed.ui.exterior_view import shell_at_pointer
            hit=shell_at_pointer(ctx,pixel)
            if hit is not None:
                shell,part=hit
                lines=[str(shell.function).replace('_',' ').title()]
                if part=='door':
                    lines.append('Entrance door — right-click to interact')
                    lines.append(f'Access threshold: {shell.entrance[0]}, {shell.entrance[1]}')
                else:lines.append('Building exterior — right-click to inspect')
                return lines
        z=ctx['z']; pk=pos_key(wx,wy,z); known=ctx['known']; k=(wx,wy,z)
        # RC9's inline branch was spelled `if hpk in known`; this helper keeps
        # the same discovery-gating contract while using a neutral key name.
        if pk not in known:return ['Unexplored']
        registry=ctx['registry']; world=ctx['world']; sim=ctx['sim']
        hpos=WorldPos(wx,wy,z); htile=world.tile_at(hpos)
        lines=[htile.terrain.name,f'{wx}, {wy}, z{z}']
        site=sim.homestead.at(hpos) if hasattr(sim,'homestead') else None
        if site is not None:
            from worldseed.systems.homestead_blueprints import progress as blueprint_progress, STAGES
            amount=sum(h for h,n in blueprint_progress(site).values())
            total=sum(n for h,n in blueprint_progress(site).values())
            status='Complete' if site['stage']==4 else STAGES[site['stage']]
            return [f'Log cabin • {status}',f'Deposited {amount}/{total} materials','Right-click to open blueprint panel']
        current_getter=getattr(world,'current_at',None)
        if callable(current_getter):
            current=current_getter(hpos,prepared_only=True)
            if current is not None and getattr(current,'flowing',False):
                label='River current' if str(getattr(current,'kind','')).startswith('river') else 'Ocean current'
                lines.append(f"{label}: {current.strength_band} {current.heading}")
        if 'water' in htile.terrain.tags:
            from worldseed.systems.swimming import exposure, stroke_cost
            water=exposure(sim,hpos)
            lines.append(f'{water.mode.title()} | {water.salinity} water')
            if water.mode=='swimming':lines.append(f'Swimming / Endurance | ~{stroke_cost(sim,hpos,0,0)} stamina + treading')
        c=ctx['creature_by'].get(k)
        if c:
            sp=registry.species.get(c.species_id);lines.append(sp.name if sp else 'Creature')
        n=ctx['npc_by'].get(k)
        if n:lines.append(n.name if n.uid in ctx['known_npcs'] else 'Stranger')
        shell=ctx.get('shell_by',{}).get(k)
        if shell is not None:
            lines.append(str(shell.function).replace('_',' ').title())
            # A transparent roof corner can still be over the solid footprint.
            # Describe the collision honestly without advertising a painted
            # object action that the alpha-aware pointer did not actually hit.
            if painted_hit_testing:
                lines.append('Building footprint — movement blocked')
            else:
                lines.append('Entrance door — right-click to enter or knock' if shell.entrance is not None and (wx,wy)==tuple(shell.entrance)
                             else 'Building exterior — right-click to inspect')
            return lines
        settlement=ctx.get('settlement_by',{}).get(k)
        if settlement:
            spid=settlement.structure_piece_id or settlement.fixture_piece_id or settlement.ground_piece_id
            piece=registry.settlement_pieces.get(spid) if spid else None
            structure=sim.settlement_physicalization.structure_by_id(settlement.structure_id) if settlement.structure_id else None
            if structure is not None:lines.append(str(structure.function).replace('_',' ').title())
            if piece is not None:lines.append(piece.name)
        st=ctx['structure_by'].get(k)
        if st:
            d=registry.structures.get(st.structure_id);lines.append(d.name if d else st.structure_id)
        pc=ctx.get('property_container_by',{}).get(k)
        if pc:
            lines.append(pc.name or 'Property storage')
        cr=ctx['crop_by'].get(k)
        if cr:
            d=registry.crops.get(cr.crop_id);lines.append((d.name if d else cr.crop_id)+(' (mature)' if cr.mature else f' ({int(cr.growth)}%)'))
        feature=ctx['resource_by'].get(k)
        if feature:
            fv,_=feature;d=registry.resources.get(fv.feature_id);lines.append(d.name if d else fv.feature_id)
        pile=ctx['pile_by'].get(k)
        if pile:
            for iid,qty in list(pile.items.items())[:3]:
                d=registry.items.get(iid);lines.append(f'{qty}x {d.name if d else iid}')
        sign=ctx.get('sign_by',{}).get(k)
        if sign:
            lines.append(sim.hunting.describe_sign(sign,sim.player_skill('hunting'),sim.player_skill('survival'),sim.clock.minute,species_known=sign.species_id in sim.known_species_ids()))
        home=ctx.get('home_by',{}).get(k)
        if home:
            lines.append(sim.hunting.describe_home(home,sim.player_skill('hunting'),sim.player_skill('survival')))
        attack=ctx.get('combat_by',{}).get(k)
        if attack:
            difficulty=str(attack.get('difficulty','')).replace('_',' ').title()
            lines.append(f'Attack: {difficulty}')
        return lines

    def _restore_hover_damage(self):
        if self.screen is None or self._hover_map_snapshot is None or not self._hover_context:return None
        used=self._hover_context['used']; damage=None
        for rect in (self._hover_rect,self._hover_tile_rect):
            if rect is None:continue
            clipped=rect.clip(used)
            if clipped.width<=0 or clipped.height<=0:continue
            src=self.pg.Rect(clipped.x-used.x,clipped.y-used.y,clipped.width,clipped.height)
            self.screen.blit(self._hover_map_snapshot,clipped.topleft,src)
            damage=clipped.copy() if damage is None else damage.union(clipped)
        self._hover_rect=None;self._hover_tile_rect=None
        return damage

    def present_homestead_styles(self,style,index:int,count:int)->None:
        from worldseed.ui.homestead_panels import present_style_selector
        present_style_selector(self,style,index,count)

    def present_homestead_depot(self,data:dict)->None:
        from worldseed.ui.homestead_panels import present_blueprint_depot
        present_blueprint_depot(self,data)

    def begin_homestead_placement(self,style_id:str)->None:
        """Temporary UI intent; only confirm emits a simulation command."""
        self._homestead_placement={'style_id':str(style_id),'orientation':0}
        self._hover_cell=None

    def _blueprint_cursor_cell(self,pos):
        ctx=self._hover_context
        if not ctx or not ctx['used'].collidepoint(pos):return None
        size=ctx['tile_px']
        wx=ctx['left']+(pos[0]-ctx.get('grid_x',ctx['used'].x))//size
        wy=ctx['top']+(pos[1]-ctx.get('grid_y',ctx['used'].y))//size
        # Select the center of the rotated house, not its upper-left tile.
        # Preview and click both use this function and cannot disagree.
        placement=getattr(self,'_homestead_placement',None)
        if placement:
            from worldseed.systems.homestead_blueprints import catalog
            style=catalog()[1].get(str(placement.get('style_id','')))
            if style:
                home=catalog()[0][style['home_id']]
                width,height=int(home['width']),int(home['depth'])
                if int(placement.get('orientation',0))%2:width,height=height,width
                wx-=width//2;wy-=height//2
        return wx,wy

    def _refresh_homestead_ghost(self,force:bool=False,update_display:bool=True)->None:
        """Paint an alpha footprint, cabin silhouette and explicit door onto the
        retained world view. Mouse movement never creates or spends anything.
        """
        if self.screen is None or not self._hover_context or self._hover_map_snapshot is None:return
        pg=self.pg;ctx=self._hover_context;used=ctx['used']
        cell=self._blueprint_cursor_cell(self._last_mouse)
        state=getattr(self,'_homestead_placement',None)
        if not state:return
        marker=(cell,int(state['orientation']))
        if not force and marker==self._hover_cell:return
        damage=self._restore_hover_damage()
        self._hover_cell=marker
        if cell is None:
            if update_display and damage is not None:pg.display.update(damage)
            return
        from worldseed.systems.homestead_blueprints import footprint,doorway,catalog
        wx,wy=cell
        orientation=int(state['orientation'])
        style_id=str(state['style_id'])
        sim=ctx['sim']
        ok,reason,site=sim.homestead.preview(style_id,wx,wy,orientation)
        if site is None:
            if update_display and damage is not None:pg.display.update(damage)
            return
        cells=footprint(site)
        entrance,landing=doorway(site)
        size=ctx['tile_px']
        x0=min(x for x,y,z in cells);x1=max(x for x,y,z in cells)
        y0=min(y for x,y,z in cells);y1=max(y for x,y,z in cells)
        rect=pg.Rect(ctx['grid_x']+(x0-ctx['left'])*size,
                     ctx['grid_y']+(y0-ctx['top'])*size,
                     (x1-x0+1)*size,(y1-y0+1)*size)
        # All of the body and roof share the actual 3x3 reserved footprint.
        # This is a model preview, not the completed building art sprite.
        ghost=pg.Surface(rect.size,pg.SRCALPHA)
        valid=(92,210,154) if ok else (245,104,98)
        floor_rgb=(97,73,47) if ok else (111,49,44)
        frame=pg.Rect(3,3,max(1,rect.w-6),max(1,rect.h-6))
        pg.draw.rect(ghost,(*floor_rgb,100),frame)
        for cx,cy,cz in cells:
            r=pg.Rect((cx-x0)*size,(cy-y0)*size,size,size)
            pg.draw.rect(ghost,(*valid,105),r,1)
        # The preview uses the exact same authored cabin sprite as the world.
        pg.draw.rect(ghost,(*valid,235),frame,max(2,size//13))
        oldclip=self.screen.get_clip()
        self.screen.set_clip(used)
        self.screen.blit(ghost,rect.topleft)
        from worldseed.ui.homestead_art import draw_cabin_art,doorway_edge_rect
        art_rect=draw_cabin_art(self,site,grid_x=ctx['grid_x'],grid_y=ctx['grid_y'],
                                left=ctx['left'],top=ctx['top'],size=size,
                                clip=used,opacity=155 if ok else 108)
        edge=doorway_edge_rect(pg,site,ctx['grid_x'],ctx['grid_y'],ctx['left'],ctx['top'],size)
        pg.draw.rect(self.screen,(250,208,111),edge)
        for location,rgb in ((landing,(126,221,243)),):
            px,py,pz=location
            draw=pg.Rect(ctx['grid_x']+(px-ctx['left'])*size,
                         ctx['grid_y']+(py-ctx['top'])*size,size,size)
            pg.draw.rect(self.screen,rgb,draw.inflate(-max(4,size//3),-max(4,size//3)),max(2,size//13))
        self.screen.set_clip(oldclip)
        bounds=rect.union(pg.Rect(ctx['grid_x']+(landing[0]-ctx['left'])*size,
                                  ctx['grid_y']+(landing[1]-ctx['top'])*size,size,size))
        if art_rect is not None:bounds=bounds.union(art_rect)
        bounds=bounds.clip(used)
        if bounds.width>0 and bounds.height>0:
            self._hover_tile_rect=bounds
            damage=bounds if damage is None else damage.union(bounds)
        style=catalog()[1][style_id]
        direction=('South','West','North','East')[orientation]
        label=f"{style['name'].split(' — ')[-1]} log cabin | {direction} door"
        caption='VALID - left-click to place' if ok else 'BLOCKED - '+reason
        tooltip=self._draw_hover_tooltip(
            [label,caption,'Gold = door  |  Blue = exterior landing',
             'R = rotate  |  Right-click / Esc = cancel'],(rect.right,rect.top),used)
        self._hover_rect=tooltip
        if tooltip is not None:damage=tooltip if damage is None else damage.union(tooltip)
        if update_display and damage is not None:pg.display.update(damage)

    def _refresh_hover_only(self, force:bool=False, update_display:bool=True)->None:
        # Fast path for mouse movement: update only the tile highlight + tooltip.
        # Crucially this never asks the app to rerender terrain or advance sim.
        if self.screen is None or not self._hover_context or self._hover_map_snapshot is None:return
        if getattr(self,'_homestead_placement',None):
            self._refresh_homestead_ghost(force=force,update_display=update_display)
            return
        ctx=self._hover_context;used=ctx['used'];mx,my=self._last_mouse;tile_px=ctx['tile_px']
        if used.collidepoint(mx,my):
            grid_x=int(ctx.get('grid_x',used.x))
            grid_y=int(ctx.get('grid_y',used.y))
            sx=(mx-grid_x)//tile_px;sy=(my-grid_y)//tile_px
            cell=(sx,sy)
        else:cell=None
        hover_object=None
        if cell is not None and ctx.get('shell_hit_regions'):
            from worldseed.ui.exterior_view import shell_at_pointer
            hit=shell_at_pointer(ctx,self._last_mouse)
            if hit is not None:hover_object=(hit[0].uid,hit[1])
        if not force and cell==self._hover_cell and hover_object==getattr(self,'_hover_object',None):return
        self._hover_object=hover_object
        damage=self._restore_hover_damage();self._hover_cell=cell
        if cell is not None:
            sx,sy=cell;wx=ctx['left']+sx;wy=ctx['top']+sy
            tile_rect=self.pg.Rect(ctx.get('grid_x',used.x)+sx*tile_px,
                                   ctx.get('grid_y',used.y)+sy*tile_px,tile_px,tile_px).clip(used)
            self.pg.draw.rect(self.screen,self._theme['accent'],tile_rect,1)
            self._hover_tile_rect=tile_rect
            anchor=(tile_rect.right,tile_rect.top)
            self._hover_rect=self._draw_hover_tooltip(self._hover_lines_for(wx,wy,self._last_mouse),anchor,used)
            new_damage=tile_rect.copy()
            if self._hover_rect is not None:new_damage=new_damage.union(self._hover_rect)
            damage=new_damage if damage is None else damage.union(new_damage)
        if update_display and damage is not None:self.pg.display.update(damage)

    def _draw_footer(self, rect, message: str, sim=None) -> None:
        """Draw mouse-switchable world events and authoritative damage entries."""
        pg=self.pg;screen=self.screen;th=self._theme
        if sim is not None:self._activity_footer_context=(rect.copy(),message,sim)
        self._pointer_targets=[(area,token) for area,token in self._pointer_targets
                               if not token.startswith('FOOTER_TAB:')]
        old_clip=screen.get_clip();screen.set_clip(rect.inflate(-8,-6))
        try:
            pg.draw.rect(screen,th['panel2'],rect,border_radius=3)
            screen.blit(self.small_font.render('WORLD ACTIVITY',True,th['accent']),(rect.x+14,rect.y+9))
            active=self._world_activity_tab
            for tab,label,offset,width in (
                ('activity','Events',137,66),('combat','Combat Log',211,105)):
                button=pg.Rect(rect.x+offset,rect.y+3,width,26)
                selected=active==tab
                pg.draw.rect(screen,th['panel'] if selected else th['panel2'],button,border_radius=3)
                pg.draw.rect(screen,th['accent'] if selected else th['edge'],button,1,border_radius=3)
                txt=self.small_font.render(label,True,th['accent'] if selected else th['muted'])
                screen.blit(txt,txt.get_rect(center=button.center))
                self._ui_target(button,'FOOTER_TAB:'+tab)
            section='DAMAGE EVENTS' if active=='combat' else 'RECENT EVENTS'
            screen.blit(self.small_font.render(section,True,th['muted']),(rect.right-132,rect.y+9))
            pg.draw.line(screen,th['edge'],(rect.x+14,rect.y+30),(rect.right-14,rect.y+30))
            if active=='combat':
                entries=list(getattr(getattr(sim,'state',None),'player_combat_log',()) or ())
                events=[]
                for item in entries[-12:]:
                    direction=str(item.get('direction','taken'))
                    amount=int(item.get('amount',0));minute=int(item.get('minute',0))%1440
                    name=str(item.get('source','Unknown') if direction=='taken' else item.get('target','Unknown'))
                    kind=str(item.get('kind','physical')).replace('_',' ')
                    part=str(item.get('part','')).replace('_',' ')
                    suffix=' - '+part if part else ''
                    verb='TOOK' if direction=='taken' else 'DEALT'
                    events.append((f'{minute//60:02d}:{minute%60:02d}  {verb} {amount} HP  {name} [{kind}]{suffix}',direction))
                if not events:events=[('No damage recorded yet.','none')]
            else:
                events=[(str(e.message).replace('\\n',' '),'activity') for e in list(getattr(sim,'log',()))[-5:]] if sim is not None else []
                latest=str(message).replace('\\n',' ').strip()
                if latest and (not events or latest!=events[-1][0]):events.append((latest,'activity'))
                if not events:events=[('The world continues around you.','activity')]
            max_lines=max(1,(rect.height-44)//22);shown=events[-max_lines:]
            for i,(line,direction) in enumerate(shown):
                current=i==len(shown)-1;y=rect.y+38+i*22
                if current:pg.draw.rect(screen,(45,47,42),(rect.x+9,y-2,rect.width-18,21),border_radius=3)
                color=(th['danger'] if direction=='taken' else th['good'] if direction=='dealt'
                       else th['text'] if current else th['muted'])
                pg.draw.circle(screen,th['accent'] if current else color,(rect.x+18,y+8),3)
                screen.blit(self.small_font.render(self._fit_ui_text(line,self.small_font,rect.width-52),True,color),(rect.x+30,y))
        finally:screen.set_clip(old_clip)

    def _draw_hud_icon(self, name, rect, color):
        """Small vector glyphs stay sharp at every supported window size."""
        pg=self.pg;s=self.screen;cx,cy=rect.center;w=rect.width
        if name=='Inventory':
            pg.draw.rect(s,color,(cx-10,cy-6,20,16),2,border_radius=2)
            pg.draw.arc(s,color,(cx-5,cy-11,10,11),0,math.pi,2)
        elif name=='Crafting':
            pg.draw.line(s,color,(cx-10,cy+8),(cx+8,cy-10),3)
            pg.draw.line(s,color,(cx-8,cy-10),(cx+10,cy+8),3)
            pg.draw.circle(s,color,(cx-9,cy-10),3,1)
        elif name=='Build':
            pg.draw.polygon(s,color,[(cx-11,cy-2),(cx,cy-11),(cx+11,cy-2)],2)
            pg.draw.rect(s,color,(cx-8,cy-2,16,13),2)
            pg.draw.rect(s,color,(cx-2,cy+4,5,7),1)
        elif name=='Health':
            pg.draw.line(s,color,(cx-10,cy),(cx+10,cy),3)
            pg.draw.line(s,color,(cx,cy-10),(cx,cy+10),3)
            pg.draw.rect(s,color,(cx-13,cy-13,26,26),1,border_radius=4)
        elif name=='Map':
            pg.draw.polygon(s,color,[(cx-12,cy-9),(cx-4,cy-12),(cx+4,cy-8),(cx+12,cy-11),(cx+12,cy+9),(cx+4,cy+12),(cx-4,cy+8),(cx-12,cy+11)],2)
            for dx in (-4,4):pg.draw.line(s,color,(cx+dx,cy-9),(cx+dx,cy+9),1)
        elif name=='Actions':
            pg.draw.circle(s,color,(cx,cy),10,2)
            pg.draw.line(s,color,(cx-5,cy),(cx+5,cy),2)
            pg.draw.line(s,color,(cx,cy-5),(cx,cy+5),2)
        elif name=='World':
            pg.draw.circle(s,color,(cx,cy),11,2)
            pg.draw.ellipse(s,color,(cx-5,cy-11,10,22),1)
            pg.draw.line(s,color,(cx-10,cy),(cx+10,cy),1)
        elif name=='Look':
            pg.draw.ellipse(s,color,(cx-12,cy-7,24,14),2)
            pg.draw.circle(s,color,(cx,cy),4)
        elif name=='Help':
            pg.draw.circle(s,color,(cx,cy),11,2)
            mark=self.font.render('?',True,color);s.blit(mark,(cx-mark.get_width()//2,cy-mark.get_height()//2))
        else:
            pg.draw.rect(s,color,(cx-9,cy-10,18,20),2,border_radius=3)
            pg.draw.line(s,color,(cx-4,cy-3),(cx+4,cy-3),2)
            pg.draw.line(s,color,(cx-4,cy+3),(cx+4,cy+3),2)

    def _draw_hud_actions(self, rect, stance='normal'):
        """One bounded toolbar for exterior and continuous interior views."""
        from worldseed.ui.router import HUD_BUTTONS
        pg=self.pg;screen=self.screen;th=self._theme
        inset=min(9,max(0,rect.width//12));margin=min(11,max(1,rect.width//16))
        height=max(1,min(168,rect.height-2*inset))
        bar=pg.Rect(rect.x+inset,rect.bottom-inset-height,max(1,rect.width-2*inset),height)
        self._hud_tooltip_bounds=pg.Rect(rect.x+inset,rect.y+3,max(1,rect.width-2*inset),max(1,rect.height-6))
        old_clip=screen.get_clip();screen.set_clip(bar.clip(old_clip))
        pg.draw.rect(screen,(19,23,25),bar,border_radius=5)
        pg.draw.rect(screen,th['edge'],bar,1,border_radius=5)
        title=self._fit_ui_text('TOOLS & ACTIONS',self.small_font,max(1,bar.width-2*margin))
        screen.blit(self.small_font.render(title,True,th['accent']),(bar.x+margin,bar.y+7))
        cols=5;gap=min(6,max(0,bar.width//35));bw=max(1,(bar.width-2*margin-gap*4)//cols)
        buttons=HUD_BUTTONS if self._input_mode=='world' else (('Confirm','\r'),('Cancel','ESC'))
        header=min(28,max(1,bar.height//5));stance_height=min(29,max(1,bar.height//5))
        button_h=max(1,min(40,(bar.height-header-stance_height-18)//2))
        descriptions={
            'Inventory':'Manage carried items and equipment', 'Crafting':'Recipes and discovery',
            'Build':'Construction and placement', 'Health':'Health and condition',
            'Map':'Explore the world map', 'Actions':'Interact with the world',
            'World':'Open the World Console', 'Look':'Inspect a nearby tile',
            'Help':'Controls and help', 'Pause':'Save, settings, and exit',
            'Confirm':'Confirm target', 'Cancel':'Cancel target',
        }
        for i,(name,token) in enumerate(buttons):
            box=pg.Rect(bar.x+margin+(i%cols)*(bw+gap),bar.y+header+(i//cols)*(button_h+gap),bw,button_h).clip(bar)
            hovered=box.collidepoint(self._last_mouse)
            pg.draw.rect(screen,(53,58,55) if hovered else th['panel2'],box,border_radius=4)
            pg.draw.rect(screen,th['edge_hi'] if hovered else th['edge'],box,1,border_radius=4)
            screen.set_clip(box.clip(old_clip))
            self._draw_hud_icon(name,box,th['accent'] if hovered else th['text'])
            screen.set_clip(bar.clip(old_clip))
            self._pointer_targets.append((box,token))
            hint={'\r':'Enter','\t':'Tab','ESC':'Esc'}.get(token,token.upper())
            self._hud_tooltips.append((box,name,f'{descriptions[name]}  [{hint}]'))
        if self._input_mode=='world':
            sy=bar.bottom-stance_height-9
            pg.draw.line(screen,th['edge'],(bar.x+margin,sy-7),(bar.right-margin,sy-7))
            self._draw_stance_buttons(pg.Rect(bar.x,sy,bar.width,stance_height),stance)
        screen.set_clip(old_clip)
        self._hud_tooltip_hover=None;self._hud_tooltip_since=self.pg.time.get_ticks()
        return bar

    def _draw_stance_buttons(self,rect,stance='normal'):
        """Shared HUD-only posture selection for exterior and interior spaces."""
        pg=self.pg;screen=self.screen;th=self._theme
        margin=min(11,max(0,rect.width//12));gap=min(2,max(0,rect.width//40))
        width=max(1,(rect.width-2*margin-gap*3)//4)
        height=max(1,min(29,rect.height))
        for i,(name,detail) in enumerate((('normal','Normal · fastest'),('stalk','Stalk · quieter, enables theft'),('crouch','Crouch · quietest'),('aggressive','Aggressive Stance · lockpicking, door bashing'))):
            slot=pg.Rect(rect.x+margin+i*(width+gap),rect.y,width,height).clip(rect)
            active=stance==name
            pg.draw.rect(screen,(85,73,48) if active else th['panel2'],slot,border_radius=3)
            pg.draw.rect(screen,th['accent'] if active else th['edge'],slot,1,border_radius=3)
            label=self.small_font.render(self._fit_ui_text('Aggro' if name=='aggressive' else name.title(),self.small_font,max(1,slot.width-6)),True,th['text'] if active else th['muted'])
            clip=screen.get_clip();screen.set_clip(slot.clip(clip))
            screen.blit(label,label.get_rect(center=slot.center));screen.set_clip(clip)
            self._pointer_targets.append((slot,'UI_STANCE:'+name))
            self._hud_tooltips.append((slot,name.title()+' movement',detail+'; changes movement stance'))

    def _update_hud_tooltip_hover(self, now):
        target=next(((r,name,description) for r,name,description in self._hud_tooltips if r.collidepoint(self._last_mouse)),None)
        if target==self._hud_tooltip_hover:return
        if self._hud_tooltip_rect is not None and self._hud_tooltip_backdrop is not None:
            self.screen.blit(self._hud_tooltip_backdrop,self._hud_tooltip_rect.topleft)
            self.pg.display.update(self._hud_tooltip_rect)
        self._hud_tooltip_rect=None;self._hud_tooltip_backdrop=None
        self._hud_tooltip_hover=target;self._hud_tooltip_since=now

    def _tick_hud_tooltip(self, now):
        if self._hud_tooltip_hover is None or self._hud_tooltip_rect is not None or now-self._hud_tooltip_since<1200:return
        _,name,description=self._hud_tooltip_hover
        bounds=self.screen.get_rect();font=self.small_font
        bar=self._hud_tooltip_bounds
        width=min(bar.width,max(font.size(name)[0],font.size(description)[0])+22)
        height=49
        action_rect=self._hud_tooltip_hover[0]
        x=max(bar.x,min(action_rect.centerx-width//2,bar.right-width))
        y=max(58,action_rect.top-height-8)
        rect=self.pg.Rect(x,y,width,height)
        self._hud_tooltip_backdrop=self.screen.subsurface(rect).copy();self._hud_tooltip_rect=rect
        self.pg.draw.rect(self.screen,(18,22,24),rect,border_radius=4)
        self.pg.draw.rect(self.screen,self._theme['edge_hi'],rect,1,border_radius=4)
        self.screen.blit(font.render(name,True,self._theme['accent']),(x+10,y+5))
        label=self._fit_ui_text(description,font,width-20)
        self.screen.blit(font.render(label,True,self._theme['text']),(x+10,y+25))
        self.pg.display.update(rect)

    def present_region_map(self, sim) -> None:
        """Present authoritative prepared terrain without realization."""
        from worldseed.ui.atlas_map import draw_atlas
        draw_atlas(self, sim)

    def _play_combat_effects(self,sim,used,left:int,top:int,tile_px:int,z:int)->None:
        events=[e for e in getattr(sim,'visual_effects',()) if int(e.get('uid',0))>self._last_combat_effect_uid]
        if not events or self.screen is None:return
        pg=self.pg
        for event in events[-3:]:
            uid=int(event.get('uid',0));self._last_combat_effect_uid=max(self._last_combat_effect_uid,uid)
            src=event.get('source',(0,0,z));dst=event.get('target',(0,0,z))
            if len(src)<3 or len(dst)<3 or int(src[2])!=z or int(dst[2])!=z:continue
            sx=used.x+(int(src[0])-left)*tile_px+tile_px//2;sy=used.y+(int(src[1])-top)*tile_px+tile_px//2
            tx=used.x+(int(dst[0])-left)*tile_px+tile_px//2;ty=used.y+(int(dst[1])-top)*tile_px+tile_px//2
            if not used.collidepoint(sx,sy) and not used.collidepoint(tx,ty):continue
            base=self.screen.subsurface(used).copy();kind=str(event.get('kind',''))
            duration=120 if kind=='projectile' else 95;start=pg.time.get_ticks()
            while True:
                elapsed=pg.time.get_ticks()-start;t=min(1.0,elapsed/max(1,duration))
                self.screen.blit(base,used.topleft)
                if kind=='projectile':
                    x=round(sx+(tx-sx)*t);y=round(sy+(ty-sy)*t)
                    pg.draw.line(self.screen,(224,213,170),(sx,sy),(x,y),max(1,tile_px//14))
                    pg.draw.circle(self.screen,(242,231,183),(x,y),max(2,tile_px//9))
                else:
                    dx=tx-sx;dy=ty-sy;length=max(1.0,(dx*dx+dy*dy)**0.5)
                    reach=max(6,int(tile_px*(.45+.45*t)));ex=round(sx+dx/length*reach);ey=round(sy+dy/length*reach)
                    col=(224,185,105) if kind in ('melee','bash') else (204,102,83)
                    pg.draw.line(self.screen,col,(sx,sy),(ex,ey),max(2,tile_px//8))
                    pg.draw.circle(self.screen,col,(tx,ty),max(2,round(tile_px*.18*t)),1)
                pg.display.update(used);pg.event.pump();self.clock.tick(120)
                if t>=1:break
            self.screen.blit(base,used.topleft);pg.display.update(used)

    def present_game(self, registry, world, entities, sim, player_id: int, message: str = '', cursor: WorldPos | None = None,
                     combat_overlay: dict | None = None, stealth_overlay: dict | None = None) -> None:
        """Hybrid local-world view: sprite map + dense terminal-derived panels."""
        pg=self.pg; screen=self.screen
        if screen is None: return
        interiors=getattr(sim,'interiors',None)
        if interiors is not None and interiors.current_plan() is not None:
            from worldseed.ui.interior_view import draw_interior
            draw_interior(self,registry,sim,entities,player_id,message)
            return
        self._interior_context=None
        terrain_token=(id(registry),len(registry.terrains))
        if terrain_token!=self._terrain_catalog_token:
            configure_terrain_catalog(registry.terrains);self._terrain_catalog_token=terrain_token
            self._terrain_transition_cache.clear();self._terrain_transition_masks.clear()
        self._drawing_target=cursor is not None
        self._combat_targeting=combat_overlay is not None
        ox,oy,ow,oh=self._draw_chrome("WORLDSEED // LOCAL")
        sw,sh=screen.get_size(); sidebar=max(280,min(350,sw//4)); footer=148
        map_rect=pg.Rect(ox,oy,ow-sidebar-10,oh-footer-8); side_rect=pg.Rect(map_rect.right+10,oy,sidebar,oh); foot_rect=pg.Rect(ox,map_rect.bottom+8,map_rect.width,footer)
        pg.draw.rect(screen,(10,13,15),map_rect); pg.draw.rect(screen,self._theme['panel2'],side_rect,border_radius=3); pg.draw.rect(screen,self._theme['panel2'],foot_rect,border_radius=3)
        pg.draw.rect(screen,self._theme['edge'],map_rect,1); pg.draw.rect(screen,self._theme['edge'],side_rect,1,border_radius=3); pg.draw.rect(screen,self._theme['edge'],foot_rect,1,border_radius=3)

        pos=entities.get(player_id,Position).value
        vit=entities.try_get(player_id,Vitals) or Vitals()
        inv=entities.get(player_id,Inventory)
        tile_px=self._tile_px
        cols, rows, inset_x, inset_y = centered_tile_grid(map_rect.width, map_rect.height, tile_px)
        map_rect = pg.Rect(map_rect.x + inset_x, map_rect.y + inset_y, cols * tile_px, rows * tile_px)
        # Keep a fixed viewport but render one extra tile on each side.
        # World coordinates and the sprite share the same continuous camera:
        # when fx wraps at a tile boundary, the projection remains continuous.
        viewport=map_rect.copy()
        view_cols,view_rows=cols,rows
        fx=max(0.0,min(0.999,float(getattr(sim.state,'player_fx',0.5))))
        fy=max(0.0,min(0.999,float(getattr(sim.state,'player_fy',0.5))))
        cx,cy,cz=pos.x,pos.y,pos.z
        self._camera=(cx,cy,cz)
        left=cx-view_cols//2-1; top=cy-view_rows//2-1
        cols=view_cols+2; rows=view_rows+2
        map_rect=pg.Rect(
            viewport.x-tile_px-round((fx-0.5)*tile_px),
            viewport.y-tile_px-round((fy-0.5)*tile_px),
            cols*tile_px,rows*tile_px,
        )
        known=sim.discovered_tiles_set
        visible=getattr(sim,'visible_tiles_set',known)
        right = left + cols - 1
        bottom = top + rows - 1
        def _onscreen(x:int,y:int,z:int)->bool:
            return z == pos.z and left <= x <= right and top <= y <= bottom
        nearby=self._spatial_state_views(sim,left,top,right,bottom,pos.z)
        creature_by={(c.x,c.y,c.z):c for c in nearby['creatures'] if c.hp>0 and _onscreen(c.x,c.y,c.z)}
        interior_actors=getattr(sim.state,'interior_actors',{})
        npc_by={(n.x,n.y,n.z):n for n in nearby['npcs'] if n.alive and n.uid not in interior_actors and _onscreen(n.x,n.y,n.z)}
        structure_by={(s.x,s.y,s.z):s for s in nearby['structures'] if _onscreen(s.x,s.y,s.z)}
        property_container_by={
            (q.x,q.y,q.z):q for q in nearby['containers']
            if q.kind=='property' and not getattr(q,'interior_space_id','') and _onscreen(q.x,q.y,q.z)
        }
        settlement_by={(c.x,c.y,0):c for c in sim.settlement_physicalization.cells_in_bounds(left,top,right,bottom)} if pos.z==0 else {}
        shell_query=getattr(sim.settlement_physicalization,'shells_in_bounds',None)
        building_shells=shell_query(left,top,right,bottom) if pos.z==0 and callable(shell_query) else ()
        from worldseed.ui.exterior_view import shell_cells, draw_shells
        shell_by=shell_cells(building_shells)
        shell_hit_regions=[]
        property_container_by={key:row for key,row in property_container_by.items() if key not in shell_by}
        crop_by={(q.x,q.y,q.z):q for q in nearby['crops'] if _onscreen(q.x,q.y,q.z)}
        fire_by={(f.x,f.y,f.z):f for f in nearby['fires'] if _onscreen(f.x,f.y,f.z)}
        fluid_by={(f.x,f.y,f.z):f for f in nearby['fluids'] if f.amount>20 and _onscreen(f.x,f.y,f.z)}
        pile_by={(p.x,p.y,p.z):p for p in nearby['ground_piles'] if p.items and _onscreen(p.x,p.y,p.z)}
        carcass_by={(q.x,q.y,q.z):q for q in nearby['carcasses'] if _onscreen(q.x,q.y,q.z)}
        hunt_skill=max(sim.player_skill('hunting'),sim.player_skill('survival'))
        sign_by={(q.x,q.y,q.z):q for q in nearby['animal_signs'] if _onscreen(q.x,q.y,q.z) and q.strength+hunt_skill*8>=52}
        home_by={(q.x,q.y,q.z):q for q in nearby['animal_homes'] if _onscreen(q.x,q.y,q.z) and q.discovered}
        monument_by={(m.x,m.y,0):m for m in sim.state.claim_monuments.values() if _onscreen(m.x,m.y,0)} if pos.z==0 else {}
        resource_by=self._resource_view(sim,visible,pos.z,left,top,cols,rows)
        resource_by={
            k:v for k,v in resource_by.items()
            if not sim.settlement_physicalization.clears_natural_feature(WorldPos(k[0],k[1],k[2]))
        }
        if pos.z==0:
            weather,lighting=sim.environment.visual_conditions(sim.clock.minute,pos)
        else:
            weather={'kind':'underground','cloud_cover':0,'rain':0,'wetness':0,'fog':0,'wind_dx':0,'wind_dy':0,'storm_intensity':0}
            lighting=None
        known_npcs=sim.introduced_npc_ids()
        neighbor_cache={}
        display_cache={}
        current_cache={}

        def discovered_neighbor_ids(wx:int, wy:int):
            key=(wx,wy)
            cached=neighbor_cache.get(key)
            if cached is not None:return cached
            ids={}
            for direction,ndx,ndy in DIRECTIONS_8:
                nwx,nwy=wx+ndx,wy+ndy
                if pos_key(nwx,nwy,pos.z) not in known:continue
                ids[direction]=world.tile_at(WorldPos(nwx,nwy,pos.z)).terrain_id
            neighbor_cache[key]=ids
            return ids

        def display_id_for(wx:int, wy:int, terrain_id:str):
            key=(wx,wy,terrain_id)
            cached=display_cache.get(key)
            if cached is not None:return cached
            value=contextual_display_id(terrain_id, discovered_neighbor_ids(wx,wy) if terrain_id=='core:water' else {})
            display_cache[key]=value
            return value

        def current_for(wx:int, wy:int):
            hydro=getattr(world.generator,'hydrology',None)
            domain=hydro.cached_domain(*hydro.domain_for_world(wx,wy)) if hydro else None
            key=(world.generator.world_seed,world.generator.version,wx,wy,pos.z,
                 domain.fingerprint if domain else None)
            if key in self._water_current_cache:return self._water_current_cache[key]
            value=world.current_at(WorldPos(wx,wy,pos.z),prepared_only=True)
            # A missing prepared domain may be supplied later. Do not retain
            # speculative currents while hydrology preparation is incomplete.
            ready=hydro is None or domain is not None
            if ready:
                if len(self._water_current_cache)>=8192:self._water_current_cache.clear()
                self._water_current_cache[key]=value
            return value

        # Clip all world layers (terrain, structures, sprites, weather) to the
        # original map panel; margins may extend over the HUD or window edges.
        prior_world_clip=screen.get_clip()
        screen.set_clip(viewport)
        terrain_base=self._build_base_layer(world, known, pos.z, left, top, cols, rows, tile_px)
        screen.blit(terrain_base, map_rect.topleft)
        water_phase=(pg.time.get_ticks()//160)%8
        water_cells=[]
        weather_cells=[]
        for sy in range(rows):
            wy=top+sy
            for sx in range(cols):
                wx=left+sx
                if pos_key(wx,wy,pos.z) not in visible:continue
                tile=world.tile_at(WorldPos(wx,wy,pos.z))
                display_id=display_id_for(wx,wy,tile.terrain_id)
                rect=pg.Rect(map_rect.x+sx*tile_px,map_rect.y+sy*tile_px,tile_px,tile_px)
                if display_id not in CONTEXTUAL_WATER_DISPLAY_IDS:
                    weather_cells.append((rect.copy(),tile.terrain_id))
                    continue
                current=current_for(wx,wy)
                flow_dx=int(getattr(current,'dx',0) or 0) if current is not None else 0
                flow_dy=int(getattr(current,'dy',0) or 0) if current is not None else 0
                flow_speed=int(getattr(current,'speed',0) or 0) if current is not None else 0
                water_cells.append((rect.copy(),display_id,flow_dx,flow_dy,flow_speed))
                screen.blit(self._animated_water_overlay(display_id,tile_px,water_phase,flow_dx,flow_dy,flow_speed), rect.topleft)
        def _blit_static_memory(surf, dest, key):
            """Render discovered static world geometry outside current LOS dimmed."""
            if surf is None:return
            if pos_key(*key) in visible:
                screen.blit(surf,dest);return
            cached_key=('remembered-static',id(surf))
            remembered=self._overlay_cache.get(cached_key)
            if remembered is None:
                remembered=surf.copy();remembered.set_alpha(138)
                self._overlay_cache[cached_key]=remembered
            screen.blit(remembered,dest)

        if settlement_by:
            for (wx,wy,wz),cell in sorted(settlement_by.items(),key=lambda kv:(kv[0][1],kv[0][0])):
                key=(wx,wy,wz)
                if wz!=pos.z or pos_key(wx,wy,wz) not in known or not cell.ground_piece_id or key in shell_by:continue
                piece=registry.settlement_pieces.get(cell.ground_piece_id)
                bits=self._settlement_connection_bits(key,cell,settlement_by,registry,ground=True)
                surf=self._settlement_ground_surface(piece,tile_px,bits)
                if surf is not None:
                    rect=pg.Rect(map_rect.x+(wx-left)*tile_px,map_rect.y+(wy-top)*tile_px,tile_px,tile_px)
                    _blit_static_memory(surf,rect.topleft,key)
        for key,placed in structure_by.items():
            piece=self._placed_building_piece(placed.structure_id)
            if piece is None or piece.category!='floor' or pos_key(*key) not in known:continue
            wx,wy,wz=key
            bits=self._placed_building_bits(key,structure_by,piece)
            surf=self._settlement_ground_surface(piece,tile_px,bits)
            if surf is not None:
                rect=pg.Rect(map_rect.x+(wx-left)*tile_px,map_rect.y+(wy-top)*tile_px,tile_px,tile_px)
                _blit_static_memory(surf,rect.topleft,key)
        if pos.z==0:
            self._weather_fx.draw_wet_ground(screen,weather_cells,int(weather.get('wetness',0)))

        combat_by={}
        if combat_overlay:
            range_fill=pg.Surface((cols*tile_px,rows*tile_px),pg.SRCALPHA)
            for cell in combat_overlay.get('cells',()):
                wx=int(cell.get('x',0));wy=int(cell.get('y',0));wz=int(cell.get('z',pos.z))
                if not _onscreen(wx,wy,wz):continue
                chance=max(0,min(100,int(cell.get('chance',0))))
                if cell.get('blocked'):
                    rgb=(104,108,110)
                elif chance>=50:
                    t=(chance-50)/50.0;rgb=(round(230*(1-t)+55*t),round(190+45*t),55)
                else:
                    t=chance/50.0;rgb=(225,round(55+135*t),55)
                combat_by[(wx,wy,wz)]={**cell,'rgb':rgb}
                local=pg.Rect((wx-left)*tile_px,(wy-top)*tile_px,tile_px,tile_px)
                pg.draw.rect(range_fill,(*rgb,30),local.inflate(-2,-2),border_radius=max(1,tile_px//8))
            if combat_by:screen.blit(range_fill,map_rect.topleft)
        stealth_by={}
        stealth_observers={}
        if stealth_overlay and stealth_overlay.get('active'):
            stealth_by={
                (int(cell.get('x',0)),int(cell.get('y',0)),int(cell.get('z',pos.z))):cell
                for cell in stealth_overlay.get('cells',())
                if _onscreen(int(cell.get('x',0)),int(cell.get('y',0)),int(cell.get('z',pos.z)))
            }
            stealth_observers={
                str(row.get('uid','')):row for row in stealth_overlay.get('observers',())
                if row.get('uid')
            }
        proc_species = self._visuals.procedural_species_paths()
        player_sprite = self._visuals.player_path(getattr(sim.state, 'player_sex', 'male'), getattr(sim.state, 'player_sprite_index', 0))
        cursor_sprite = self._visuals.special('cursor')

        # The cached base layer already contains every terrain tile. Walk only
        # cells that actually have an overlay instead of scanning the entire
        # viewport in Python every frame. Sorting by y preserves sprite depth.
        overlay_keys=set(resource_by)|set(fluid_by)|set(crop_by)|set(structure_by)|set(property_container_by)|set(pile_by)|set(carcass_by)|set(fire_by)|set(creature_by)|set(npc_by)|set(sign_by)|set(home_by)|set(monument_by)
        overlay_keys.update(settlement_by)
        overlay_keys.add((pos.x,pos.y,pos.z))
        if cursor is not None:overlay_keys.add((cursor.x,cursor.y,cursor.z))
        player_settlement_cell=sim.settlement_physicalization.cell_at(pos) if pos.z==0 else None
        # A doorway/wall belongs to the structure footprint but is not an
        # interior room. Keep roofs closed until the player actually steps into
        # a room so approaching/casing a house never reveals its floor plan.
        player_structure_id=(
            player_settlement_cell.structure_id
            if player_settlement_cell and player_settlement_cell.room_id else ''
        )
        for wx,wy,wz in sorted(overlay_keys,key=lambda q:(q[1],q[0])):
            if wz!=pos.z or not (left<=wx<=right and top<=wy<=bottom):continue
            k=(wx,wy,pos.z);pk=pos_key(*k)
            if pk not in known:continue
            is_visible=pk in visible
            sx=wx-left;sy=wy-top
            rect=pg.Rect(map_rect.x+sx*tile_px,map_rect.y+sy*tile_px,tile_px,tile_px)
            scell=settlement_by.get(k)
            if scell and k not in shell_by:
                roofed=bool(scell.roof_piece_id and scell.structure_id and scell.structure_id!=player_structure_id)
                if roofed:
                    roof_piece=registry.settlement_pieces.get(scell.roof_piece_id)
                    roof_bits=self._settlement_roof_bits(k,scell,settlement_by)
                    roof_surf=self._settlement_roof_surface(roof_piece,tile_px,roof_bits)
                    _blit_static_memory(roof_surf,rect.topleft,k)
                # Interior partitions/doors belong below the roof and should not
                # telegraph the floor plan while the player is outside. Exterior
                # shell pieces have no roof cell and remain visible.
                hide_under_roof=roofed and scell.structure_piece_role in {'partition','interior_door'}
                if scell.structure_piece_id and not hide_under_roof:
                    piece=registry.settlement_pieces.get(scell.structure_piece_id)
                    bits=self._settlement_connection_bits(k,scell,settlement_by,registry,ground=False)
                    surf=self._settlement_wall_surface(piece,tile_px,bits,scell.structure_piece_role)
                    _blit_static_memory(surf,rect.topleft,k)
                if scell.fixture_piece_id and not roofed:
                    if is_visible:
                        self._draw_settlement_piece(registry.settlement_pieces.get(scell.fixture_piece_id),rect,fixture=True)
                    else:
                        # Draw remembered fixtures to a temporary tile so their
                        # dim state does not mutate the shared sprite cache.
                        mem_tile=pg.Surface((tile_px,tile_px),pg.SRCALPHA)
                        old_screen=self.screen;self.screen=mem_tile
                        try:self._draw_settlement_piece(registry.settlement_pieces.get(scell.fixture_piece_id),pg.Rect(0,0,tile_px,tile_px),fixture=True)
                        finally:self.screen=old_screen
                        mem_tile.set_alpha(138);screen.blit(mem_tile,rect.topleft)
            # Player-built structures and property storage are static memory too.
            if k in structure_by:
                st=structure_by[k];piece=self._placed_building_piece(st.structure_id)
                if piece is not None:
                    bits=self._placed_building_bits(k,structure_by,piece)
                    if piece.category in {'wall','opening'}:
                        surf=self._settlement_wall_surface(piece,tile_px,bits,'entrance' if piece.category=='opening' else 'wall')
                    elif piece.category=='roof':
                        surf=self._settlement_roof_surface(piece,tile_px,bits)
                    else:surf=None
                    _blit_static_memory(surf,rect.topleft,k)
                else:
                    path=self._visuals.resolve(self._visuals.ref('structures',st.structure_id))
                    surf=self._load_sprite(path,int(tile_px*1.35),int(tile_px*1.35))
                    if surf is not None:
                        copy=surf if is_visible else surf.copy()
                        if not is_visible:copy.set_alpha(138)
                        screen.blit(copy,(rect.centerx-copy.get_width()//2,rect.bottom-copy.get_height()))
            if k in property_container_by:
                pc=property_container_by[k]
                path=self._visuals.resolve(self._visuals.ref('containers',getattr(pc,'profile_id',''))) or self._visuals.resolve(self._visuals.ref('structures',pc.source_id))
                surf=self._load_sprite(path,int(tile_px*1.35),int(tile_px*.95))
                if surf is not None:
                    copy=surf if is_visible else surf.copy()
                    if not is_visible:copy.set_alpha(138)
                    screen.blit(copy,(rect.centerx-copy.get_width()//2,rect.bottom-copy.get_height()))
            if k in monument_by:
                monument=monument_by[k]
                path=Path(__file__).resolve().parents[1]/'assets'/'sprites'/'monuments'/f'{monument.monument_type}.png'
                scale={'claim_stone':1.55,'watch_monument':1.9,'frontier_post':2.15,'regional_stronghold':2.45}.get(monument.monument_type,1.6)
                surf=self._load_sprite(path,int(tile_px*scale),int(tile_px*scale))
                if surf is not None:
                    copy=surf if is_visible else surf.copy()
                    if not is_visible:copy.set_alpha(138)
                    screen.blit(copy,(rect.centerx-copy.get_width()//2,rect.bottom-copy.get_height()))
            if not is_visible:
                # Never remember live actors, fires, fluids, wildlife, crop
                # growth, tracks or loose piles as if their old positions were
                # still current. Static architecture alone persists in memory.
                continue
            if k in fluid_by:screen.blit(self._fluid_overlay(tile_px),rect.topleft)
            feature=resource_by.get(k)
            if feature:
                fv,rp=feature
                self._draw_resource_feature(fv,rp,rect)
            if k in crop_by:
                crop=crop_by[k];ref=self._visuals.ref('crops',crop.crop_id);stage=2 if crop.mature else (1 if crop.growth>=45 else 0)
                self._draw_sprite_bottom(self._visuals.resolve(ref,stage),rect,1.25,255)
            if k in pile_by:
                iid=next(iter(pile_by[k].items));self._draw_sprite_bottom(self._visuals.resolve(self._visuals.ref('items',iid)),rect,.8)
            if k in carcass_by:
                carc=carcass_by[k];self._draw_sprite_bottom(self._visuals.resolve(self._visuals.ref('species',carc.species_id),1),rect,1.0,145)
            if k in sign_by:
                sign=sign_by[k]
                mark=(145,55,47) if sign.kind=='blood' else (174,145,99)
                rr=max(2,tile_px//10)
                pg.draw.ellipse(screen,mark,(rect.centerx-rr*2,rect.bottom-rr*3,rr*2,rr))
                pg.draw.ellipse(screen,mark,(rect.centerx+rr//2,rect.bottom-rr*2,rr*2,rr))
            if k in home_by:
                pg.draw.ellipse(screen,(24,20,17),(rect.x+tile_px//5,rect.y+tile_px//2,3*tile_px//5,tile_px//3))
                pg.draw.arc(screen,(103,82,58),(rect.x+tile_px//6,rect.y+tile_px//3,2*tile_px//3,tile_px//2),math.pi,2*math.pi,max(1,tile_px//12))
            if k in fire_by:self._draw_sprite_bottom(self._visuals.resolve(self._visuals.ref('structures','core:campfire')),rect,1.0)
        # Previously explored terrain remains as map memory, but anything
        # outside the current condition-driven sight circle is visibly subdued.
        # Entities/resources are never rendered through this memory fog.
        memory_fog=pg.Surface((cols*tile_px,rows*tile_px),pg.SRCALPHA)
        memory_dirty=False
        for sy in range(rows):
            wy=top+sy
            for sx in range(cols):
                wx=left+sx;pk=pos_key(wx,wy,pos.z)
                if pk in known and pk not in visible:
                    pg.draw.rect(memory_fog,(4,8,13,138),(sx*tile_px,sy*tile_px,tile_px,tile_px))
                    memory_dirty=True
        if memory_dirty:screen.blit(memory_fog,map_rect.topleft)

        # Roofs are recognizable static objects. Paint their whole silhouettes
        # after cell-exact terrain fog; otherwise LOS stopped by a solid facade
        # punches black tile-sized holes across the artwork. Discovery itself
        # and every live overlay above remain cell-exact and unchanged.
        if pos.z==0:
            draw_shells(self,building_shells,map_rect,left,top,tile_px,known,visible,
                        hit_regions=shell_hit_regions,
                        interior_plans=sim.state.interiors,
                        door_states={shell.door_uid:sim.property_security.door_by_id(shell.door_uid)
                                     for shell in building_shells if shell.door_uid})

        # Authoritative player cabins: the same ten PNG sprites as the Build
        # carousel, with precise physical doors and no invented hitboxes.
        if pos.z==0 and getattr(sim.state,'homesteads',None):
            from worldseed.systems.homestead_blueprints import footprint as home_cells, doorway as home_door
            from worldseed.ui.homestead_art import draw_cabin_art,doorway_edge_rect
            for project in sim.state.homesteads.values():
                if project['z']!=pos.z or not (left-5<=project['x']<=left+cols+3 and top-5<=project['y']<=top+rows+3):
                    continue
                cells=home_cells(project)
                discovered=[(wx,wy,wz) for wx,wy,wz in cells
                            if pos_key(wx,wy,wz) in known and _onscreen(wx,wy,wz)]
                if not discovered:continue
                seen=any(pos_key(*cell) in visible for cell in discovered)
                stage=int(project['stage'])
                # Foundation and deposit marker remain clearly visible while
                # the home is not yet far enough along to have a roof.
                if stage>=2:
                    opacity=(150,210,255)[min(2,stage-2)]
                    if not seen:opacity=min(opacity,145)
                    draw_cabin_art(self,project,grid_x=map_rect.x,grid_y=map_rect.y,
                                   left=left,top=top,size=tile_px,
                                   clip=used,opacity=opacity)
                if stage<=1:
                    for wx,wy,wz in discovered:
                        cell=pg.Rect(map_rect.x+(wx-left)*tile_px,
                                     map_rect.y+(wy-top)*tile_px,tile_px,tile_px)
                        ink=(104,177,196) if pos_key(wx,wy,wz) in visible else (73,92,94)
                        pg.draw.rect(screen,ink,cell.inflate(-4,-4),max(1,tile_px//13))
                    wx,wy,wz=cells[0]
                    if _onscreen(wx,wy,wz) and pos_key(wx,wy,wz) in known:
                        anchor=pg.Rect(map_rect.x+(wx-left)*tile_px,
                                       map_rect.y+(wy-top)*tile_px,tile_px,tile_px)
                        pg.draw.rect(screen,(237,224,174),pg.Rect(anchor.centerx-3,anchor.centery-9,6,18))
                        pg.draw.circle(screen,(230,221,178),
                                       (anchor.centerx,anchor.centery-9),max(2,tile_px//8))
                # A narrow physical threshold lies on the *actual* facing
                # edge. For all four orientations it is derived from doorway(),
                # not guessed from the art sprite's current apparent front.
                door_cell,_=home_door(project)
                if _onscreen(*door_cell) and pos_key(*door_cell) in known:
                    edge=doorway_edge_rect(pg,project,map_rect.x,map_rect.y,left,top,tile_px)
                    pg.draw.rect(screen,(244,199,105) if seen else (117,105,77),edge)

        # Actors remain exact visible foreground objects, never inferred from
        # a building's newly complete silhouette or remembered exterior.
        def _fractional_actor_rect(rect,fx,fy):
            try:
                ox=round((max(0.0,min(0.999,float(fx)))-0.5)*tile_px)
                oy=round((max(0.0,min(0.999,float(fy)))-0.5)*tile_px)
            except (TypeError,ValueError):
                ox=oy=0
            return rect.move(ox,oy)

        actor_keys=set(creature_by)|set(npc_by)|{(pos.x,pos.y,pos.z)}
        for wx,wy,wz in sorted(actor_keys,key=lambda key:(key[1],key[0])):
            k=(wx,wy,wz)
            if not _onscreen(wx,wy,wz) or pos_key(*k) not in visible:continue
            rect=pg.Rect(map_rect.x+(wx-left)*tile_px,map_rect.y+(wy-top)*tile_px,tile_px,tile_px)
            if k in creature_by:
                c=creature_by[k];ref=self._visuals.ref('species',c.species_id)
                ap=self._visuals.resolve(ref,self._stable_variant(c.uid,len(ref.paths))) if ref.paths else (proc_species[self._stable_variant(c.species_id+c.uid,len(proc_species))] if proc_species else None)
                self._draw_sprite_bottom(ap,rect,1.25)
            if k in npc_by:
                npc=npc_by[k]
                npc_rect=_fractional_actor_rect(rect,getattr(npc,'fx',0.5),getattr(npc,'fy',0.5))
                self._draw_sprite_bottom(self._npc_sprite_path(npc),npc_rect,1.45)
            if k==(pos.x,pos.y,pos.z):
                from worldseed.systems.swimming import exposure
                player_rect=_fractional_actor_rect(
                    rect,getattr(sim.state,'player_fx',0.5),getattr(sim.state,'player_fy',0.5)
                )
                if exposure(sim,pos).mode=='swimming':
                    saved=screen.get_clip();screen.set_clip(player_rect.move(0,-tile_px//2).inflate(0,-tile_px//3))
                    self._draw_sprite_bottom(player_sprite,player_rect.move(0,tile_px//3),1.45);screen.set_clip(saved)
                    pg.draw.ellipse(screen,(165,207,205),player_rect.inflate(-tile_px//4,-tile_px*2//3),1)
                else:self._draw_sprite_bottom(player_sprite,player_rect,1.45)
        if cursor is not None and _onscreen(cursor.x,cursor.y,cursor.z) and pos_key(cursor.x,cursor.y,cursor.z) in known:
            cp=self._load_sprite(cursor_sprite,tile_px,tile_px)
            if cp:screen.blit(cp,(map_rect.x+(cursor.x-left)*tile_px,map_rect.y+(cursor.y-top)*tile_px))

        # Weather/light presentation is observational and applies only to the
        # local world viewport. UI chrome remains fully readable at night.
        used=viewport.copy()
        if pos.z==0 and lighting is not None:
            now_ms=pg.time.get_ticks()
            previous=getattr(self,'_weather_animation_context',None)
            self._weather_fx.set_lighting(lighting,now_ms,reset=not previous or previous.get('seed')!=sim.seed or previous.get('lighting') is None)
            self._weather_static_snapshot=screen.subsurface(used).copy()
            self._weather_fx.draw_lighting(screen,used,lighting,elapsed_ms=now_ms)
            fire_rects=[]
            for (fx,fy,fz),fire in fire_by.items():
                if fz!=pos.z or fire.fuel<=0 or fire.intensity<=0:continue
                fire_rects.append((pg.Rect(
                    map_rect.x+(fx-left)*tile_px,map_rect.y+(fy-top)*tile_px,tile_px,tile_px
                ),int(getattr(fire,'intensity',60))))
            self._weather_fx.draw_fire_glows(screen,used,fire_rects,lighting)
            self._weather_fx.draw_atmosphere(
                screen,used,sim.seed,weather,world_left=left,world_top=top,
                tile_px=tile_px,elapsed_ms=now_ms,game_minute=sim.clock.minute,lighting=lighting)
        else:
            self._weather_static_snapshot=None
        # Stealth cones are drawn after lighting so the tactical information
        # remains legible at night. Generated settlement walls already clipped
        # the cells in StealthSystem, so the overlay cannot see through houses.
        if stealth_by:
            vision_layer=pg.Surface((cols*tile_px,rows*tile_px),pg.SRCALPHA)
            for (wx,wy,wz),cell in stealth_by.items():
                local=pg.Rect((wx-left)*tile_px,(wy-top)*tile_px,tile_px,tile_px)
                rgba=(196,70,58,42) if bool(cell.get('alert')) else (205,166,67,30)
                pg.draw.rect(vision_layer,rgba,local.inflate(-2,-2),border_radius=max(1,tile_px//8))
            screen.blit(vision_layer,map_rect.topleft)
            for uid,row in stealth_observers.items():
                wx,wy,wz=int(row.get('x',0)),int(row.get('y',0)),int(row.get('z',pos.z))
                if not _onscreen(wx,wy,wz):continue
                rect=pg.Rect(map_rect.x+(wx-left)*tile_px,map_rect.y+(wy-top)*tile_px,tile_px,tile_px)
                sees=bool(row.get('sees_player'))
                edge=self._theme['danger'] if sees else self._theme['accent']
                pg.draw.rect(screen,edge,rect.inflate(-2,-2),2,border_radius=max(1,tile_px//7))
                fx=int(row.get('facing_dx',0));fy=int(row.get('facing_dy',0))
                if fx or fy:
                    center=rect.center
                    end=(center[0]+fx*max(5,tile_px//3),center[1]+fy*max(5,tile_px//3))
                    pg.draw.line(screen,edge,center,end,3)
        # Combat range stays readable after world lighting/weather while its
        # translucent fill sits beneath sprites. Green is easier, red harder;
        # blocked cells use a neutral grey outline.
        if combat_by:
            selected=tuple(combat_overlay.get('cursor',())) if combat_overlay else ()
            for (wx,wy,wz),cell in combat_by.items():
                rect=pg.Rect(map_rect.x+(wx-left)*tile_px,map_rect.y+(wy-top)*tile_px,tile_px,tile_px)
                rgb=cell['rgb'];width=3 if (wx,wy,wz)==selected else 2
                pg.draw.rect(screen,rgb,rect.inflate(-2,-2),width,border_radius=max(1,tile_px//8))
        # Restore the screen clip before rendering the sidebar / footer.
        screen.set_clip(prior_world_clip)
        # frame map exactly to the fixed visible viewport.
        pg.draw.rect(screen,(78,91,91),used,1)

        # Hover inspection data is retained for the read_key() fast path.
        # Mouse movement no longer causes a complete game-frame rebuild.
        # Sidebar: information-dense but legible.
        tx=side_rect.x+16; ty=side_rect.y+14
        status_bottom=side_rect.bottom-186
        sidebar_clip=screen.get_clip()
        screen.set_clip(pg.Rect(side_rect.x+8,side_rect.y+6,side_rect.width-16,max(1,status_bottom-side_rect.y-6)))
        def text(s,color=None,font=None,gap=20):
            nonlocal ty
            f=font or self.small_font
            surf=f.render(self._fit_ui_text(str(s),f,side_rect.width-32),True,color or self._theme['text'])
            screen.blit(surf,(tx,ty)); ty+=gap
        text(sim.state.player_name,self._theme['accent'],self.title_font,28)
        text(sim.clock.label(),self._theme['muted'])
        if sim.combat_active():text('COMBAT PAUSED — act for 1 tick',self._theme['danger'])
        text(f"Position  {pos.x}, {pos.y}, z{pos.z}",self._theme['muted'],gap=26)
        for label,val,maxv in [('Health',vit.hp,vit.max_hp),('Stamina',vit.stamina,100),('Hunger',100-vit.hunger,100),('Hydration',100-vit.thirst,100)]:
            text(f"{label:<10} {val:>3}/{maxv:<3}",gap=17)
            bw=side_rect.width-32; frac=max(0,min(1,val/max(1,maxv))); pg.draw.rect(screen,(45,50,52),(tx,ty-1,bw,6),border_radius=2); pg.draw.rect(screen,self._theme['good'] if frac>.35 else self._theme['danger'],(tx,ty-1,int(bw*frac),6),border_radius=2); ty+=11
        ty+=6
        if vit.body_temp<20 or vit.body_temp>85:
            text(f'CRITICAL BODY TEMP {vit.body_temp}/100',self._theme['danger'],gap=18)
        if vit.blood<50:
            text(f'LOW BLOOD VOLUME {vit.blood}/100',self._theme['danger'],gap=18)
        if sim.state.player_infections:
            text('ACTIVE INFECTION - check Health',self._theme['danger'],gap=18)
        terrain=world.tile_at(pos).terrain.name; text('LOCAL',self._theme['accent'],gap=19); text(terrain); text(f"Carried stacks: {len(inv.items)}",self._theme['muted'])
        stance=str(getattr(sim.state,'player_hunting_stance','normal')).title()
        if stance!='Normal':text(f'Hunting stance: {stance}',self._theme['good'],gap=18)
        if combat_overlay:
            text('ATTACK RANGE',self._theme['accent'],gap=19)
            mode=str(combat_overlay.get('mode','attack')).title();weapon_name=str(combat_overlay.get('weapon_name','Weapon'))
            text(f'{mode} • {weapon_name}')
            text('Green easier  →  red harder',self._theme['muted'])
            diff=str(combat_overlay.get('cursor_difficulty','')).replace('_',' ').title()
            if diff:text(f'Cursor: {diff}',self._theme['muted'])
        if stealth_overlay and stealth_overlay.get('active'):
            seen=list(stealth_overlay.get('seen_by',()))
            text('STEALTH',self._theme['accent'],gap=19)
            if seen:
                text(f'EXPOSED • {len(seen)} observer{"s" if len(seen)!=1 else ""}',self._theme['danger'])
                for uid in seen[:3]:
                    npc=sim.state.npcs.get(uid)
                    label=npc.name if npc and uid in known_npcs else 'Stranger'
                    text(f'{label} sees you',self._theme['danger'],gap=17)
            else:
                text('Hidden from current observers',self._theme['good'])
            text(f'Stealth {sim.player_skill("stealth")} • movement quieter/slower',self._theme['muted'])
            structure_id=str(stealth_overlay.get('structure_id',''))
            structure=sim.settlement_physicalization.structure_by_id(structure_id) if structure_id else None
            if structure is not None:
                text(f'Inside: {str(structure.function).replace("_"," ").title()}',self._theme['muted'])
            security=stealth_overlay.get('security') or {}
            if security.get('trespassing'):
                text('TRESPASSING',self._theme['danger'],gap=19)
                level=int(security.get('search_level',0))
                text(
                    'Guard response: '+('active search' if level>=2 else 'warning / observation'),
                    self._theme['danger']
                )
        if pos.z==0 and lighting is not None:
            text('WEATHER',self._theme['accent'],gap=19)
            text(f"{str(weather.get('kind','clear')).title()}  Clouds {int(weather.get('cloud_cover',0))}%")
            text(f"Wet ground {int(weather.get('wetness',0))}%  •  {lighting.phase.title()}",self._theme['muted'])
            text(f"View radius {sim.visibility_radius(pos)} cells",self._theme['muted'])
        from worldseed.systems.swimming import exposure
        water=exposure(sim,pos)
        if water.mode!='dry':
            text(water.mode.upper(),self._theme['accent'])
            text(f"Swimming {sim.player_skill('swimming')} / Endurance {sim.player_attribute('endurance')}",self._theme['muted'])
            if vit.stamina<25 and water.mode=='swimming':text('EXHAUSTED - reach shore!',self._theme['danger'])
        # Nearby immediately visible entities only, no omniscient names.
        near=[]
        for c in creature_by.values():
            if abs(c.x-pos.x)+abs(c.y-pos.y)<=5:
                sp=registry.species.get(c.species_id); near.append(sp.name if sp else 'Creature')
        for n in npc_by.values():
            if abs(n.x-pos.x)+abs(n.y-pos.y)<=5:
                near.append(n.name if n.uid in known_npcs else 'Stranger')
        nearby_limit=min(7,max(0,(status_bottom-ty-27)//18))
        if near and nearby_limit:
            ty+=8; text('NEARBY',self._theme['accent'],gap=19)
            for n in near[:nearby_limit]: text('• '+n,self._theme['text'],gap=18)
        screen.set_clip(sidebar_clip)
        self._draw_hud_actions(side_rect,str(getattr(sim.state,'player_hunting_stance','normal')))

        # Footer keeps the recent world and player action history.
        msg=message or (sim.log[-1].message if sim.log else 'The world continues around you.')
        self._draw_footer(foot_rect,msg,sim)
        # Apply the presentation overlay before snapshotting the clean map.
        # The snapshot lets hover repaint only a few small rectangles while the
        # main loop is blocked waiting for the next gameplay input.
        self._draw_scanlines((ox,oy,ow,oh))
        self._play_combat_effects(sim,used,left,top,tile_px,pos.z)
        self._hover_context={
            'used':used.copy(),'grid_x':map_rect.x,'grid_y':map_rect.y,
            'tile_px':tile_px,'left':left,'top':top,'z':pos.z,
            'known':known,'visible':visible,'registry':registry,'world':world,'sim':sim,
            'creature_by':creature_by,'npc_by':npc_by,'structure_by':structure_by,
            'property_container_by':property_container_by,'settlement_by':settlement_by,'shell_by':shell_by,
            'shell_hit_regions':shell_hit_regions,
            'crop_by':crop_by,'pile_by':pile_by,'resource_by':resource_by,'known_npcs':known_npcs,
            'sign_by':sign_by,'home_by':home_by,
            'combat_by':combat_by,'stealth_by':stealth_by,
        }
        self._water_animation_cells=[]
        base=terrain_base
        for wr,display,dx,dy,speed in water_cells:
            cell=(left+(wr.x-map_rect.x)//tile_px,top+(wr.y-map_rect.y)//tile_px,pos.z)
            # Tall/wide sprites may extend into adjacent water rectangles.
            # Leave their entire neighborhood untouched during idle redraw.
            if any(hit['kind']=='body' and hit['rect'].colliderect(wr)
                   for hit in shell_hit_regions):continue
            if any((cell[0]+dx,cell[1]+dy,cell[2]) in overlay_keys
                   for dx in (-1,0,1) for dy in (-1,0,1)):continue
            local=wr.move(-map_rect.x,-map_rect.y)
            self._water_animation_cells.append((wr,base.subsurface(local).copy(),display,dx,dy,speed))
        self._water_animation_phase=water_phase
        self._weather_animation_context={
            'lighting':lighting if pos.z==0 else None,
            'fire_rects':fire_rects if pos.z==0 and lighting is not None else [],
            'fog':int(weather.get('fog',0)) if pos.z==0 else 0,
            'storm_intensity':int(weather.get('storm_intensity',0)) if pos.z==0 else 0,
            'minute':sim.clock.minute,
            'seed':sim.seed,'rain':int(weather.get('rain',0)) if pos.z==0 else 0,
            'wind_dx':int(weather.get('wind_dx',0)) if pos.z==0 else 0,
            'wind_dy':int(weather.get('wind_dy',0)) if pos.z==0 else 0,
            'cloud_cover':int(weather.get('cloud_cover',0)) if pos.z==0 else 0,
            'wetness':int(weather.get('wetness',0)) if pos.z==0 else 0,
            'night':bool(lighting is not None and lighting.phase=='night'),
            'left':left,'top':top,'tile_px':tile_px,
        }
        self._weather_animation_phase=None
        self._hover_map_snapshot=screen.subsurface(used).copy()
        self._hover_rect=None;self._hover_tile_rect=None;self._hover_cell=None
        self._refresh_hover_only(force=True,update_display=False)
        pg.display.flip(); self.clock.tick(120)
