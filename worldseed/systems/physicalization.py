"""Local projection of persistent settlement plans.

This is a bounded reconstruction layer. It never invents a second village,
mutates generated terrain, or copies planned walls into player-built structure
state. The authoritative SettlementSkeleton remains the source; this module
indexes only the currently relevant cells for simulation/render queries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from worldseed.core.coords import WorldPos


@dataclass(frozen=True, slots=True)
class PhysicalizedSettlementCell:
    x: int
    y: int
    settlement_id: str
    parcel_id: str = ""
    road_ids: tuple[str, ...] = ()
    structure_id: str = ""
    room_id: str = ""
    ground_piece_id: str = ""
    structure_piece_id: str = ""
    structure_piece_uid: str = ""
    structure_piece_role: str = ""
    fixture_piece_id: str = ""
    roof_piece_id: str = ""
    crossing_id: str = ""
    crossing_kind: str = ""
    crossing_condition: int = 100
    crossing_blocked: bool = False
    border_post_id: str = ""

    @property
    def occupied(self) -> bool:
        return bool(self.structure_piece_id or self.fixture_piece_id)


class SettlementPhysicalizationSystem:
    """Materialize nearby settlement plans into a cheap local cell index."""

    ROAD_PIECES = {
        "path": "core:footpath_piece",
        "trail": "core:footpath_piece",
        "service_path": "core:footpath_piece",
        "road": "core:dirt_lane_piece",
        "maintained_road": "core:cobble_road_piece",
    }

    def __init__(self, world, registry, region_planner, skeleton_planner, route_planner=None):
        self.world = world
        self.registry = registry
        self.region_planner = region_planner
        self.skeleton_planner = skeleton_planner
        self.route_planner = route_planner
        self._cells: dict[tuple[int, int], PhysicalizedSettlementCell] = {}
        self._rooms: dict[str, object] = {}
        self._structures: dict[str, object] = {}
        self._skeletons: dict[str, object] = {}
        self._route_segments: dict[str, object] = {}
        self._crossings: dict[str, object] = {}
        self._active_settlement_ids: tuple[str, ...] = ()
        self.revision = 0

    @property
    def active_settlement_ids(self) -> tuple[str, ...]:
        return self._active_settlement_ids

    def clear(self) -> None:
        self._cells.clear()
        self._rooms.clear()
        self._structures.clear()
        self._skeletons.clear()
        self._route_segments.clear()
        self._crossings.clear()
        self._active_settlement_ids = ()
        self.revision += 1

    def _road_piece(self, road_class: str) -> str:
        preferred = self.ROAD_PIECES.get(str(road_class), "core:dirt_lane_piece")
        if preferred in self.registry.settlement_pieces:
            return preferred
        rows = sorted(
            (p.id for p in self.registry.settlement_pieces.values() if p.category == "road")
        )
        return rows[0] if rows else ""

    @staticmethod
    def _merge_cell(existing: PhysicalizedSettlementCell | None, **changes) -> PhysicalizedSettlementCell:
        base = {
            "x": changes["x"], "y": changes["y"], "settlement_id": changes["settlement_id"],
            "parcel_id": "", "road_ids": (), "structure_id": "", "room_id": "",
            "ground_piece_id": "", "structure_piece_id": "", "structure_piece_uid": "", "structure_piece_role": "", "fixture_piece_id": "", "roof_piece_id": "",
            "crossing_id": "", "crossing_kind": "", "crossing_condition": 100, "crossing_blocked": False, "border_post_id": "",
        }
        if existing is not None:
            base.update({
                "parcel_id": existing.parcel_id, "road_ids": existing.road_ids,
                "structure_id": existing.structure_id, "room_id": existing.room_id,
                "ground_piece_id": existing.ground_piece_id,
                "structure_piece_id": existing.structure_piece_id,
                "structure_piece_uid": existing.structure_piece_uid,
                "structure_piece_role": existing.structure_piece_role,
                "fixture_piece_id": existing.fixture_piece_id,
                "roof_piece_id": existing.roof_piece_id,
                "crossing_id": existing.crossing_id,
                "crossing_kind": existing.crossing_kind,
                "crossing_condition": existing.crossing_condition,
                "crossing_blocked": existing.crossing_blocked,
                "border_post_id": existing.border_post_id,
            })
        base.update({k: v for k, v in changes.items() if k not in ("x", "y", "settlement_id")})
        base["x"] = int(changes["x"]); base["y"] = int(changes["y"])
        base["settlement_id"] = str(changes["settlement_id"])
        return PhysicalizedSettlementCell(**base)

    def _index_skeleton(self, settlement_id: str, skeleton) -> None:
        for parcel in skeleton.parcels:
            for x, y in parcel.cells:
                key = (int(x), int(y)); old = self._cells.get(key)
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id, parcel_id=parcel.uid
                )

        for road in skeleton.roads:
            piece_id = self._road_piece(road.road_class)
            for x, y in road.polyline:
                key = (int(x), int(y)); old = self._cells.get(key)
                roads = tuple(sorted(set((old.road_ids if old else ()) + (road.uid,))))
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id,
                    road_ids=roads, ground_piece_id=piece_id,
                )

        for structure in skeleton.structures:
            self._structures[structure.uid] = structure
            for x, y in structure.footprint:
                key = (int(x), int(y)); old = self._cells.get(key)
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id, structure_id=structure.uid
                )

        for room in skeleton.rooms:
            self._rooms[room.uid] = room
            for x, y in room.cells:
                key = (int(x), int(y)); old = self._cells.get(key)
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id, room_id=room.uid
                )

        for placement in skeleton.pieces:
            key = (int(placement.x), int(placement.y)); old = self._cells.get(key)
            piece = self.registry.settlement_pieces.get(placement.piece_id)
            if piece is None:
                continue
            changes = {}
            if placement.role in {"wall", "partition", "entrance", "interior_door", "yard_fence", "yard_gate"}:
                changes["structure_piece_id"] = placement.piece_id
                changes["structure_piece_uid"] = placement.uid
                changes["structure_piece_role"] = placement.role
            elif placement.role in {"fixture", "yard_fixture"}:
                changes["fixture_piece_id"] = placement.piece_id
            elif placement.role == "roof" or piece.category == "roof":
                changes["roof_piece_id"] = placement.piece_id
            elif placement.role == "floor" or piece.layer == "ground":
                changes["ground_piece_id"] = placement.piece_id
            self._cells[key] = self._merge_cell(
                old, x=placement.x, y=placement.y, settlement_id=settlement_id, **changes
            )

    def _index_regional_route(self, road, crossings) -> None:
        """Project one exact strategic road segment into the local cell index."""
        self._route_segments[road.uid]=road
        route_crossings=[c for c in crossings if c.route_id==road.route_id]
        crossing_cells={}
        landing_cells={}
        for crossing in route_crossings:
            self._crossings[crossing.uid]=crossing
            cells=list(getattr(crossing,"cells",()) or [(int(crossing.x),int(crossing.y))])
            for cell in cells:crossing_cells[tuple(map(int,cell))]=crossing
            for landing in (getattr(crossing,"landing_a",None),getattr(crossing,"landing_b",None)):
                if landing is not None:landing_cells[tuple(map(int,landing))]=crossing

        piece_id=self._road_piece(road.road_class)
        for x,y in road.polyline:
            x=int(x);y=int(y);key=(x,y);old=self._cells.get(key)
            crossing=crossing_cells.get(key);landing=landing_cells.get(key)
            road_ids=tuple(sorted(set((old.road_ids if old else ())+(road.uid,road.route_id))))
            settlement_id=old.settlement_id if old else ""
            ground_piece=piece_id
            changes={}
            if crossing is not None:
                kind=str(crossing.kind)
                if kind=="bridge":
                    ground_piece="core:plank_road_piece" if "core:plank_road_piece" in self.registry.settlement_pieces else piece_id
                elif kind=="ferry":
                    # Water between ferry landings remains water; the local cell
                    # exists for interaction/hover but never receives a fake road.
                    env=self.world.environment_at(WorldPos(x,y,0))
                    if env is not None and env.open_water:ground_piece=""
                elif kind=="ford":
                    ground_piece="core:bridge_approach_piece" if "core:bridge_approach_piece" in self.registry.settlement_pieces else piece_id
                changes.update(
                    crossing_id=str(crossing.uid),crossing_kind=kind,
                    crossing_condition=int(crossing.condition),crossing_blocked=bool(crossing.blocked),
                )
            elif landing is not None:
                kind=str(landing.kind)
                if kind=="ferry":
                    ground_piece="core:dock_walk_piece" if "core:dock_walk_piece" in self.registry.settlement_pieces else piece_id
                elif kind=="bridge":
                    ground_piece="core:bridge_approach_piece" if "core:bridge_approach_piece" in self.registry.settlement_pieces else piece_id
                changes.update(
                    crossing_id=str(landing.uid),crossing_kind=kind,
                    crossing_condition=int(landing.condition),crossing_blocked=bool(landing.blocked),
                )
            self._cells[key]=self._merge_cell(
                old,x=x,y=y,settlement_id=settlement_id,
                road_ids=road_ids,ground_piece_id=ground_piece,**changes,
            )

        if self.route_planner is not None:
            for post in self.route_planner.border_posts_for_route(road.route_id):
                key=(int(post.x),int(post.y))
                # Only index a post in the region currently represented by this
                # segment. Posts remain simulation state even when not local.
                if key not in set((int(x),int(y)) for x,y in road.polyline):
                    continue
                old=self._cells.get(key);settlement_id=old.settlement_id if old else ""
                self._cells[key]=self._merge_cell(
                    old,x=key[0],y=key[1],settlement_id=settlement_id,
                    border_post_id=str(post.uid),
                )

    def sync(self, settlements: Iterable, center_region: tuple[int, int], radius: int = 0) -> int:
        """Rebuild the local index from settlements near one active region.

        Missing environmental preparation is treated as not-yet-materializable,
        never as permission to invent a fallback layout.
        """
        rx, ry = int(center_region[0]), int(center_region[1])
        selected = sorted(
            (
                s for s in settlements
                if abs(int(s.region_x) - rx) <= radius and abs(int(s.region_y) - ry) <= radius
            ),
            key=lambda s: s.uid,
        )
        new_cells = {}
        new_rooms = {}
        new_structures = {}
        new_skeletons = {}
        new_route_segments={}
        new_crossings={}
        old_cells,old_rooms,old_structures,old_skeletons,old_route_segments,old_crossings=(
            self._cells,self._rooms,self._structures,self._skeletons,self._route_segments,self._crossings
        )
        self._cells,self._rooms,self._structures,self._skeletons,self._route_segments,self._crossings=(
            new_cells,new_rooms,new_structures,new_skeletons,new_route_segments,new_crossings
        )
        active = []
        try:
            for settlement in selected:
                region = self.region_planner.plan(settlement.region_x, settlement.region_y, persist=True)
                try:
                    route_links=(
                        self.route_planner.links_for_settlement(settlement.uid)
                        if self.route_planner is not None else ()
                    )
                    skeleton = self.skeleton_planner.plan(
                        region, settlement.uid, settlement.population,
                        culture_id=str(getattr(settlement,"culture_id","")),
                        faction_id=str(getattr(settlement,"faction_id","")),
                        route_links=route_links,persist=True
                    )
                except ValueError:
                    continue
                active.append(settlement.uid)
                self._skeletons[settlement.uid] = skeleton
                self._index_skeleton(settlement.uid, skeleton)
            if self.route_planner is not None:
                route_roads,route_crossings=self.route_planner.materialize_region((rx,ry),self._skeletons)
                for road in route_roads:self._index_regional_route(road,route_crossings)
        except Exception:
            self._cells,self._rooms,self._structures,self._skeletons,self._route_segments,self._crossings=(
                old_cells,old_rooms,old_structures,old_skeletons,old_route_segments,old_crossings
            )
            raise
        self._active_settlement_ids = tuple(active)
        self.revision += 1
        return len(active)

    def cells(self) -> tuple[PhysicalizedSettlementCell, ...]:
        return tuple(self._cells[key] for key in sorted(self._cells, key=lambda p: (p[1], p[0])))

    def cells_in_bounds(self,left:int,top:int,right:int,bottom:int) -> tuple[PhysicalizedSettlementCell, ...]:
        """Return only materialized settlement cells intersecting a local viewport."""
        left,top,right,bottom=map(int,(left,top,right,bottom))
        return tuple(cell for (x,y),cell in self._cells.items() if left<=x<=right and top<=y<=bottom)

    def route_segments(self):
        return tuple(self._route_segments[key] for key in sorted(self._route_segments))

    def crossing_by_id(self,crossing_id:str):
        return self._crossings.get(str(crossing_id))

    def crossing_at(self,pos:WorldPos):
        cell=self._cells.get((int(pos.x),int(pos.y)))
        if cell is not None and cell.crossing_id:
            return self._crossings.get(cell.crossing_id)
        for crossing in self._crossings.values():
            cells=set(tuple(map(int,p)) for p in (getattr(crossing,"cells",()) or ()))
            landings={tuple(map(int,p)) for p in (getattr(crossing,"landing_a",None),getattr(crossing,"landing_b",None)) if p is not None}
            if (pos.x,pos.y) in cells|landings:return crossing
        return None

    def border_post_at(self,pos:WorldPos):
        cell=self._cells.get((int(pos.x),int(pos.y)))
        if cell is None or not cell.border_post_id:return None
        return self.route_planner.state.border_posts.get(cell.border_post_id) if self.route_planner is not None else None

    def skeleton_for(self, settlement_id: str):
        return self._skeletons.get(str(settlement_id))

    def structure_by_id(self, structure_id: str):
        return self._structures.get(str(structure_id))

    def room_by_id(self, room_id: str):
        return self._rooms.get(str(room_id))

    def destination_for(self, structure_id: str, room_id: str = "") -> WorldPos | None:
        """Return a stable passable destination inside one active planned structure."""
        structure = self._structures.get(str(structure_id))
        if structure is None:
            return None
        room = self._rooms.get(str(room_id)) if room_id else None
        if room is None:
            room = next(
                (
                    row for row in sorted(self._rooms.values(), key=lambda value: value.uid)
                    if row.structure_plan_id == structure.uid
                ),
                None,
            )
        if room is not None and room.cells:
            xs=[int(p[0]) for p in room.cells];ys=[int(p[1]) for p in room.cells]
            cx=sum(xs)//len(xs);cy=sum(ys)//len(ys)
            candidates=[]
            for x,y in room.cells:
                pos=WorldPos(int(x),int(y),0)
                if self.passable(pos,True):
                    candidates.append((abs(int(x)-cx)+abs(int(y)-cy),int(y),int(x)))
            if candidates:
                _,y,x=min(candidates)
                return WorldPos(x,y,0)
        if structure.entrance is not None:
            return WorldPos(int(structure.entrance[0]),int(structure.entrance[1]),0)
        if structure.footprint:
            x,y=structure.footprint[0]
            return WorldPos(int(x),int(y),0)
        return None

    def destination_for_function(self, settlement_id: str, functions) -> WorldPos | None:
        skeleton=self._skeletons.get(str(settlement_id))
        if skeleton is None:return None
        wanted=tuple(functions) if not isinstance(functions,str) else (functions,)
        candidates=sorted(
            (s for s in skeleton.structures if not s.destroyed and s.function in wanted),
            key=lambda s:(wanted.index(s.function),s.uid),
        )
        for structure in candidates:
            rooms=sorted(
                (r for r in skeleton.rooms if r.structure_plan_id==structure.uid),
                key=lambda r:(r.kind,r.uid),
            )
            target=self.destination_for(structure.uid,rooms[0].uid if rooms else "")
            if target is not None:return target
        return None


    def cell_at(self, pos: WorldPos) -> PhysicalizedSettlementCell | None:
        if pos.z != 0:
            return None
        return self._cells.get((int(pos.x), int(pos.y)))

    def piece_def_at(self, pos: WorldPos):
        cell = self.cell_at(pos)
        if cell is None:
            return None
        piece_id = cell.structure_piece_id or cell.fixture_piece_id
        return self.registry.settlement_pieces.get(piece_id) if piece_id else None

    def door_at(self, pos: WorldPos):
        cell = self.cell_at(pos)
        if cell is None or cell.structure_piece_role not in {"entrance", "interior_door"}:
            return None
        return cell

    def passable(self, pos: WorldPos, world_passable: bool = True) -> bool:
        piece = self.piece_def_at(pos)
        return bool(world_passable if piece is None else world_passable and piece.passable)

    def blocks_sight(self, pos: WorldPos) -> bool:
        piece = self.piece_def_at(pos)
        return bool(piece and piece.blocks_sight)

    def clears_natural_feature(self, pos: WorldPos) -> bool:
        """Return whether planned civilization owns this cell for nature placement.

        Roads, floors, walls and fixtures always win over deterministic natural
        overlays.  Buildings also reserve a one-cell exterior apron so trees,
        boulders and natural containers cannot seal a doorway, hug a wall, or
        make casing/walking around a property impossible.
        """
        if pos.z != 0:
            return False
        x, y = int(pos.x), int(pos.y)
        cell = self._cells.get((x, y))
        if cell is not None and (
            cell.road_ids or cell.ground_piece_id or cell.structure_id
            or cell.structure_piece_id or cell.fixture_piece_id
        ):
            return True
        # Keep only buildings buffered.  Roads already clear their occupied
        # cells; buffering every road would erase too much settlement-edge
        # vegetation.  A one-cell Chebyshev apron is enough for door approach,
        # perimeter movement and casing sightlines.
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nearby = self._cells.get((x + dx, y + dy))
                if nearby is not None and nearby.structure_id:
                    return True
        return False

    def glyph_at(self, pos: WorldPos) -> str | None:
        cell = self.cell_at(pos)
        if cell is None:
            return None
        for piece_id in (cell.structure_piece_id, cell.fixture_piece_id, cell.ground_piece_id):
            piece = self.registry.settlement_pieces.get(piece_id)
            if piece is not None:
                return piece.glyph
        return None

    def room_at(self, pos: WorldPos) -> dict | None:
        cell = self.cell_at(pos)
        if cell is None or not cell.room_id:
            return None
        room = self._rooms.get(cell.room_id)
        if room is None:
            return None
        fixture_names = []
        for c in self._cells.values():
            if c.room_id != room.uid or not c.fixture_piece_id:
                continue
            definition = self.registry.settlement_pieces.get(c.fixture_piece_id)
            if definition is not None:
                fixture_names.append(definition.name)
        return {
            "enclosed": bool(room.enclosed),
            "sheltered": bool(room.sheltered),
            "roof_percent": int(room.roof_percent),
            "area": int(room.area),
            "doors": len(room.doorway_cells),
            "beds": 1 if room.kind == "bedroom" else 0,
            "stations": sorted(set(fixture_names)),
            "classification": str(room.kind),
            "room_id": room.uid,
            "structure_id": room.structure_plan_id,
            "settlement_id": cell.settlement_id,
        }

    def structure_at(self, pos: WorldPos):
        cell = self.cell_at(pos)
        if cell is None or not cell.structure_id:
            return None
        return self._structures.get(cell.structure_id)
