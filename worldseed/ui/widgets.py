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
    width = max(8, int(width))
    inner = max(4, width - 4)
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


def _dialogue_terminal_page(data: dict, width: int, height: int, choice_rows: int) -> list[str]:
    """Reflow the complete spoken thread for the terminal fallback.

    Topic links also appear in the ordinary arrow/Enter choices. Text paging
    uses the same route scroll as the graphical backend and never consumes a
    gameplay key. Only the current utterance is paged; earlier ones remain on
    their retained parent routes.
    """
    inner=max(8,width-4)
    path=' > '.join(str(row.get('label','')) for row in data.get('path',()))
    heading=str(data.get('role',''))+' · '+str(data.get('topic_label') or data.get('topic','Conversation'))
    body=[heading[:inner]]
    if path:body.append(('‹ '+path)[-inner:])
    spans=data.get('spans') or ()
    focus=data.get('focused_topic','')
    text=''.join(('['+str(span.get('text',''))+']' if span.get('topic')==focus else '‹'+str(span.get('text',''))+'›')
                 if span.get('topic') else str(span.get('text','')) for span in spans) if spans else str(data.get('opening') or '')
    response=str(data.get('response') or '')
    if response:text+=('\n\n' if text else '')+response
    flowed=[]
    for paragraph in text.splitlines():flowed.extend(wrap_line(paragraph,inner))
    if not flowed:flowed=['...']
    # Reserve borders/footer, topic choices, choice paging and text status.
    capacity=max(1,height-7-len(body)-choice_rows)
    pages=max(1,(len(flowed)+capacity-1)//capacity)
    page=min(pages-1,max(0,int(data.get('transcript_page',0))))
    data['transcript_page']=page;data['transcript_pages']=pages
    body.extend(flowed[page*capacity:(page+1)*capacity])
    body.append(f'Text {page+1}/{pages} [ / ]')
    body.append('Topics / actions:')
    return body


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
    focused_topic=''
    retained_items=presentation in {'inventory_unified','container_inventory','crafting_unified',
                                      'workshop_station','discovery_pot','salvaging_unified'}
    viewport_start=max(0,int(getattr(state,'scroll',0))) if state is not None else None
    while True:
        cols, lines = term.size()
        width = max(8, min(96, cols - 2))
        available = max(5, lines - 8)
        feature_graphical = getattr(term, 'present_feature_menu', None)
        graphical = getattr(term, 'present_menu', None)
        shown_breadcrumb=breadcrumb
        if breadcrumb and not callable(feature_graphical) and not callable(graphical):
            inner=width-4
            shown_breadcrumb=breadcrumb if len('‹ '+breadcrumb)<=inner else '…'+breadcrumb[-max(1,inner-3):]
        terminal_dialogue=presentation=='npc_dialogue' and not callable(feature_graphical) and not callable(graphical)
        if terminal_dialogue:
            width=max(24,min(96,cols-2))
            available=max(1,(lines-10)//3)
        capacity=getattr(term,'menu_page_size',None)
        if callable(capacity):available=max(1,capacity(presentation))
        if not callable(feature_graphical) and not callable(graphical) and not terminal_dialogue:
            # Reflowed labels consume real lines; paging by row count alone
            # made the large crafting catalogue overflow narrow terminals.
            inner=width-4
            footer_text='Click • ↑↓ Enter • Esc back' if presentation=='salvaging' else 'Click to select • Wheel to page • ↑/↓ and Enter optional'+(' • Esc back' if allow_escape else '')
            chrome=3+len(wrap_line(footer_text,inner))
            if shown_breadcrumb:chrome+=len(wrap_line('‹ '+shown_breadcrumb,inner))+1
            if subtitle:chrome+=len(wrap_line(subtitle,inner))+1
            if len(items)>1:chrome+=2
            row_cost=max(len(wrap_line(f'> 9. {row.label}',inner))+ (len(wrap_line('     '+row.hint,inner)) if row.hint else 0) for row in items)
            available=max(1,(lines-chrome)//max(1,row_cost))
        grid_columns=getattr(term,'menu_grid_columns',None)
        grid_columns=max(1,int(grid_columns(presentation))) if retained_items and callable(grid_columns) else 1
        max_scroll=max(0,len(items)-available)
        if retained_items:
            if viewport_start is None:viewport_start=(selected//available)*available
            viewport_start=max(0,min(viewport_start,max_scroll))
            page_start=viewport_start
            if state is not None:state.scroll=viewport_start
        else:
            page_start=(selected//available)*available
        page_items=items[page_start:page_start+available]
        visible_selected=selected-page_start if page_start<=selected<page_start+len(page_items) else -1
        frame_data=presentation_data or {}
        if retained_items:
            # The selected row can remain outside the scrolled viewport. Details
            # and actions must still resolve that exact row rather than row zero.
            frame_data=dict(frame_data,selected_key=items[selected].key)
        if presentation=='npc_dialogue' and presentation_data is not None:
            presentation_data['focused_topic']=focused_topic
        body = []
        if terminal_dialogue:
            body=_dialogue_terminal_page(presentation_data or {},width,lines,len(page_items))
        elif shown_breadcrumb:
            body += [f'‹ {shown_breadcrumb}', '']
        if subtitle and not terminal_dialogue:
            body += [subtitle, '']
        for idx, row in enumerate(page_items, start=page_start):
            marker = '>' if idx == selected else ' '
            quick = str(idx - page_start + 1) if idx - page_start < 9 else ' '
            text = f'{marker} {quick}. {row.label}'
            if terminal_dialogue and len(text)>width-4:text=text[:width-5]+'…'
            body.append(text)
            if idx == selected and row.hint and not terminal_dialogue:
                body.append(f'     {row.hint}')
        if len(items) > available:
            status=f'{selected+1}/{len(items)}  Page {page_start//available + 1}/{(len(items)+available-1)//available}'
            body += [status] if terminal_dialogue else ['',status]
        footer = 'Click to select • Wheel to page • ↑/↓ and Enter optional' + (' • Esc back' if allow_escape else '')
        if presentation=='salvaging' and not callable(feature_graphical):footer='Click • ↑↓ Enter • Esc back'
        if presentation=='npc_dialogue':
            if terminal_dialogue:footer='Tab/↑↓ Enter Esc'
        if presentation and callable(feature_graphical):
            feature_graphical(presentation, title, page_items, visible_selected,
                              subtitle=subtitle, breadcrumb=breadcrumb, footer=footer,
                              page_start=page_start, total=len(items), data=frame_data)
        elif callable(graphical):
            graphical(title, page_items, visible_selected,
                      subtitle=subtitle, breadcrumb=breadcrumb, footer=footer,
                      page_start=page_start, total=len(items))
        else:
            term.present(panel(title, body, width, footer))
        k = _ui_key(term.read_key())
        if state is not None:
            state.selected = selected
        if k in {'UI_REDRAW','RESIZE'}:
            continue
        if presentation in {
            'inventory_unified','container_inventory','crafting_unified',
            'workshop_station','discovery_pot','crafting_index','salvaging','salvaging_unified'
        } and (k==' ' or k.startswith('UI_TIME:')):
            clock_input=getattr(term,'handle_time_control',None)
            if callable(clock_input) and clock_input(k):continue
        if retained_items and k.startswith(('UI_SCROLL:','UI_WHEEL:')):
            try:value=int(k.split(':',1)[1])
            except ValueError:continue
            viewport_start=value if k.startswith('UI_SCROLL:') else page_start+value
            viewport_start=max(0,min(viewport_start,max_scroll))
            if state is not None:state.scroll=viewport_start
            continue
        if retained_items and k.startswith('UI_HOVER:'):
            # Hover is presentation feedback, never a change of action target.
            continue
        if presentation=='npc_dialogue' and k in {'\t','TAB'}:
            topics=list(dict.fromkeys(str(span.get('topic','')) for span in (presentation_data or {}).get('spans',()) if span.get('topic')))
            if topics:
                focused_topic=topics[(topics.index(focused_topic)+1)%len(topics)] if focused_topic in topics else topics[0]
            continue
        if presentation=='npc_dialogue' and focused_topic and k in {'\r','\n',' ','RIGHT'}:
            return 'UI_ACTION:topic:'+focused_topic
        if k in {'UP','DOWN','HOME','END','PGUP','PGDN'} or k.startswith(('UI_SELECT:','UI_HOVER:')):
            focused_topic=''
        if presentation=='npc_dialogue' and k in {'[',']'}:
            return 'UI_ACTION:transcript_previous' if k=='[' else 'UI_ACTION:transcript_next'
        if k.startswith('UI_CONTEXT:'):
            try:idx=page_start+int(k.split(':',1)[1])
            except ValueError:continue
            if page_start<=idx<page_start+len(page_items):
                selected=idx
                if state is not None:state.selected=selected
            continue
        if k.startswith('UI_SHIFT_SELECT:'):
            try:idx=page_start+int(k.split(':',1)[1])
            except ValueError:continue
            if page_start<=idx<page_start+len(page_items):
                selected=idx
                if state is not None:state.selected=selected
                if presentation=='container_inventory':return 'UI_ACTION:quick_transfer'
                if presentation=='inventory_unified' and bool((presentation_data or {}).get('near_storage')):
                    return 'UI_ACTION:quick_store'
            continue
        # Retained gameplay panels do not pause world movement. WASD is
        # forwarded to the gameplay owner while arrows/Enter remain UI navigation.
        if presentation in {
            'inventory_unified','container_inventory','crafting_unified',
            'workshop_station','discovery_pot','crafting_index','salvaging','salvaging_unified'
        } and k in {'w','a','s','d'}:
            return f'UI_WORLD_MOVE:{k}'
        if k.startswith('UI_ACTION:'):
            return k
        if presentation=='salvaging_unified':
            if k=='b':return 'UI_ACTION:salvage:begin'
            if k in {'1','2','3'}:
                choices=((frame_data.get('active_session') or {}).get('choices') or [])
                index=int(k)-1
                if index<len(choices):return 'UI_ACTION:salvage:act:'+choices[index]['id']
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
                if k.startswith('UI_SELECT:'):
                    if state is not None:state.selected=selected
                    return items[selected].key
            continue
        if allow_escape and k in ('ESC', 'q'):
            return None
        previous_selected=selected
        if retained_items and grid_columns>1 and k in {'LEFT','RIGHT'}:
            selected=max(0,min(len(items)-1,selected+(-1 if k=='LEFT' else 1)))
        elif k in ('UP', 'k'):
            selected=max(0,selected-grid_columns) if retained_items else (selected-1)%len(items)
        elif k in ('DOWN', 'j'):
            selected=min(len(items)-1,selected+grid_columns) if retained_items else (selected+1)%len(items)
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
            if idx < page_start+len(page_items):
                if state is not None:state.selected=idx
                return items[idx].key
        if retained_items and (selected!=previous_selected or k in {'UP','DOWN','LEFT','RIGHT','HOME','END','PGUP','PGDN'}):
            if selected<page_start:
                viewport_start=selected-(selected%grid_columns)
            elif selected>=page_start+available:
                viewport_start=selected-available+grid_columns
                viewport_start-=viewport_start%grid_columns
            viewport_start=max(0,min(viewport_start,max_scroll))
            if state is not None:
                state.selected=selected
                state.scroll=viewport_start


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
        cols,_=term.size(); width=max(8,min(84,cols-2))
        shown=''.join(value)
        field=getattr(term,'present_text_field',None)
        if callable(field):
            field(title,label,shown,max_len=max_len,allow_blank=allow_blank)
        else:
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
