from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def visible_len(text: str) -> int:
    return len(ANSI_RE.sub('', text))


def wrap_line(text: str, width: int) -> list[str]:
    width = max(8, width)
    if not text:
        return ['']
    return textwrap.wrap(str(text), width=width, replace_whitespace=False,
                         drop_whitespace=True, break_long_words=True,
                         break_on_hyphens=False) or ['']


def panel(title: str, body: list[str], width: int, footer: str = '') -> str:
    """Responsive ASCII panel. Width is an upper bound, never a minimum."""
    width = max(24, int(width))
    inner = max(20, width - 4)
    title_text = f' {title} '
    if len(title_text) > width - 2:
        title_text = title_text[:width - 5] + '...'
    out = ['+' + title_text.center(width - 2, '-') + '+']
    for raw in body:
        for line in wrap_line(str(raw), inner):
            out.append('| ' + line.ljust(inner) + ' |')
    if footer:
        out.append('+' + '-' * (width - 2) + '+')
        for line in wrap_line(footer, inner):
            out.append('| ' + line.ljust(inner) + ' |')
    out.append('+' + '-' * (width - 2) + '+')
    return '\n'.join(out)


@dataclass(frozen=True, slots=True)
class MenuRow:
    key: str
    label: str
    hint: str = ''


def _ui_key(raw: str) -> str:
    """Normalize widget keys. WASD belongs exclusively to world movement."""
    if raw in {"\x1b", "ESC", "Esc", "escape", "Escape"}:
        return "ESC"
    if len(raw) == 1 and raw.isalpha():
        return raw.lower()
    return raw


def select_menu(term, title: str, rows: list[tuple[str, str]] | list[MenuRow], *, allow_escape: bool = True,
                subtitle: str = '', initial: int = 0, breadcrumb: str = '', state=None,
                presentation: str = '', presentation_data: dict | None = None) -> str | None:
    """Arrow/Enter menu with paging and optional 1-9 quick selection.

    This is the primary navigation widget. It deliberately avoids requiring
    users to memorize numeric mappings; numbers are only optional shortcuts.
    """
    items = [r if isinstance(r, MenuRow) else MenuRow(r[0], r[1]) for r in rows]
    if not items:
        return None
    selected = max(0, min(len(items)-1, getattr(state, 'selected', initial) if state is not None else initial))
    while True:
        cols, lines = term.size()
        width = max(34, min(96, cols - 2))
        available = max(5, lines - 8)
        capacity=getattr(term,'menu_page_size',None)
        if callable(capacity):available=max(1,capacity(presentation))
        page_start = (selected // available) * available
        page_items = items[page_start:page_start + available]
        body = []
        if breadcrumb:
            body += [f'‹ {breadcrumb}', '']
        if subtitle:
            body += [subtitle, '']
        for idx, row in enumerate(page_items, start=page_start):
            marker = '>' if idx == selected else ' '
            quick = str(idx - page_start + 1) if idx - page_start < 9 else ' '
            text = f'{marker} {quick}. {row.label}'
            body.append(text)
            if idx == selected and row.hint:
                body.append(f'     {row.hint}')
        if len(items) > available:
            body += ['', f'{selected+1}/{len(items)}  Page {page_start//available + 1}/{(len(items)+available-1)//available}']
        footer = 'Click to select • Wheel to page • ↑/↓ and Enter optional' + (' • Esc back' if allow_escape else '')
        feature_graphical = getattr(term, 'present_feature_menu', None)
        graphical = getattr(term, 'present_menu', None)
        if presentation and callable(feature_graphical):
            feature_graphical(presentation, title, page_items, selected - page_start,
                              subtitle=subtitle, breadcrumb=breadcrumb, footer=footer,
                              page_start=page_start, total=len(items), data=presentation_data or {})
        elif callable(graphical):
            graphical(title, page_items, selected - page_start,
                      subtitle=subtitle, breadcrumb=breadcrumb, footer=footer,
                      page_start=page_start, total=len(items))
        else:
            term.present(panel(title, body, width, footer))
        k = _ui_key(term.read_key())
        if state is not None:
            state.selected = selected
        if k.startswith('UI_ACTION:'):
            return k
        if presentation=='inventory_unified':
            inventory_keys={
                'u':'UI_ACTION:use','x':'UI_ACTION:drop','h':'UI_ACTION:split',
                '[':'UI_ACTION:qty_down',']':'UI_ACTION:qty_up','m':'UI_ACTION:qty_all',
                'e':'UI_ACTION:store',
            }
            if k in inventory_keys:return inventory_keys[k]
        if presentation=='container_inventory':
            container_keys={
                't':'UI_ACTION:transfer','h':'UI_ACTION:split',
                '[':'UI_ACTION:qty_down',']':'UI_ACTION:qty_up','m':'UI_ACTION:qty_all',
                'x':'UI_ACTION:destroy',
            }
            if k in container_keys:return container_keys[k]
        if k.startswith(('UI_SELECT:','UI_HOVER:')):
            try:idx=page_start+int(k.split(':',1)[1])
            except ValueError:continue
            if page_start<=idx<page_start+len(page_items):
                selected=idx
                if state is not None:state.selected=selected
                if k.startswith('UI_SELECT:'):return items[selected].key
            continue
        if allow_escape and k in ('ESC', 'q'):
            return None
        if k in ('UP', 'k'):
            selected = (selected - 1) % len(items)
        elif k in ('DOWN', 'j'):
            selected = (selected + 1) % len(items)
        elif k == 'PGUP':
            selected = max(0, selected - available)
        elif k == 'PGDN':
            selected = min(len(items)-1, selected + available)
        elif k == 'HOME':
            selected = 0
        elif k == 'END':
            selected = len(items)-1
        elif k in ('\r', '\n', ' ', 'RIGHT'):
            return items[selected].key
        elif len(k) == 1 and k.isdigit() and k != '0':
            offset = int(k) - 1
            idx = page_start + offset
            if idx < len(items):
                return items[idx].key


def view_text(term, text: str, *, title: str = 'VIEW', breadcrumb: str = '', state=None,
              presentation: str = '', presentation_data: dict | None = None) -> None:
    """Terminal-safe pager. Reflows plain/framed text to the actual terminal."""
    raw_lines = text.splitlines() or ['']
    # Strip legacy box borders before reflow so a 112-column screen is useful
    # on an 80-column terminal instead of being clipped/wrapped by the shell.
    cleaned: list[str] = []
    inferred_title = title
    for i, line in enumerate(raw_lines):
        if i == 0 and line.startswith('+') and line.endswith('+'):
            middle = line[1:-1].strip('- ')
            if middle:
                inferred_title = middle
            continue
        if line.startswith('+') and line.endswith('+'):
            continue
        if line.startswith('| ') and line.endswith(' |'):
            line = line[2:-2].rstrip()
        cleaned.append(line)
    offset = max(0, int(getattr(state, 'scroll', 0)))
    while True:
        cols, rows = term.size()
        width = max(30, cols - 2)
        inner = max(20, width - 4)
        flowed: list[str] = []
        for line in cleaned:
            flowed.extend(wrap_line(line, inner))
        page_rows = max(5, rows - 5)
        capacity=getattr(term,'document_page_size',None)
        if callable(capacity):page_rows=capacity()
        max_offset = max(0, len(flowed) - page_rows)
        offset = max(0, min(offset, max_offset))
        if state is not None:
            state.scroll = offset
        chunk = flowed[offset:offset + page_rows]
        status = f'{offset+1}-{min(len(flowed), offset+page_rows)}/{max(1,len(flowed))}'
        if breadcrumb:
            chunk = [f'‹ {breadcrumb}', ''] + chunk
        footer=f'{status} • Wheel scrolls • Previous/Next page • Esc back'
        feature_graphical = getattr(term, 'present_feature_document', None)
        graphical = getattr(term, 'present_document', None)
        if presentation and callable(feature_graphical):
            feature_graphical(presentation, inferred_title, chunk, footer=footer, breadcrumb=breadcrumb,
                               data=presentation_data or {}, scroll_offset=offset, page_rows=page_rows,
                               total_lines=len(flowed))
        elif callable(graphical):
            graphical(inferred_title, chunk, footer=footer, breadcrumb=breadcrumb)
        else:
            term.present(panel(inferred_title, chunk, width, footer))
        k = _ui_key(term.read_key())
        if k in ('ESC', 'q', '\r', '\n'):
            return
        if k in ('UP',): offset -= 1
        elif k in ('DOWN',): offset += 1
        elif k == 'PGUP': offset -= page_rows
        elif k in ('PGDN', 'RIGHT'): offset += page_rows
        elif k == 'LEFT': offset -= page_rows
        elif k == 'HOME': offset = 0
        elif k == 'END': offset = max_offset


def prompt_text(term, title: str, label: str, *, default: str = "", max_len: int = 48, allow_blank: bool = True) -> str | None:
    """Single-line terminal text entry. ESC cancels; Enter accepts.

    Input is deliberately implemented inside the terminal abstraction so the
    new-game wizard does not leave alternate-screen/cbreak mode to call input().
    """
    value=list(default)
    while True:
        cols,_=term.size(); width=max(40,min(84,cols-2))
        shown=''.join(value)
        getattr(term,'present_text_entry',term.present)(panel(title,[label,'',f'> {shown}_','', 'Click Continue to accept or Back to cancel.'],width,'Type normally • Backspace deletes • Enter accepts'))
        k=term.read_key()
        if k in ('ESC',):return None
        if k in ('\r','\n'):
            out=''.join(value).strip()
            if out or allow_blank:return out
            continue
        if k in ('\x08','\x7f','BACKSPACE','\b'):
            if value:value.pop()
            continue
        if len(k)==1 and k.isprintable() and len(value)<max_len:
            value.append(k)
