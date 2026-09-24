from __future__ import annotations

import re

from worldseed.content.registry import ContentRegistry
from worldseed.config import ENGINE_VERSION
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.sim.engine import Simulation
from worldseed.systems.state import pos_key
from worldseed.ui.alerts import world_alerts
from worldseed.ui.layout import compute_layout
from worldseed.world.world import World

RESET = '\x1b[0m'
BOLD = '\x1b[1m'
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class Renderer:
    """Read-only, terminal-safe gameplay HUD.

    The HUD has three deliberate layouts and never assumes a larger terminal
    than the one reported by the backend.  Simulation state is only read here;
    opening/resizing the UI cannot realize or mutate world state.
    """

    def __init__(self, registry: ContentRegistry, use_unicode: bool = True, use_color: bool = True) -> None:
        self.registry = registry
        self.use_unicode = use_unicode
        self.use_color = use_color
        # Camera uses a dead-zone rather than re-centering on every step.
        # This keeps fast movement visually stable and avoids the entire map
        # appearing to slide underneath the player.
        self._camera: tuple[int,int,int] | None = None

    @staticmethod
    def _visible_len(text: str) -> int:
        return len(ANSI_RE.sub('', text))

    @classmethod
    def _pad_visible(cls, text: str, width: int) -> str:
        missing = max(0, width - cls._visible_len(text))
        return text + (' ' * missing)

    @staticmethod
    def _clip(text: str, width: int) -> str:
        if width <= 0:
            return ''
        if len(text) <= width:
            return text
        if width <= 3:
            return text[:width]
        return text[:width-3] + '...'

    @staticmethod
    def _bar(v: int, maxv: int = 100, width: int = 10) -> str:
        maxv = max(1, maxv)
        v = max(0, min(maxv, v))
        n = round(v / maxv * width)
        return '[' + '#' * n + '-' * (width-n) + ']'

    def _terrain_glyph(self, terrain) -> str:
        glyph = terrain.glyph if self.use_unicode else terrain.ascii_glyph
        return f"\x1b[{terrain.ansi_color}m{glyph}{RESET}" if self.use_color else glyph

    def _resource_glyph(self, sim: Simulation, pos: WorldPos) -> str | None:
        fv=sim.resources.feature_at(pos)
        if not fv:return None
        if fv.stage=="stump": glyph="t"
        elif fv.stage=="sapling": glyph="i" if not self.use_unicode else "♣"
        elif fv.stage=="depleted": return None
        else:
            rd=self.registry.resources.get(fv.feature_id)
            if not rd:return None
            glyph=rd.glyph if self.use_unicode else rd.ascii_glyph
            return f"\x1b[{rd.ansi_color}m{glyph}{RESET}" if self.use_color else glyph
        return f"\x1b[33m{glyph}{RESET}" if self.use_color else glyph

    def _ground_glyph(self, tile) -> str:
        # Forest/berry terrain is biome ground. Individual vegetation is drawn
        # by the resource layer, so a harvested tree reveals forest floor
        # rather than magically converting the biome to grassland.
        if tile.terrain_id in {"core:forest","core:berry_thicket"}:
            glyph="."
            return f"\x1b[32m{glyph}{RESET}" if self.use_color else glyph
        return self._terrain_glyph(tile.terrain)

    def _tiny(self, width: int, height: int) -> str:
        width = max(1, width)
        lines = [
            'WORLDSEED',
            '',
            f'Terminal: {width}x{height}',
            'Resize to at least 60x18.',
            '',
            'WASD move | TAB menu | Q save/quit',
        ]
        return '\n'.join(self._clip(x, width) for x in lines[:max(1, height)])

    def render(self, world: World, entities: EntityStore, sim: Simulation, player_id: int,
               width: int, height: int, message: str = '', cursor: WorldPos | None = None,
               combat_overlay: dict | None = None) -> str:
        self.use_color = bool(sim.state.ui_color)
        self.use_unicode = bool(sim.state.ui_unicode)
        layout = compute_layout(width, height, sim.state.ui_density)
        if layout.mode == 'tiny':
            return self._tiny(layout.width, layout.height)

        pos = entities.get(player_id, Position).value
        inv = entities.get(player_id, Inventory)
        vit = entities.try_get(player_id, Vitals) or Vitals()
        tile = world.tile_at(pos)
        weather = sim.environment.weather.at(sim.clock.minute, pos.x, pos.y)
        room = sim.building.room_at(pos)
        alerts = world_alerts(sim, 8)

        header = f' WORLDSEED {ENGINE_VERSION} | {sim.state.player_name} | {sim.clock.label()} | {weather["kind"].title()} | ({pos.x},{pos.y},z{pos.z}) '
        lines = ['+' + self._clip(header, layout.width-2).center(layout.width-2, '-') + '+']

        map_rows = self._map_rows(world, sim, pos, layout.map_width, layout.map_height, cursor, combat_overlay)
        if layout.mode == 'wide':
            inner = layout.width - 4
            gap = 3
            side_w = max(18, inner - layout.map_width - gap)
            side_rows = self._sidebar(sim, tile.terrain.name, inv, vit, room, side_w, layout.map_height, cursor)
            for i in range(layout.map_height):
                left = self._pad_visible(map_rows[i], layout.map_width)
                right = self._clip(side_rows[i], side_w).ljust(side_w)
                content = left + ' | ' + right
                lines.append('| ' + self._pad_visible(content, inner) + ' |')
        else:
            inner = layout.width - 4
            left_pad = max(0, (inner - layout.map_width)//2)
            for row in map_rows:
                row = (' ' * left_pad) + self._pad_visible(row, layout.map_width)
                lines.append('| ' + self._pad_visible(row, inner) + ' |')

        lines.append('+' + '-' * (layout.width-2) + '+')
        latest = message or (sim.log[-1].message if sim.log else 'The world continues around you.')
        lines.append(self._full_row(self._clip(latest, layout.width-4), layout.width))

        if layout.mode == 'compact':
            status = f'HP {vit.hp}/{vit.max_hp}  STA {vit.stamina}  Food {vit.hunger}  Water {vit.thirst}  Alerts {len(alerts)}'
        else:
            status = (f'{tile.terrain.name} | HP {vit.hp}/{vit.max_hp}  STA {vit.stamina}  '
                      f'Hunger {vit.hunger}  Thirst {vit.thirst}  Blood {vit.blood}  Pain {vit.pain} | '
                      f'{room.get("classification", "outside")} | Alerts {len(alerts)}')
        lines.append(self._full_row(self._clip(status, layout.width-4), layout.width))

        controls = 'WASD/Arrows Move   Enter Actions   TAB Console   I Inventory   L Look   ESC Pause   ? Help   Q Save/Quit'
        lines.append(self._full_row(self._clip(controls, layout.width-4), layout.width))
        lines.append('+' + '-' * (layout.width-2) + '+')

        # Never write beyond the physical viewport.  This is a core invariant:
        # the terminal backend may clear remnants, but the renderer itself must
        # not depend on line wrapping for layout.
        return '\n'.join(lines[:layout.height])

    @staticmethod
    def _full_row(text: str, width: int) -> str:
        inner = max(0, width-4)
        return '| ' + text.ljust(inner)[:inner] + ' |'

    def _map_rows(self, world: World, sim: Simulation, pos: WorldPos, map_w: int, map_h: int,
                  cursor: WorldPos | None, combat_overlay: dict | None = None) -> list[str]:
        known = sim.discovered_tiles_set
        visible = sim.visible_tiles_set
        combat_by={(int(c["x"]),int(c["y"]),int(c["z"])):c for c in (combat_overlay or {}).get("cells",())}
        half_w, half_h = map_w//2, map_h//2
        # Keep the local-world camera centered on the player. The cursor may
        # move independently without dragging the camera away from the avatar.
        cx, cy, cz = pos.x, pos.y, pos.z
        self._camera=(cx,cy,cz)
        creature_by = {(c.x,c.y,c.z):c for c in sim.state.creatures.values() if c.hp > 0}
        npc_by = {(n.x,n.y,n.z):n for n in sim.state.npcs.values() if n.alive}
        structure_by = {(s.x,s.y,s.z):s for s in sim.state.structures.values()}
        crop_by = {(c.x,c.y,c.z):c for c in sim.state.crops.values()}
        fire_by = {(f.x,f.y,f.z):f for f in sim.state.fires.values()}
        fluid_by = {(f.x,f.y,f.z):f for f in sim.state.fluids.values() if f.amount > 20}
        pile_by = {(p.x,p.y,p.z):p for p in sim.state.ground_piles.values() if p.items}
        carcass_by = {(c.x,c.y,c.z):c for c in sim.state.carcasses.values()}
        den_by = {(d.x,d.y,d.z):d for d in sim.state.animal_dens.values()}
        sign_by = {}
        for sign in sorted(sim.state.animal_signs.values(),key=lambda q:(q.created_minute,q.uid)):
            sign_by[(sign.x,sign.y,sign.z)]=sign
        grave_by = {(g.x,g.y,g.z):g for g in sim.state.graves.values()}
        arc_by = {tuple(int(q) for q in k.split(',')):a for k,a in sim.state.arcane_contamination.items() if a.intensity > 20}
        dungeon_by: dict[tuple[int,int,int], str] = {}
        for site in sim.state.dungeon_sites.values():
            for pk, closed in site.locks.items():
                if closed:
                    dungeon_by[tuple(int(q) for q in pk.split(','))] = '+'
            for pk, armed in site.traps.items():
                if armed:
                    dungeon_by[tuple(int(q) for q in pk.split(','))] = '^'

        rows: list[str] = []
        for sy in range(map_h):
            y = cy + sy - half_h
            row: list[str] = []
            for sx in range(map_w):
                x = cx + sx - half_w
                k = (x,y,pos.z)
                pk = pos_key(x,y,pos.z)
                if x == pos.x and y == pos.y:
                    ch = '@'
                elif cursor is not None and (x,y,pos.z) == (cursor.x,cursor.y,cursor.z) and pk in known:
                    ch = 'X'
                elif pk not in known:
                    ch = ' '
                elif k in creature_by:
                    spec = self.registry.species.get(creature_by[k].species_id)
                    ch = spec.glyph if spec else 'm'
                elif k in npc_by: ch = 'n'
                elif k in fire_by: ch = '!'
                elif k in fluid_by: ch = '~'
                elif k in dungeon_by: ch = dungeon_by[k]
                elif k in carcass_by: ch = '&'
                elif k in den_by and pk in visible: ch = '⌂' if self.use_unicode else 'o'
                elif k in sign_by and pk in visible: ch = '·' if self.use_unicode else ','
                elif k in pile_by: ch = '
                elif k in grave_by: ch = '†' if self.use_unicode else '+'
                elif k in arc_by: ch = '*'
                elif k in crop_by: ch = 'Y' if crop_by[k].mature else ';'
                elif k in structure_by:
                    sd = self.registry.structures.get(structure_by[k].structure_id)
                    ch = sd.glyph if sd else '#'
                else:
                    wp=WorldPos(x,y,pos.z)
                    resource=self._resource_glyph(sim,wp)
                    ch = resource if resource is not None else self._ground_glyph(world.tile_at(wp))
                if ch == '@' and self.use_color:
                    ch = f'{BOLD}\x1b[97m@{RESET}'
                elif ch == 'X' and self.use_color:
                    ch = f'{BOLD}\x1b[93mX{RESET}'
                elif k in combat_by and self.use_color:
                    cell=combat_by[k]
                    plain=str(cell.get("glyph") or ANSI_RE.sub('',ch))
                    if cell.get("blocked"):code="90"
                    else:
                        chance=int(cell.get("chance",0))
                        code="92" if chance>=75 else "93" if chance>=55 else "33" if chance>=35 else "91"
                    ch=f'\x1b[{code}m{plain}{RESET}'
                elif k in combat_by and not self.use_color and ch not in ('@','X'):
                    ch=str(combat_by[k].get("glyph") or ('+' if int(combat_by[k].get("chance",0))>=55 else '!'))
                row.append(ch)
            rows.append(''.join(row))
        return rows

    def _sidebar(self, sim: Simulation, terrain: str, inv: Inventory, v: Vitals, room: dict,
                 width: int, height: int, cursor: WorldPos | None) -> list[str]:
        p = sim.player_pos
        rows = [
            'STATUS',
            f'Stance: {sim.state.player_stance}',
            f'HP   {self._bar(v.hp,v.max_hp)} {v.hp:>3}',
            f'STA  {self._bar(v.stamina)} {v.stamina:>3}',
            f'FOOD {self._bar(100-v.hunger)}',
            f'WATR {self._bar(100-v.thirst)}',
            f'BLD  {self._bar(v.blood)} {v.blood:>3}',
            f'PAIN {self._bar(v.pain)} {v.pain:>3}',
            '',
            self._clip(sim.resources.description(p), width),
            'Room: ' + str(room.get('classification','outside')),
        ]
        if cursor is not None:
            rows += ['', 'LOOK', f'{cursor.x},{cursor.y},z{cursor.z}']
        alerts = [a for a in world_alerts(sim) if a.severity >= 60][:3]
        if alerts:
            rows += ['', 'ALERTS']
            for a in alerts:
                rows.append(f'{a.severity:>3} {a.text}')
        wounds = [w for w in sim.state.player_wounds if int(w.get('severity',0))>0 or int(w.get('bleeding',0))>0 or w.get('fracture')]
        if wounds:
            rows += ['', 'INJURIES']
            for w in wounds[-2:]:
                rows.append(f"{str(w.get('part','?')).replace('_',' ')} s{w.get('severity',0)} b{w.get('bleeding',0)}")
        rows += ['', 'NEARBY']
        near = []
        known_species=sim.known_species_ids();known_npcs=sim.known_npc_ids();known_creatures=sim.known_creature_ids()
        for c in sorted((c for c in sim.state.creatures.values() if c.hp>0 and c.z==p.z and abs(c.x-p.x)+abs(c.y-p.y)<=40), key=lambda c:abs(c.x-p.x)+abs(c.y-p.y))[:2]:
            spec = self.registry.species.get(c.species_id)
            label=(c.name if c.uid in known_creatures and c.name else (spec.name if spec and c.species_id in known_species else 'Unknown creature'))
            near.append(f'{label} d{abs(c.x-p.x)+abs(c.y-p.y)}')
        for n in sorted((n for n in sim.state.npcs.values() if n.alive and n.z==p.z and abs(n.x-p.x)+abs(n.y-p.y)<=40), key=lambda n:abs(n.x-p.x)+abs(n.y-p.y))[:2]:
            near.append(f'{n.name} [{n.occupation}]' if n.uid in known_npcs else f'Stranger d{abs(n.x-p.x)+abs(n.y-p.y)}')
        rows += near or ['Quiet nearby']
        rows += ['', 'GEAR']
        gear = [f'{slot}: {self.registry.items[iid].name}' for slot,iid in sorted(sim.state.player_equipment.items()) if iid in self.registry.items]
        rows += gear[:3] or ['None equipped']
        rows += ['', f'Pack: {sum(n for n in inv.items.values() if n>0)} items']
        rows = [self._clip(str(r), width) for r in rows]
        rows += [''] * max(0, height-len(rows))
        return rows[:height]

                elif k in grave_by: ch = '†' if self.use_unicode else '+'
                elif k in arc_by: ch = '*'
                elif k in crop_by: ch = 'Y' if crop_by[k].mature else ';'
                elif k in structure_by:
                    sd = self.registry.structures.get(structure_by[k].structure_id)
                    ch = sd.glyph if sd else '#'
                else:
                    wp=WorldPos(x,y,pos.z)
                    resource=self._resource_glyph(sim,wp)
                    ch = resource if resource is not None else self._ground_glyph(world.tile_at(wp))
                if ch == '@' and self.use_color:
                    ch = f'{BOLD}\x1b[97m@{RESET}'
                elif ch == 'X' and self.use_color:
                    ch = f'{BOLD}\x1b[93mX{RESET}'
                elif k in combat_by and self.use_color:
                    cell=combat_by[k]
                    plain=ANSI_RE.sub('',ch)
                    if cell.get("blocked"):code="90"
                    else:
                        chance=int(cell.get("chance",0))
                        code="92" if chance>=75 else "93" if chance>=55 else "33" if chance>=35 else "91"
                    ch=f'\x1b[{code}m{plain}{RESET}'
                elif k in combat_by and not self.use_color and ch not in ('@','X'):
                    ch='+' if int(combat_by[k].get("chance",0))>=55 else '!'
                row.append(ch)
            rows.append(''.join(row))
        return rows

    def _sidebar(self, sim: Simulation, terrain: str, inv: Inventory, v: Vitals, room: dict,
                 width: int, height: int, cursor: WorldPos | None) -> list[str]:
        p = sim.player_pos
        rows = [
            'STATUS',
            f'HP   {self._bar(v.hp,v.max_hp)} {v.hp:>3}',
            f'STA  {self._bar(v.stamina)} {v.stamina:>3}',
            f'FOOD {self._bar(100-v.hunger)}',
            f'WATR {self._bar(100-v.thirst)}',
            f'BLD  {self._bar(v.blood)} {v.blood:>3}',
            f'PAIN {self._bar(v.pain)} {v.pain:>3}',
            '',
            self._clip(sim.resources.description(p), width),
            'Room: ' + str(room.get('classification','outside')),
        ]
        if cursor is not None:
            rows += ['', 'LOOK', f'{cursor.x},{cursor.y},z{cursor.z}']
        alerts = [a for a in world_alerts(sim) if a.severity >= 60][:3]
        if alerts:
            rows += ['', 'ALERTS']
            for a in alerts:
                rows.append(f'{a.severity:>3} {a.text}')
        wounds = [w for w in sim.state.player_wounds if int(w.get('severity',0))>0 or int(w.get('bleeding',0))>0 or w.get('fracture')]
        if wounds:
            rows += ['', 'INJURIES']
            for w in wounds[-2:]:
                rows.append(f"{str(w.get('part','?')).replace('_',' ')} s{w.get('severity',0)} b{w.get('bleeding',0)}")
        rows += ['', 'NEARBY']
        near = []
        known_species=sim.known_species_ids();known_npcs=sim.known_npc_ids();known_creatures=sim.known_creature_ids()
        for c in sorted((c for c in sim.state.creatures.values() if c.hp>0 and c.z==p.z and abs(c.x-p.x)+abs(c.y-p.y)<=40), key=lambda c:abs(c.x-p.x)+abs(c.y-p.y))[:2]:
            spec = self.registry.species.get(c.species_id)
            label=(c.name if c.uid in known_creatures and c.name else (spec.name if spec and c.species_id in known_species else 'Unknown creature'))
            near.append(f'{label} d{abs(c.x-p.x)+abs(c.y-p.y)}')
        for n in sorted((n for n in sim.state.npcs.values() if n.alive and n.z==p.z and abs(n.x-p.x)+abs(n.y-p.y)<=40), key=lambda n:abs(n.x-p.x)+abs(n.y-p.y))[:2]:
            near.append(f'{n.name} [{n.occupation}]' if n.uid in known_npcs else f'Stranger d{abs(n.x-p.x)+abs(n.y-p.y)}')
        rows += near or ['Quiet nearby']
        rows += ['', 'GEAR']
        gear = [f'{slot}: {self.registry.items[iid].name}' for slot,iid in sorted(sim.state.player_equipment.items()) if iid in self.registry.items]
        rows += gear[:3] or ['None equipped']
        rows += ['', f'Pack: {sum(n for n in inv.items.values() if n>0)} items']
        rows = [self._clip(str(r), width) for r in rows]
        rows += [''] * max(0, height-len(rows))
        return rows[:height]
