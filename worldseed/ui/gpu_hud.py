"""GPU gameplay HUD and a small, observational controls window.

The backend owns presentation and events; these helpers never dispatch player
commands. Toolbar regions keep the shared router's existing command tokens.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.ui.presentation_style import draw_floating_panel_frame
from worldseed.ui.router import DIRECTIONS, HUD_BUTTONS, classify_key
from worldseed.ui.session import NavigationStack, RouteState
from worldseed.ui.terminal import pause_realtime_callback


@dataclass(frozen=True, slots=True)
class VitalBar:
    key: str
    label: str
    fraction: float
    color: tuple[int, int, int]
    detail: str


def vital_bars(vitals) -> tuple[VitalBar, ...]:
    """Read simulation values; hunger/thirst fills show remaining reserves."""
    hp = max(0, int(vitals.hp)); maximum = max(1, int(vitals.max_hp))
    hunger = max(0, min(100, int(vitals.hunger)))
    thirst = max(0, min(100, int(vitals.thirst)))
    stamina = max(0, min(100, int(vitals.stamina)))
    return (
        VitalBar('health', f'Health {hp}/{maximum}', min(1., hp / maximum),
                 (185, 75, 66), 'Health; empty means incapacitated'),
        VitalBar('stamina', f'Stamina {stamina}/100', stamina / 100.,
                 (116, 160, 91), 'Stamina available for movement and effort'),
        VitalBar('hunger', f'Hunger {100-hunger}/100', 1. - hunger / 100.,
                 (192, 151, 67), 'Food reserve; empties as hunger increases'),
        VitalBar('thirst', f'Thirst {100-thirst}/100', 1. - thirst / 100.,
                 (77, 143, 181), 'Water reserve; empties as thirst increases'),
    )


def _text(owner, text, point, *, color=None, width=None, font=None):
    font = font or owner.small_font
    if width is not None:
        text = owner._fit_ui_text(str(text), font, max(1, int(width)))
    owner.screen.blit(font.render(str(text), True, color or owner._theme['text']), point)


def _icon(owner, key, rect):
    from worldseed.ui.gpu_control_art import load_icon
    size = max(1, min(38, rect.width - 6, rect.height - 6))
    cache = getattr(owner, '_gpu_control_art_cache', None)
    if cache is None:
        cache = owner._gpu_control_art_cache = {}
    cache_key = (key, size)
    if cache_key not in cache:
        if len(cache) >= 64:
            cache.clear()
        cache[cache_key] = load_icon(owner.pg, key, size)
    surface = cache[cache_key]
    owner.screen.blit(surface, surface.get_rect(center=rect.center))


def draw_hud(owner, rect, sim, vitals):
    """Draw metadata, visible bars and shared command buttons within sidebar."""
    pg = owner.pg; screen = owner.screen; colors = owner._theme
    old_clip = screen.get_clip(); screen.set_clip(rect.clip(old_clip))
    pg.draw.rect(screen, colors['panel2'], rect)
    line = owner.small_font.get_height() + 5
    margin = min(10, max(3, rect.width // 14))
    x = rect.x + margin; usable = max(1, rect.width - margin * 2)
    y = rect.y + 9
    for text in (getattr(sim.state, 'player_name', 'Wanderer'), sim.clock.label(),
                 f'{sim.player_pos.x}, {sim.player_pos.y}, {sim.player_pos.z}'):
        _text(owner, text, (x, y), width=usable); y += line
    time_rect = pg.Rect(x, y, usable, 39)
    y += time_rect.height + 3
    # Preserve the controls at short supported sizes by reducing the meters'
    # whitespace, not by replacing their graphical tracks with numbers.
    meter_h = max(25, min(39, (rect.height - (y - rect.y) - 202) // 4))
    for meter in vital_bars(vitals):
        _text(owner, meter.label, (x, y), width=usable)
        track = pg.Rect(x, y + owner.small_font.get_height() + 2, usable, max(5, min(10, meter_h - line)))
        pg.draw.rect(screen, (12, 16, 18), track, border_radius=3)
        inner = track.inflate(-2, -2)
        fill = inner.copy(); fill.width = max(0, round(inner.width * meter.fraction))
        if fill.width:
            pg.draw.rect(screen, meter.color, fill, border_radius=2)
            if fill.height > 3:
                highlight = tuple(min(255, c + 30) for c in meter.color)
                pg.draw.line(screen, highlight, fill.topleft, (fill.right - 1, fill.top))
        pg.draw.rect(screen, colors['edge_hi'], track, 1, border_radius=3)
        owner._hud_tooltips.append((track, meter.label, meter.detail))
        y += meter_h
    controls = pg.Rect(rect.x, max(y + 7, rect.bottom - 202), rect.width,
                       max(1, rect.bottom - max(y + 7, rect.bottom - 202)))
    toolbar = draw_actions(owner, controls, str(getattr(sim.state, 'player_hunting_stance', 'normal')))
    # Append targets after the established action/stance regions; the time row
    # reads the session driver and emits tokens through the shared app router.
    draw_time_controls(owner, time_rect)
    screen.set_clip(old_clip)
    return toolbar


def draw_time_controls(owner, rect):
    """Show actual session pause/speed without advancing or changing its clock."""
    pg = owner.pg; colors = owner._theme; screen = owner.screen
    state = owner.read_time_controls()
    speed = max(1, min(3, state['speed']))
    paused = state['paused'] or state.get('held', False)
    _text(owner, f'TIME  {"Paused" if paused else "Running"} · {speed}×',
          (rect.x, rect.y), width=rect.width, color=colors['muted'])
    gap = 3; top = rect.y + owner.small_font.get_height() + 2
    width = max(1, (rect.width - gap * 3) // 4)
    for index, (label, token) in enumerate((('Pause', 'pause'), ('1×', '1'),
                                          ('2×', '2'), ('3×', '3'))):
        box = pg.Rect(rect.x + index * (width + gap), top, width,
                      max(1, rect.bottom - top)).clip(rect)
        chosen = paused if token == 'pause' else not paused and speed == int(token)
        pg.draw.rect(screen, (79, 70, 45) if chosen else colors['panel'], box, border_radius=3)
        pg.draw.rect(screen, colors['accent'] if chosen else colors['edge'], box,
                     2 if chosen else 1, border_radius=3)
        if token == 'pause' and owner.small_font.size(label)[0] > box.width - 4:
            label = 'Ⅱ'
        text = owner.small_font.render(owner._fit_ui_text(label, owner.small_font,
                                            max(1, box.width - 4)), True, colors['text'])
        screen.blit(text, text.get_rect(center=box.center))
        if owner._input_mode == 'world':
            owner._pointer_targets.append((box, 'UI_TIME:' + token))
        owner._hud_tooltips.append((box, label, 'Toggle pause [Space]' if token == 'pause'
                                   else f'Run world time at {token}× speed'))


def draw_actions(owner, rect, stance='normal'):
    """Art controls retain canonical tokens and accessible tooltip labels."""
    pg = owner.pg; screen = owner.screen; colors = owner._theme
    margin = min(8, max(2, rect.width // 15))
    bar = rect.inflate(-2 * margin, -8)
    if bar.width < 1 or bar.height < 1:
        return bar
    old_clip = screen.get_clip(); screen.set_clip(bar.clip(old_clip))
    pg.draw.rect(screen, (18, 23, 24), bar, border_radius=5)
    pg.draw.rect(screen, colors['edge'], bar, 1, border_radius=5)
    _text(owner, 'TOOLS & ACTIONS', (bar.x + 5, bar.y + 5), width=bar.width - 10, color=colors['accent'])
    gap = 3; inset = 5; columns = 5
    button_w = max(1, (bar.width - 2 * inset - 4 * gap) // columns)
    header = owner.small_font.get_height() + 12
    stance_h = min(54, max(23, bar.height // 3))
    button_h = max(1, min(43, (bar.height - header - stance_h - 14) // 2))
    buttons = HUD_BUTTONS if owner._input_mode == 'world' else (('Confirm', '\r'), ('Cancel', 'ESC'))
    for i, (name, token) in enumerate(buttons):
        box = pg.Rect(bar.x + inset + (i % columns) * (button_w + gap),
                      bar.y + header + (i // columns) * (button_h + gap), button_w, button_h).clip(bar)
        hover = box.collidepoint(owner._last_mouse)
        pg.draw.rect(screen, (52, 59, 54) if hover else colors['panel2'], box, border_radius=3)
        pg.draw.rect(screen, colors['accent'] if hover else colors['edge'], box, 1, border_radius=3)
        screen.set_clip(box.clip(old_clip))
        _icon(owner, name.lower(), box)
        if name == 'Help':
            # The literal mark makes the control immediately discoverable even
            # when its authored art is reduced to a tiny sidebar button.
            mark = owner.small_font.render('?', True, colors['text'])
            screen.blit(mark, (box.right - mark.get_width() - 2, box.y + 1))
        screen.set_clip(bar.clip(old_clip))
        owner._pointer_targets.append((box, token))
        key = {'\r': 'Enter', '\t': 'Tab', 'ESC': 'Esc'}.get(token, token.upper())
        owner._hud_tooltips.append((box, name, ('Movable controls window' if name == 'Help' else name) + f' [{key}]'))
    if owner._input_mode == 'world':
        y = bar.bottom - stance_h - 5
        pg.draw.line(screen, colors['edge'], (bar.x + 5, y - 4), (bar.right - 5, y - 4))
        _draw_stances(owner, pg.Rect(bar.x + inset, y, bar.width - inset * 2, stance_h), stance)
    owner._hud_tooltip_bounds = rect.copy()
    screen.set_clip(old_clip)
    return bar


def _draw_stances(owner, rect, active):
    pg = owner.pg; screen = owner.screen; colors = owner._theme
    details = (('normal', 'Normal', 'Normal movement; fastest'),
               ('stalk', 'Stalk', 'Stalk; quieter, enables theft'),
               ('crouch', 'Crouch', 'Crouch; quietest movement'),
               ('aggressive', 'Aggro', 'Aggressive stance; lockpicking and door bashing'))
    gap = 2; width = max(1, (rect.width - 3 * gap) // 4)
    for i, (key, name, detail) in enumerate(details):
        box = pg.Rect(rect.x + i * (width + gap), rect.y, width, rect.height).clip(rect)
        chosen = key == active
        pg.draw.rect(screen, (79, 70, 45) if chosen else colors['panel2'], box, border_radius=3)
        pg.draw.rect(screen, colors['accent'] if chosen else colors['edge'], box, 2 if chosen else 1, border_radius=3)
        icon_box = pg.Rect(box.x, box.y, box.width, max(1, box.height - 15))
        old_clip = screen.get_clip(); screen.set_clip(box.clip(old_clip))
        _icon(owner, key, icon_box)
        label = name if box.width >= owner.small_font.size(name)[0] + 4 else name[0]
        surface = owner.small_font.render(label, True, colors['text'] if chosen else colors['muted'])
        screen.blit(surface, surface.get_rect(center=(box.centerx, box.bottom - 9)))
        screen.set_clip(old_clip)
        owner._pointer_targets.append((box, 'UI_STANCE:' + key))
        owner._hud_tooltips.append((box, name + ' movement', detail))


def keybinding_rows():
    """Read primary controls from the router; do not establish a second map."""
    rows = [('Movement', ' / '.join(key.upper() for key in DIRECTIONS if len(key) == 1) + ' / arrows')]
    rows.extend((('World pause / resume', 'Space'), ('World speed', 'HUD 1× / 2× / 3×')))
    rows.extend((label, {'\r': 'Enter', '\t': 'Tab', 'ESC': 'Esc'}.get(token, token.upper()))
                for label, token in HUD_BUTTONS)
    for token, label, intent in (('g', 'Harvest / mine', 'gather'), ('p', 'Pick up', 'pickup'),
                                  ('.', 'Wait 10 minutes', 'wait'), ('>', 'Descend', 'vertical'),
                                  ('<', 'Ascend', 'vertical')):
        if classify_key(token).kind == intent:
            rows.append((label, token.upper()))
    rows.extend((('Zoom', 'Wheel / + / -'), ('Screenshot', 'F12'),
                 ('Move controls window', 'Drag title'), ('Close controls', 'Esc / ?')))
    return tuple(rows)


class _HelpWindow:
    def __init__(self, owner):
        self.navigation = NavigationStack(RouteState('world', 'World'))
        self.navigation.push(RouteState('keybindings', 'Controls'))
        self.rect = None
        self.drag = None
        self.close_rect = None
        self.pause = pause_realtime_callback(owner)
        self.pause.__enter__()


def help_popup_open(owner):
    return getattr(owner, '_gpu_help_window', None) is not None


def _clear_movement(owner):
    owner._held_movement.clear(); owner._active_movement_key = None
    owner._movement_next_repeat_ms = 0
    owner._free_movement_last_ms = owner.pg.time.get_ticks()


def open_help_popup(owner):
    if help_popup_open(owner):
        return
    _clear_movement(owner)
    owner._gpu_help_window = _HelpWindow(owner)


def close_help_popup(owner):
    window = getattr(owner, '_gpu_help_window', None)
    if window is None:
        return
    window.navigation.back()
    owner._gpu_help_window = None
    window.pause.__exit__(None, None, None)
    _clear_movement(owner)


def _help_rect(owner, window):
    pg = owner.pg; bounds = owner.screen.get_rect()
    inset = min(12, min(bounds.width, bounds.height) // 12)
    bounds = bounds.inflate(-2 * inset, -2 * inset)
    width = min(500, max(1, bounds.width * 3 // 4))
    height = min(430, max(1, bounds.height * 4 // 5))
    if window.rect is None:
        window.rect = pg.Rect(0, 0, width, height)
        window.rect.center = bounds.center
    else:
        window.rect.size = (width, height)
    window.rect.clamp_ip(bounds)
    return window.rect


def draw_help_popup(owner):
    """Paint over the GPU world; no full-screen backdrop or hidden reads."""
    window = getattr(owner, '_gpu_help_window', None)
    if window is None:
        return
    pg = owner.pg; screen = owner.screen; colors = owner._theme
    rect = _help_rect(owner, window)
    old_clip = screen.get_clip(); screen.set_clip(rect.clip(old_clip))
    draw_floating_panel_frame(pg, screen, rect, colors)
    _text(owner, '?  CONTROLS', (rect.x + 13, rect.y + 12), color=colors['accent'], width=rect.width - 65)
    close = window.close_rect = pg.Rect(rect.right - 34, rect.y + 7, 26, 26)
    pg.draw.rect(screen, colors['panel'], close, border_radius=3)
    _text(owner, '×', (close.x + 6, close.y + 3))
    content = pg.Rect(rect.x + 14, rect.y + 53, max(1, rect.width - 28), max(1, rect.height - 88))
    row_h = owner.small_font.get_height() + 9
    capacity = max(1, content.height // row_h)
    rows = keybinding_rows(); route = window.navigation.current
    route.scroll = max(0, min(route.scroll, max(0, len(rows) - capacity)))
    screen.set_clip(content.clip(old_clip))
    left_width = min(220, content.width * 3 // 5)
    for i, (label, key) in enumerate(rows[route.scroll:route.scroll + capacity]):
        y = content.y + i * row_h
        if i % 2 == 0:
            pg.draw.rect(screen, (28, 34, 34), (content.x, y - 2, content.width, row_h))
        _text(owner, label, (content.x + 3, y), width=left_width - 8)
        _text(owner, key, (content.x + left_width, y), width=content.width - left_width - 3, color=colors['accent'])
    screen.set_clip(rect.clip(old_clip))
    _text(owner, 'Drag title · Wheel scrolls · Esc closes · Paused',
          (rect.x + 13, rect.bottom - 25), width=rect.width - 26, color=colors['muted'])
    if len(rows) > capacity:
        scrollbar = pg.Rect(rect.right - 9, content.y, 3, content.height)
        pg.draw.rect(screen, colors['edge'], scrollbar)
        thumb_h = max(12, scrollbar.height * capacity // len(rows))
        thumb_y = scrollbar.y + round((scrollbar.height - thumb_h) * route.scroll / max(1, len(rows) - capacity))
        pg.draw.rect(screen, colors['accent'], (scrollbar.x, thumb_y, 3, thumb_h))
    screen.set_clip(old_clip)


def handle_hud_event(owner, event):
    """Consume controls-window input before normal movement/menu routing."""
    pg = owner.pg; window = getattr(owner, '_gpu_help_window', None)
    question = event.type == pg.KEYDOWN and getattr(event, 'unicode', '') == '?'
    if window is None:
        if getattr(owner, '_input_mode', None) != 'world':
            return False
        help_click = (event.type == pg.MOUSEBUTTONDOWN and event.button == 1 and
                      any(token == '?' and rect.collidepoint(event.pos) for rect, token in owner._pointer_targets))
        if question or help_click:
            open_help_popup(owner)
            return True
        return False
    if event.type == pg.KEYDOWN:
        if question or event.key == pg.K_ESCAPE:
            close_help_popup(owner)
        elif event.key in (pg.K_DOWN, pg.K_PAGEDOWN):
            window.navigation.current.scroll += 1 if event.key == pg.K_DOWN else 8
        elif event.key in (pg.K_UP, pg.K_PAGEUP):
            window.navigation.current.scroll = max(0, window.navigation.current.scroll - (1 if event.key == pg.K_UP else 8))
        return True
    if event.type == pg.KEYUP:
        return True
    if event.type == pg.MOUSEBUTTONDOWN:
        point = getattr(event, 'pos', owner._last_mouse)
        rect = _help_rect(owner, window)
        if event.button == 1:
            if window.close_rect is not None and window.close_rect.collidepoint(point):
                close_help_popup(owner)
            elif pg.Rect(rect.x, rect.y, rect.width, 42).collidepoint(point):
                window.drag = (point[0] - rect.x, point[1] - rect.y)
        elif event.button in (4, 5):
            window.navigation.current.scroll = max(0, window.navigation.current.scroll + (-1 if event.button == 4 else 1))
        return True
    if event.type == pg.MOUSEBUTTONUP:
        if event.button == 1:
            window.drag = None
        return True
    if event.type == pg.MOUSEMOTION:
        owner._last_mouse = event.pos
        if window.drag is not None:
            rect = _help_rect(owner, window)
            rect.topleft = (event.pos[0] - window.drag[0], event.pos[1] - window.drag[1])
            rect.clamp_ip(owner.screen.get_rect().inflate(-24, -24))
        return True
    if event.type == pg.MOUSEWHEEL:
        window.navigation.current.scroll = max(0, window.navigation.current.scroll - event.y)
        return True
    if event.type == getattr(pg, 'WINDOWFOCUSLOST', -1):
        window.drag = None
    return False
