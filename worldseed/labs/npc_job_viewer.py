"""An observational pygame workbench for the separate NPC job laboratory.

The renderer consumes detached snapshots. Only the explicit viewer controls call
``step`` or construct a replacement lab; drawing and inspecting never run AI.
Pygame is deliberately confined to this optional presentation module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

import pygame


BG = (15, 22, 30)
PANEL = (23, 33, 43)
EDGE = (46, 61, 73)
TEXT = (224, 232, 236)
MUTED = (143, 163, 176)
ACCENT = (109, 224, 183)
GOLD = (237, 195, 113)
RED = (237, 133, 123)
JOB_COLORS = {
    "lumberjack": (111, 222, 163),
    "carpenter": (231, 177, 116),
    "miner": (166, 184, 214),
    "smith": (238, 148, 125),
    "blacksmith": (238, 148, 125),
    "farmer": (189, 209, 123),
    "cook": (223, 160, 214),
    "merchant": (130, 195, 239),
    "hauler": (162, 171, 230),
}
SPEEDS = (1, 4, 12, 30)


@lru_cache(maxsize=12)
def _font(size: int, bold: bool = False) -> pygame.font.Font:
    if not pygame.font.get_init():
        pygame.font.init()
    return pygame.font.SysFont("dejavusans", size, bold=bold)


def _label(value: Any) -> str:
    return str(value).split(":")[-1].replace("_", " ")


def _location_uid(kind: str, item: dict[str, Any]) -> str:
    """Identify position-owned records in the detached inspector only."""
    return f"{kind}:{item['x']}:{item['y']}:{item.get('z', 0)}"


def _time(minute: int) -> str:
    day, within = divmod(int(minute), 1440)
    hour, minute = divmod(within, 60)
    return f"Day {day + 1} {hour:02d}:{minute:02d}"


def _wrap(value: Any, width: int, font: pygame.font.Font) -> list[str]:
    """Wrap long IDs as well as prose without losing any inspector text."""
    if width < 1:
        return []
    lines: list[str] = []
    for paragraph in str(value).splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if font.size(candidate)[0] <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for character in word:
                if line and font.size(line + character)[0] > width:
                    lines.append(line)
                    line = ""
                line += character
        lines.append(line)
    return lines


@dataclass
class HitRegion:
    rect: pygame.Rect
    action: str
    value: Any = None


@dataclass
class FrameLayout:
    """Presentation hit regions rebuilt from the current snapshot every frame."""

    hits: list[HitRegion] = field(default_factory=list)
    inspector: pygame.Rect | None = None
    events: pygame.Rect | None = None
    inspector_max_scroll: int = 0
    events_max_scroll: int = 0


class _Renderer:
    def __init__(
        self,
        surface: pygame.Surface,
        snapshot: dict[str, Any],
        selected_uid: str | None,
        *,
        running: bool = False,
        speed: int = 1,
        inspector_scroll: int = 0,
        events_scroll: int = 0,
        compact_tab: str = "inspect",
        status: str = "",
        hover: tuple[int, int] | None = None,
    ) -> None:
        self.surface, self.snapshot = surface, snapshot
        npcs = snapshot.get("npcs", [])
        self.selected_uid = selected_uid or (npcs[0]["uid"] if npcs else None)
        self.running, self.speed = running, speed
        self.inspector_scroll, self.events_scroll = inspector_scroll, events_scroll
        self.compact_tab, self.status, self.hover = compact_tab, status, hover
        self.layout = FrameLayout()
        self.regular, self.small = _font(13), _font(11)
        self.title, self.section = _font(22, True), _font(12, True)
        self.tooltip: list[str] = []

    def text(
        self, value: Any, position: tuple[int, int], color: tuple[int, int, int] = TEXT,
        font: pygame.font.Font | None = None, width: int | None = None,
    ) -> None:
        rendered = (font or self.regular).render(str(value), True, color)
        if width is not None and rendered.get_width() > width:
            rendered = rendered.subsurface((0, 0, max(0, width), rendered.get_height()))
        self.surface.blit(rendered, position)

    def panel(self, rect: pygame.Rect, heading: str) -> None:
        pygame.draw.rect(self.surface, PANEL, rect, border_radius=8)
        pygame.draw.rect(self.surface, EDGE, rect, width=1, border_radius=8)
        self.text(heading, (rect.x + 12, rect.y + 10), MUTED, self.section, rect.width - 24)

    def button(self, rect: pygame.Rect, label: str, action: str, value: Any = None, active: bool = False) -> None:
        hovered = self.hover is not None and rect.collidepoint(self.hover)
        color = (49, 73, 76) if active else ((44, 59, 73) if hovered else PANEL)
        pygame.draw.rect(self.surface, color, rect, border_radius=5)
        pygame.draw.rect(self.surface, ACCENT if active else EDGE, rect, width=1, border_radius=5)
        rendered = self.small.render(label, True, ACCENT if active else TEXT)
        self.surface.blit(rendered, rendered.get_rect(center=rect.center))
        self.layout.hits.append(HitRegion(rect, action, value))

    def draw(self) -> FrameLayout:
        self.surface.fill(BG)
        width, height = self.surface.get_size()
        margin = 12 if width >= 600 else 7
        self.text("NPC JOB LAB", (margin, 10), TEXT, self.title, width - margin * 2)
        state = "RUNNING" if self.running else "PAUSED"
        if width >= 600:
            self.text(state, (width - 106, 17), ACCENT if self.running else GOLD, self.section)
        meta = f"{_label(self.snapshot.get('scenario', ''))}  |  seed: {self.snapshot.get('seed', '')}"
        self.text(meta, (margin, 39), MUTED, self.small, width - margin * 2)
        self.text(f"{_time(self.snapshot.get('minute', 0))}  |  minute {self.snapshot.get('minute', 0)}  |  {state.lower()}",
                  (margin, 57), ACCENT, self.small, width - margin * 2)
        controls = [
            ("Pause [Space]" if self.running else "Run [Space]", "toggle", None, self.running),
            ("Step [Right]", "step", None, False),
            ("-", "slower", None, False),
            (f"{self.speed} ticks/s +", "faster", None, False),
            ("Scenario [C]", "scenario", None, False),
            ("Reset [R]", "reset", None, False),
            ("Export [E]", "export", None, False),
        ]
        x, y = margin, 80
        for label, action, value, active in controls:
            button_width = self.small.size(label)[0] + 20
            if x + button_width > width - margin and x > margin:
                x, y = margin, y + 34
            rect = pygame.Rect(x, y, min(button_width, width - margin * 2), 28)
            self.button(rect, label, action, value, active)
            x += button_width + 6
        content_y = y + 39
        footer = 28 if height >= 360 else 0
        available_height = max(1, height - content_y - margin - footer)
        if width >= 840:
            side_width = min(370, max(300, width // 3))
            left_width = width - margin * 3 - side_width
            event_height = min(186, max(94, available_height // 3))
            map_rect = pygame.Rect(margin, content_y, left_width, max(1, available_height - event_height - 10))
            event_rect = pygame.Rect(margin, map_rect.bottom + 10, left_width, event_height)
            inspector_rect = pygame.Rect(map_rect.right + margin, content_y, side_width, available_height)
            self.draw_map(map_rect)
            self.draw_events(event_rect)
            self.draw_inspector(inspector_rect)
        else:
            map_height = max(42, (available_height - 38) // 2)
            map_height = min(map_height, max(1, available_height - 37))
            map_rect = pygame.Rect(margin, content_y, width - margin * 2, map_height)
            self.draw_map(map_rect)
            tab_y = map_rect.bottom + 6
            tab_width = max(1, (width - margin * 2 - 6) // 2)
            self.button(pygame.Rect(margin, tab_y, tab_width, 27), "Inspect [I]", "tab", "inspect", self.compact_tab == "inspect")
            self.button(pygame.Rect(margin + tab_width + 6, tab_y, tab_width, 27), "Events [L]", "tab", "events", self.compact_tab == "events")
            detail = pygame.Rect(margin, tab_y + 33, width - margin * 2, max(1, content_y + available_height - tab_y - 33))
            if self.compact_tab == "events":
                self.draw_events(detail)
            else:
                self.draw_inspector(detail)
        if footer:
            hint = self.status or "Click an NPC or storage to inspect.  Tab: next NPC  |  Wheel / PgUp / PgDn: scroll  |  Esc: exit"
            self.text(hint, (margin, height - 21), MUTED, self.small, width - margin * 2)
        if self.tooltip and self.hover:
            self.draw_tooltip()
        return self.layout

    def draw_map(self, rect: pygame.Rect) -> None:
        metrics = self.snapshot.get("metrics", {})
        self.panel(rect, "WORKSITE  /  exact positions")
        stats = (f"{len(self.snapshot.get('npcs', []))} workers    "
                 f"{metrics.get('completed_activities', 0)} activities    "
                 f"{metrics.get('transfers', 0)} transfers    "
                 f"{metrics.get('transactions', 0)} trades    "
                 f"cash delta {metrics.get('cash_delta', 0):+}")
        if rect.height >= 70:
            self.text(stats, (rect.x + 12, rect.y + 30), ACCENT, self.small, rect.width - 24)
        old_clip = self.surface.get_clip()
        self.surface.set_clip(rect.inflate(-12, -12))
        xmin, ymin, xmax, ymax = self.snapshot.get("bounds", [-32, -24, 32, 24])
        columns, rows = max(1, xmax - xmin + 1), max(1, ymax - ymin + 1)
        map_space = pygame.Rect(rect.x + 15, rect.y + (54 if rect.height >= 100 else 29), rect.width - 30, max(1, rect.height - (78 if rect.height >= 100 else 35)))
        scale = max(0.1, min(max(1, map_space.width) / columns, max(1, map_space.height) / rows))
        origin_x = map_space.centerx - columns * scale / 2
        origin_y = map_space.centery - rows * scale / 2

        def position(x: float, y: float) -> tuple[int, int]:
            return round(origin_x + (x - xmin + 0.5) * scale), round(origin_y + (y - ymin + 0.5) * scale)

        floor = pygame.Rect(round(origin_x), round(origin_y), max(1, round(columns * scale)), max(1, round(rows * scale)))
        pygame.draw.rect(self.surface, (29, 43, 47), floor)
        for x in range(xmin, xmax + 2, 4):
            px = round(origin_x + (x - xmin) * scale)
            pygame.draw.line(self.surface, (38, 53, 56), (px, floor.top), (px, floor.bottom))
        for y in range(ymin, ymax + 2, 4):
            py = round(origin_y + (y - ymin) * scale)
            pygame.draw.line(self.surface, (38, 53, 56), (floor.left, py), (floor.right, py))
        for x, y in self.snapshot.get("blocked", []):
            point = position(x, y)
            pygame.draw.rect(self.surface, (80, 87, 91), pygame.Rect(point[0] - scale / 2, point[1] - scale / 2, max(1, scale), max(1, scale)))
        for crop in self.snapshot.get("crops", []):
            point = position(crop["x"], crop["y"])
            radius = max(2, round(scale * 0.45))
            crop_rect = pygame.Rect(point[0] - radius, point[1] - radius, radius * 2, radius * 2)
            pygame.draw.rect(self.surface, GOLD if crop.get("mature") else (95, 160, 105), crop_rect)
            uid = _location_uid("crop", crop)
            self.map_hit(crop_rect.inflate(4, 4), uid, [_label(crop.get("crop_id", "crop")), "Mature" if crop.get("mature") else f"Growth {crop.get('growth', 0)}"])
            if uid == self.selected_uid:
                pygame.draw.rect(self.surface, ACCENT, crop_rect.inflate(4, 4), 1)
        for pile in self.snapshot.get("piles", []):
            point = position(pile["x"], pile["y"])
            radius = max(3, round(scale * 0.55))
            pile_rect = pygame.Rect(point[0] - radius, point[1] - radius, radius * 2, radius * 2)
            pygame.draw.polygon(self.surface, (203, 160, 94), [pile_rect.midtop, pile_rect.bottomright, pile_rect.bottomleft])
            uid = _location_uid("pile", pile)
            self.map_hit(pile_rect.inflate(4, 4), uid, ["Ground goods", f"{sum(pile.get('items', {}).values())} items"])
            if uid == self.selected_uid:
                pygame.draw.rect(self.surface, ACCENT, pile_rect.inflate(4, 4), 1)
        for tree in self.snapshot.get("trees", []):
            point = position(tree["x"], tree["y"])
            mature = tree.get("stage") != "stump"
            radius = max(2, round(scale * (0.65 if mature else 0.3)))
            pygame.draw.circle(self.surface, (72, 127, 91) if mature else (145, 111, 82), point, radius)
            if mature:
                pygame.draw.circle(self.surface, (101, 163, 113), (point[0] - 1, point[1] - 1), max(1, radius // 2))
        for fixture in self.snapshot.get("fixtures", []):
            point = position(fixture["x"], fixture["y"])
            radius = max(3, round(scale * 0.68))
            fixture_rect = pygame.Rect(point[0] - radius, point[1] - radius, radius * 2, radius * 2)
            pygame.draw.rect(self.surface, (143, 147, 172), fixture_rect, border_radius=2)
            self.map_hit(fixture_rect.inflate(6, 6), fixture["uid"], [fixture.get("label", fixture["uid"]), f"Station at {fixture['x']}, {fixture['y']}"])
            if fixture["uid"] == self.selected_uid:
                pygame.draw.rect(self.surface, ACCENT, fixture_rect.inflate(6, 6), 2, border_radius=3)
        for container in self.snapshot.get("containers", []):
            point = position(container["x"], container["y"])
            radius = max(3, round(scale * 0.65))
            storage_rect = pygame.Rect(point[0] - radius, point[1] - radius, radius * 2, radius * 2)
            pygame.draw.rect(self.surface, GOLD, storage_rect, border_radius=2)
            pygame.draw.line(self.surface, (124, 95, 57), storage_rect.midtop, storage_rect.midbottom, 1)
            self.map_hit(storage_rect.inflate(6, 6), container["uid"], [container.get("name", container["uid"]), f"Storage: {sum(container.get('items', {}).values())} items"])
            if container["uid"] == self.selected_uid:
                pygame.draw.rect(self.surface, ACCENT, storage_rect.inflate(6, 6), 2, border_radius=3)
        fixtures = {item["uid"]: item for item in self.snapshot.get("fixtures", [])}
        for reservation in self.snapshot.get("reservations", []):
            fixture = fixtures.get(reservation.get("target_uid"))
            if fixture and reservation.get("status") in ("active", "reserved", "running"):
                pygame.draw.circle(self.surface, GOLD, position(fixture["x"], fixture["y"]), max(5, round(scale * 1.2)), 1)
        for index, npc in enumerate(self.snapshot.get("npcs", [])):
            point = position(npc["x"], npc["y"])
            color = JOB_COLORS.get(npc.get("occupation", ""), (165, 200, 229))
            radius = max(4, min(9, round(scale * 0.65)))
            if npc["uid"] == self.selected_uid:
                pygame.draw.circle(self.surface, ACCENT, point, radius + 4, 2)
            pygame.draw.circle(self.surface, BG, point, radius + 1)
            pygame.draw.circle(self.surface, color, point, radius)
            hit = pygame.Rect(point[0] - radius - 3, point[1] - radius - 3, (radius + 3) * 2, (radius + 3) * 2)
            self.map_hit(hit, npc["uid"], [npc.get("name", npc["uid"]), _label(npc.get("occupation", "")), npc.get("task", "Idle")])
            if scale >= 5:
                self.text(str(index + 1), (point[0] + radius + 3, point[1] - 8), color, self.small)
        self.surface.set_clip(old_clip)
        if rect.height >= 100:
            self.text("Circle: worker   Green: tree   Violet: station   Gold: storage   Grey: blocked", (rect.x + 12, rect.bottom - 21), MUTED, self.small, rect.width - 24)

    def map_hit(self, rect: pygame.Rect, uid: str, tooltip: list[str]) -> None:
        clipped = rect.clip(self.surface.get_clip())
        if clipped.width and clipped.height:
            self.layout.hits.append(HitRegion(clipped, "select", uid))
            if self.hover is not None and clipped.collidepoint(self.hover):
                self.tooltip = tooltip

    def draw_inspector(self, rect: pygame.Rect) -> None:
        self.panel(rect, "INSPECTOR  /  wheel to scroll")
        lines: list[tuple[str, tuple[int, int, int], bool]] = []

        def line(value: Any = "", color: tuple[int, int, int] = TEXT, bold: bool = False) -> None:
            lines.append((str(value), color, bold))

        def section(value: str) -> None:
            line()
            line(value.upper(), ACCENT, True)

        selected: dict[str, Any] | None = None
        kind = ""
        for key in ("npcs", "containers", "fixtures"):
            selected = next((item for item in self.snapshot.get(key, []) if item["uid"] == self.selected_uid), None)
            if selected:
                kind = key
                break
        if selected is None:
            for key, prefix in (("crops", "crop"), ("piles", "pile")):
                item = next((item for item in self.snapshot.get(key, [])
                             if _location_uid(prefix, item) == self.selected_uid), None)
                if item is not None:
                    selected = dict(item, uid=_location_uid(prefix, item))
                    kind = key
                    break
        if selected and kind == "npcs":
            line(selected.get("name", selected["uid"]), TEXT, True)
            line(_label(selected.get("occupation", "")), JOB_COLORS.get(selected.get("occupation", ""), MUTED))
            line(f"Position  {selected.get('x', 0)}, {selected.get('y', 0)}, {selected.get('z', 0)}    Cash  {selected.get('wealth', 0)}")
            line(f"Hunger {selected.get('hunger', 0)}  /  Thirst {selected.get('thirst', 0)}  /  Rest need {selected.get('rest', 0)}", MUTED)
            section("Intent")
            line(f"Goal: {_label(selected.get('goal') or 'idle')}")
            line(f"Now: {selected.get('task') or 'Idle'}")
            section("Task queue")
            tasks = selected.get("tasks", [])
            if not tasks:
                line("Empty", MUTED)
            for index, task in enumerate(tasks, 1):
                if isinstance(task, dict):
                    name = task.get("kind") or task.get("type") or task.get("action") or task.get("task") or "task"
                    details = ", ".join(f"{key}={value}" for key, value in task.items() if key not in ("kind", "type", "action", "task"))
                    line(f"{index}. {_label(name)}" + (f"  ({details})" if details else ""))
                else:
                    line(f"{index}. {task}")
            section("Carried cargo")
            self.item_lines(selected.get("inventory", {}), line)
            section("Skills")
            self.item_lines(selected.get("skills", {}), line)
            if selected.get("needs"):
                section("Needs / utilities")
                self.item_lines(selected["needs"], line)
            section("Activity reservations")
            reservations = [r for r in self.snapshot.get("reservations", []) if r.get("actor_uid") == selected["uid"]]
            if not reservations:
                line("None", MUTED)
            for reservation in reservations:
                line(f"{_label(reservation.get('status', ''))}: {reservation.get('target_uid', '')}")
                line(f"Start {reservation.get('started_minute', 0)}  /  duration {reservation.get('duration_minutes', 0)} min", MUTED)
        elif selected:
            line(selected.get("name") or selected.get("label") or selected["uid"], TEXT, True)
            line(f"Position  {selected['x']}, {selected['y']}", MUTED)
            line(f"ID: {selected['uid']}", MUTED)
            if kind == "crops":
                section("Crop")
                line(_label(selected.get("crop_id", "crop")))
                line(f"Mature  {selected.get('mature', False)}  /  Growth  {selected.get('growth', 0)}")
                line(f"Moisture  {selected.get('moisture', 0)}  /  Health  {selected.get('health', 0)}")
            elif kind == "piles":
                section("Ground goods")
                self.item_lines(selected.get("items", {}), line)
            elif kind == "containers":
                line(f"Property: {selected.get('property_id') or 'public'}", MUTED)
                section("Stored goods")
                self.item_lines(selected.get("items", {}), line)
            else:
                section("Activity reservations")
                reservations = [r for r in self.snapshot.get("reservations", []) if r.get("target_uid") == selected["uid"]]
                if not reservations:
                    line("Available / no reservations", MUTED)
                for reservation in reservations:
                    line(f"{reservation.get('actor_uid', '')}: {_label(reservation.get('status', ''))}")
                    line(f"Start {reservation.get('started_minute', 0)} / duration {reservation.get('duration_minutes', 0)} min", MUTED)
        else:
            line("Click a worker, station or storage.", MUTED)
        section("Lab metrics")
        metrics = self.snapshot.get("metrics", {})
        line(f"Activities  {metrics.get('completed_activities', 0)}")
        line(f"Transfers  {metrics.get('transfers', 0)}    Trades  {metrics.get('transactions', 0)}")
        line(f"Cash total  {metrics.get('cash_total', 0)}    Delta  {metrics.get('cash_delta', 0):+}", ACCENT if not metrics.get("cash_delta") else RED)
        section("All physical goods")
        self.item_lines(metrics.get("goods_totals", {}), line)
        section("Market stock")
        market = self.snapshot.get("market", {})
        line(f"Market cash  {market.get('wealth', 0)}")
        self.item_lines(market.get("stocks", {}), line)
        warnings = metrics.get("warnings", [])
        if warnings:
            section("Warnings")
            for warning in warnings:
                line(warning, RED)
        else:
            line()
            line("No conservation / stock warnings", ACCENT)
        diagnostics = metrics.get("diagnostics", [])
        if diagnostics:
            section("Observations")
            for diagnostic in diagnostics:
                line(diagnostic, GOLD)
        section("Worker roster / Tab to cycle")
        for index, npc in enumerate(self.snapshot.get("npcs", []), 1):
            line(f"{index}. {npc.get('name', npc['uid'])}  /  {_label(npc.get('occupation', ''))}", JOB_COLORS.get(npc.get("occupation", ""), TEXT))
        body = pygame.Rect(rect.x + 12, rect.y + 34, max(1, rect.width - 26), max(0, rect.height - 43))
        self.layout.inspector = body
        self.layout.inspector_max_scroll = self.scroll_lines(body, lines, self.inspector_scroll)

    @staticmethod
    def item_lines(items: dict[str, Any], callback: Any) -> None:
        if not items:
            callback("Empty", MUTED)
        for item, count in sorted(items.items()):
            callback(f"{_label(item)}  {count}")

    def draw_events(self, rect: pygame.Rect) -> None:
        self.panel(rect, "ACTIVITY LOG  /  newest first")
        lines: list[tuple[str, tuple[int, int, int], bool]] = []
        for event in reversed(self.snapshot.get("events", [])):
            if isinstance(event, dict):
                lines.append((f"[{_time(event.get('minute', 0))}]  {event.get('message', '')}", TEXT, False))
            else:
                lines.append((str(event), TEXT, False))
        if not lines:
            lines.append(("No events yet. Run or step to observe jobs.", MUTED, False))
        body = pygame.Rect(rect.x + 12, rect.y + 34, max(1, rect.width - 26), max(0, rect.height - 43))
        self.layout.events = body
        self.layout.events_max_scroll = self.scroll_lines(body, lines, self.events_scroll)

    def scroll_lines(self, body: pygame.Rect, lines: list[tuple[str, tuple[int, int, int], bool]], scroll: int) -> int:
        wrapped: list[tuple[str, tuple[int, int, int], pygame.font.Font]] = []
        for value, color, bold in lines:
            font = self.section if bold else self.regular
            for text in _wrap(value, max(1, body.width - 10), font):
                wrapped.append((text, color, font))
        row_height = 20
        max_scroll = max(0, len(wrapped) * row_height - body.height)
        scroll = max(0, min(max_scroll, scroll))
        old_clip = self.surface.get_clip()
        self.surface.set_clip(body.clip(old_clip))
        first = scroll // row_height
        for index in range(first, min(len(wrapped), first + body.height // row_height + 2)):
            value, color, font = wrapped[index]
            self.text(value, (body.x, body.y + index * row_height - scroll), color, font)
        self.surface.set_clip(old_clip)
        if max_scroll and body.height:
            track = pygame.Rect(body.right - 2, body.y, 2, body.height)
            pygame.draw.rect(self.surface, EDGE, track)
            handle_height = max(8, round(body.height * body.height / (max_scroll + body.height)))
            handle_y = body.y + round((body.height - handle_height) * scroll / max_scroll)
            pygame.draw.rect(self.surface, ACCENT, (track.x, handle_y, 2, handle_height))
        return max_scroll

    def draw_tooltip(self) -> None:
        lines = [line for value in self.tooltip for line in _wrap(value, min(300, max(1, self.surface.get_width() - 30)), self.small)]
        if not lines:
            return
        width = min(self.surface.get_width(), max(self.small.size(line)[0] for line in lines) + 18)
        height = len(lines) * 18 + 12
        x = max(0, min(self.hover[0] + 14, self.surface.get_width() - width))
        y = max(0, min(self.hover[1] + 14, self.surface.get_height() - height))
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.surface, BG, rect, border_radius=4)
        pygame.draw.rect(self.surface, EDGE, rect, 1, border_radius=4)
        for index, line in enumerate(lines):
            self.text(line, (x + 9, y + 6 + index * 18), TEXT, self.small)


def render_frame(surface: pygame.Surface, snapshot: dict[str, Any], selected_uid: str | None = None) -> FrameLayout:
    """Render a paused snapshot, including on an offscreen/dummy SDL surface.

    This function does not access or mutate a lab, making it suitable for visual
    regression captures and inspection of an exported JSON snapshot.
    """
    return _Renderer(surface, snapshot, selected_uid).draw()


class LabViewer:
    """Presentation state and explicit lab controls, separated from rendering."""

    def __init__(self, lab: Any) -> None:
        self.lab = lab
        self.running = False
        self.alive = True
        self.speed = SPEEDS[0]
        self.selected_uid: str | None = None
        self.inspector_scroll = 0
        self.events_scroll = 0
        self.compact_tab = "inspect"
        self.status = ""
        self.layout = FrameLayout()
        self._accumulator = 0.0

    def draw(self, surface: pygame.Surface) -> FrameLayout:
        snapshot = self.lab.snapshot()
        if self.selected_uid is None and snapshot.get("npcs"):
            self.selected_uid = snapshot["npcs"][0]["uid"]
        self.layout = _Renderer(
            surface, snapshot, self.selected_uid, running=self.running, speed=self.speed,
            inspector_scroll=self.inspector_scroll, events_scroll=self.events_scroll,
            compact_tab=self.compact_tab, status=self.status, hover=pygame.mouse.get_pos() if pygame.display.get_init() else None,
        ).draw()
        self.inspector_scroll = min(self.inspector_scroll, self.layout.inspector_max_scroll)
        self.events_scroll = min(self.events_scroll, self.layout.events_max_scroll)
        return self.layout

    def update(self, elapsed_seconds: float) -> None:
        if not self.running:
            return
        # A suspended/dragged window never catches up with unbounded local ticks.
        self._accumulator += max(0.0, min(0.25, elapsed_seconds)) * self.speed
        ticks = int(self._accumulator)
        if ticks:
            self._accumulator -= ticks
            self._advance(ticks)

    def _advance(self, ticks: int) -> None:
        """Finish the bounded experiment and leave its final state inspectable."""
        from worldseed.config import SIMULATION_TICK_MINUTES
        from .npc_jobs import MAX_MINUTES, START_MINUTE

        remaining = max(0, (START_MINUTE + MAX_MINUTES - self.lab.minute) // SIMULATION_TICK_MINUTES)
        if remaining:
            self.lab.step(ticks=min(ticks, remaining))
        if ticks >= remaining:
            self.running = False
            self._accumulator = 0.0
            self.status = "Seven-day experiment complete; reset [R] to run again."

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.alive = False
        elif event.type == pygame.KEYDOWN:
            key_actions = {
                pygame.K_SPACE: "toggle", pygame.K_RIGHT: "step", pygame.K_r: "reset",
                pygame.K_c: "scenario", pygame.K_e: "export", pygame.K_MINUS: "slower",
                pygame.K_EQUALS: "faster", pygame.K_KP_PLUS: "faster", pygame.K_KP_MINUS: "slower",
            }
            if event.key == pygame.K_ESCAPE:
                self.alive = False
            elif event.key == pygame.K_TAB:
                self.cycle_npc(-1 if getattr(event, "mod", 0) & pygame.KMOD_SHIFT else 1)
            elif event.key in (pygame.K_i, pygame.K_l):
                self.compact_tab = "inspect" if event.key == pygame.K_i else "events"
            elif event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                self.scroll(-120 if event.key == pygame.K_PAGEUP else 120)
            elif event.key == pygame.K_HOME:
                self.inspector_scroll = self.events_scroll = 0
            elif event.key in key_actions:
                self.action(key_actions[event.key])
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for hit in reversed(self.layout.hits):
                if hit.rect.collidepoint(event.pos):
                    self.action(hit.action, hit.value)
                    break
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll(-event.y * 40)
        elif event.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
            self.running = False
            self._accumulator = 0.0

    def scroll(self, amount: int) -> None:
        pointer = pygame.mouse.get_pos() if pygame.display.get_init() else (0, 0)
        events_focused = self.layout.events is not None and self.layout.events.collidepoint(pointer)
        if events_focused or (self.layout.inspector is None and self.compact_tab == "events"):
            self.events_scroll = max(0, min(self.layout.events_max_scroll, self.events_scroll + amount))
        else:
            self.inspector_scroll = max(0, min(self.layout.inspector_max_scroll, self.inspector_scroll + amount))

    def cycle_npc(self, direction: int) -> None:
        npcs = self.lab.snapshot().get("npcs", [])
        if not npcs:
            return
        uids = [npc["uid"] for npc in npcs]
        index = uids.index(self.selected_uid) if self.selected_uid in uids else -1
        self.selected_uid = uids[(index + direction) % len(uids)]
        self.inspector_scroll = 0
        self.compact_tab = "inspect"

    def action(self, action: str, value: Any = None) -> None:
        if action == "toggle":
            self.running = not self.running
            self._accumulator = 0.0
        elif action == "step":
            self.running = False
            self._accumulator = 0.0
            self._advance(1)
        elif action in ("faster", "slower"):
            index = SPEEDS.index(self.speed)
            self.speed = SPEEDS[max(0, min(len(SPEEDS) - 1, index + (1 if action == "faster" else -1)))]
        elif action == "select":
            self.selected_uid = value
            self.inspector_scroll = 0
            self.compact_tab = "inspect"
        elif action == "tab":
            self.compact_tab = value
        elif action in ("reset", "scenario"):
            from .npc_jobs import SCENARIOS

            scenario = self.lab.scenario
            if action == "scenario":
                choices = list(SCENARIOS)
                scenario = choices[(choices.index(scenario) + 1) % len(choices)]
            self.lab = type(self.lab)(scenario=scenario, seed=self.lab.seed, workers=getattr(self.lab, "workers", 1))
            self.running = False
            self.selected_uid = None
            self.inspector_scroll = self.events_scroll = 0
            self._accumulator = 0.0
            self.status = f"Reset {_label(scenario)} with seed {self.lab.seed}; paused."
        elif action == "export":
            snapshot = self.lab.snapshot()
            path = Path(f"npc-job-lab-{self.lab.scenario}-m{self.lab.minute}.json")
            try:
                path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                self.status = f"Exported snapshot to {path.resolve()}"
            except OSError as exc:
                self.status = f"Export failed: {exc}"


def run_viewer(lab: Any) -> Any:
    """Open paused and return the final active lab when its window closes."""
    pygame.init()
    try:
        info = pygame.display.Info()
        width = min(1180, info.current_w) if info.current_w > 0 else 1000
        height = min(800, max(1, info.current_h - 80)) if info.current_h > 0 else 720
        surface = pygame.display.set_mode((max(1, width), max(1, height)), pygame.RESIZABLE)
        pygame.display.set_caption("WORLDSEED | NPC Job Lab")
        clock = pygame.time.Clock()
        viewer = LabViewer(lab)
        while viewer.alive:
            elapsed = clock.tick(30) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.VIDEORESIZE:
                    surface = pygame.display.set_mode((max(1, event.w), max(1, event.h)), pygame.RESIZABLE)
                else:
                    viewer.handle_event(event)
            if not viewer.alive:
                break
            viewer.update(elapsed)
            viewer.draw(surface)
            pygame.display.flip()
        return viewer.lab
    finally:
        pygame.quit()
