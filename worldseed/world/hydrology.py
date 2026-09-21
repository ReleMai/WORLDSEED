from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Any, TYPE_CHECKING

from worldseed.config import HYDROLOGY_VERSION
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64

if TYPE_CHECKING:  # avoids generator <-> hydrology runtime import cycles
    from worldseed.world.generator import WorldGenerator

# One hydrology node represents 16 world cells. A 64x64 core covers 1024x1024
# cells. Eight halo nodes (128 cells) on every side are enough for tile-level
# river refinement and keep the ordinary prepared play area away from the
# unresolved outside edge of a planning window.
HYDROLOGY_LATTICE_SPACING = 16
HYDROLOGY_DOMAIN_NODES = 64
HYDROLOGY_HALO_NODES = 8
HYDROLOGY_ALGORITHM = "rc14-phase3-window-v1"

D8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


@dataclass(frozen=True, slots=True)
class HydrologySurface:
    """Cheap physical-geography read model for one surface cell.

    The values are intentionally game-readable classes/scores rather than a GIS
    simulation. They are stable consumers for terrain projection, route costs,
    settlement siting and later ecology.
    """

    watershed_id: int = 0
    river_class: int = 0
    river_width: int = 0
    river_depth_class: int = 0
    floodplain_strength: int = 0
    wetland_probability: int = 0
    water_access_score: int = 0
    flood_risk: int = 0
    crossing_cost: int = 0
    lake: bool = False
    ford: bool = False
    terrain_override: str | None = None


@dataclass(frozen=True, slots=True)
class HydrologyDomain:
    domain_x: int
    domain_y: int
    version: int
    lattice_spacing: int
    core_nodes: int
    halo_nodes: int
    origin_node_x: int
    origin_node_y: int
    width: int
    height: int
    elevation: tuple[int, ...]
    filled_elevation: tuple[int, ...]
    flow_to: tuple[int, ...]
    accumulation: tuple[int, ...]
    watershed_id: tuple[int, ...]
    river_class: tuple[int, ...]
    floodplain_strength: tuple[int, ...]
    outlets: tuple[tuple[int, int, int], ...]
    fingerprint: str
    algorithm: str = HYDROLOGY_ALGORITHM

    @property
    def uid(self) -> str:
        return f"hydro:{self.version}:{self.domain_x}:{self.domain_y}"

    def index(self, lx: int, ly: int) -> int:
        return int(ly) * self.width + int(lx)

    def local_xy(self, index: int) -> tuple[int, int]:
        return int(index) % self.width, int(index) // self.width

    def global_node_xy(self, index: int) -> tuple[int, int]:
        lx, ly = self.local_xy(index)
        return self.origin_node_x + lx, self.origin_node_y + ly

    def world_xy(self, index: int) -> tuple[int, int]:
        gx, gy = self.global_node_xy(index)
        return gx * self.lattice_spacing, gy * self.lattice_spacing

    def global_index(self, gx: int, gy: int) -> int | None:
        lx, ly = int(gx) - self.origin_node_x, int(gy) - self.origin_node_y
        if 0 <= lx < self.width and 0 <= ly < self.height:
            return self.index(lx, ly)
        return None

    def is_outer_boundary(self, index: int) -> bool:
        x, y = self.local_xy(index)
        return x == 0 or y == 0 or x == self.width - 1 or y == self.height - 1

    def core_indices(self):
        h = self.halo_nodes
        for y in range(h, h + self.core_nodes):
            base = y * self.width
            for x in range(h, h + self.core_nodes):
                yield base + x

    def to_payload(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "domain_x": self.domain_x,
            "domain_y": self.domain_y,
            "version": self.version,
            "lattice_spacing": self.lattice_spacing,
            "core_nodes": self.core_nodes,
            "halo_nodes": self.halo_nodes,
            "origin_node_x": self.origin_node_x,
            "origin_node_y": self.origin_node_y,
            "width": self.width,
            "height": self.height,
            "elevation": list(self.elevation),
            "filled_elevation": list(self.filled_elevation),
            "flow_to": list(self.flow_to),
            "accumulation": list(self.accumulation),
            "watershed_id": list(self.watershed_id),
            "river_class": list(self.river_class),
            "floodplain_strength": list(self.floodplain_strength),
            "outlets": [list(v) for v in self.outlets],
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> "HydrologyDomain":
        if str(raw.get("algorithm", "")) != HYDROLOGY_ALGORITHM:
            raise ValueError("stale hydrology algorithm")
        return cls(
            int(raw["domain_x"]), int(raw["domain_y"]), int(raw["version"]), int(raw["lattice_spacing"]),
            int(raw["core_nodes"]), int(raw["halo_nodes"]), int(raw["origin_node_x"]), int(raw["origin_node_y"]),
            int(raw["width"]), int(raw["height"]), tuple(map(int, raw["elevation"])),
            tuple(map(int, raw["filled_elevation"])), tuple(map(int, raw["flow_to"])),
            tuple(map(int, raw["accumulation"])), tuple(map(int, raw["watershed_id"])),
            tuple(map(int, raw["river_class"])), tuple(map(int, raw["floodplain_strength"])),
            tuple(tuple(map(int, v)) for v in raw.get("outlets", [])), str(raw["fingerprint"]),
            str(raw.get("algorithm", HYDROLOGY_ALGORITHM)),
        )


class HydrologyGenerator:
    """Deterministic RC14 hydrology planner and Phase-3 geography read model.

    The important seam change from Dev1/Dev2 is ``prepare_window``: every
    hydrology domain needed by a prepared exploration envelope is solved inside
    one larger Priority-Flood lattice, then sliced into per-domain cache records.
    Adjacent prepared domains therefore share exactly the same overlap fields.

    Future background-ring preparation can extend this contract without making
    the renderer or movement loop the owner of generation work.
    """

    def __init__(self, world_generator: "WorldGenerator", cache_source: Any | None = None,
                 version: int = HYDROLOGY_VERSION):
        self.world_generator = world_generator
        self.seed = world_generator.world_seed
        self.cache_source = cache_source
        self.version = int(version)
        self._domain_cache: dict[tuple[int, int], HydrologyDomain] = {}

    @staticmethod
    def domain_for_world(x: int, y: int) -> tuple[int, int]:
        span = HYDROLOGY_DOMAIN_NODES * HYDROLOGY_LATTICE_SPACING
        return int(x) // span, int(y) // span

    @staticmethod
    def domains_for_world_bounds(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
        ax, ay = HydrologyGenerator.domain_for_world(min(x0, x1), min(y0, y1))
        bx, by = HydrologyGenerator.domain_for_world(max(x0, x1), max(y0, y1))
        return ax, bx, ay, by

    def _remember(self, domain: HydrologyDomain) -> HydrologyDomain:
        if len(self._domain_cache) >= 24 and (domain.domain_x, domain.domain_y) not in self._domain_cache:
            self._domain_cache.clear()
        self._domain_cache[(domain.domain_x, domain.domain_y)] = domain
        return domain

    def cached_domain(self, domain_x: int, domain_y: int) -> HydrologyDomain | None:
        """Read an existing plan only; never solve drainage during inspection."""
        key = (int(domain_x), int(domain_y))
        if key in self._domain_cache:
            return self._domain_cache[key]
        loader = getattr(self.cache_source, "load_generated_hydrology_domain", None)
        if callable(loader):
            raw = loader(key[0], key[1], self.version)
            if raw:
                try:
                    domain = HydrologyDomain.from_payload(raw)
                    if (domain.domain_x, domain.domain_y) == key and domain.fingerprint == self._fingerprint_payload(domain.to_payload()):
                        return self._remember(domain)
                except (KeyError, TypeError, ValueError, IndexError):
                    pass
        return None

    def load_or_generate(self, domain_x: int, domain_y: int, *, persist: bool = False) -> HydrologyDomain:
        domain = self.cached_domain(domain_x, domain_y)
        if domain is None:
            domain = self.generate(int(domain_x), int(domain_y))
        # A previously generated in-memory plan must still be written when the
        # caller explicitly requests persistence (Dev3 returned too early).
        if persist:
            self._store_domains((domain,))
        return self._remember(domain)

    def prepare_world_bounds(self, x0: int, y0: int, x1: int, y1: int, *, persist: bool = True,
                             progress=None) -> tuple[HydrologyDomain, ...]:
        min_dx, max_dx, min_dy, max_dy = self.domains_for_world_bounds(x0, y0, x1, y1)
        return self.prepare_window(min_dx, max_dx, min_dy, max_dy, persist=persist, progress=progress)

    def prepare_window(self, min_dx: int, max_dx: int, min_dy: int, max_dy: int, *, persist: bool = True,
                       progress=None) -> tuple[HydrologyDomain, ...]:
        """Solve a rectangular set of adjacent domains as one seam-safe lattice."""
        min_dx, max_dx = sorted((int(min_dx), int(max_dx)))
        min_dy, max_dy = sorted((int(min_dy), int(max_dy)))
        wanted = [(dx, dy) for dy in range(min_dy, max_dy + 1) for dx in range(min_dx, max_dx + 1)]

        # If every domain is already a current-algorithm cache, loading is cheap
        # and no raw planning work occurs.
        loaded: list[HydrologyDomain] = []
        loader = getattr(self.cache_source, "load_generated_hydrology_domain", None)
        if callable(loader):
            all_current = True
            for dx, dy in wanted:
                if (dx, dy) in self._domain_cache:
                    loaded.append(self._domain_cache[(dx, dy)])
                    continue
                raw = loader(dx, dy, self.version)
                try:
                    domain = HydrologyDomain.from_payload(raw) if raw else None
                    if not domain or domain.fingerprint != self._fingerprint_payload(domain.to_payload()):
                        all_current = False
                        break
                    loaded.append(self._remember(domain))
                except Exception:
                    all_current = False
                    break
            if all_current and len(loaded) == len(wanted):
                return tuple(loaded)

        core = HYDROLOGY_DOMAIN_NODES
        halo = HYDROLOGY_HALO_NODES
        spacing = HYDROLOGY_LATTICE_SPACING
        domain_count_x = max_dx - min_dx + 1
        domain_count_y = max_dy - min_dy + 1
        width = domain_count_x * core + halo * 2
        height = domain_count_y * core + halo * 2
        origin_node_x = min_dx * core - halo
        origin_node_y = min_dy * core - halo

        if progress:
            progress(0, 5, f"sampling {domain_count_x}x{domain_count_y} hydrology domains")
        elevation, moisture = self._sample_grid(width, height, origin_node_x, origin_node_y, spacing)
        if progress:
            progress(1, 5, "resolving depressions")
        filled, flood_parent, flood_rank = self._priority_flood(elevation, width, height, origin_node_x, origin_node_y)
        if progress:
            progress(2, 5, "deriving drainage and accumulation")
        flow_to = self._assign_flow(elevation, filled, flood_parent, width, height, origin_node_x, origin_node_y)
        accumulation = self._accumulate(flow_to, filled, flood_rank, moisture)
        if progress:
            progress(3, 5, "labeling watersheds and river hierarchy")
        watersheds, outlets = self._watersheds(flow_to, filled, flood_rank, width, height, origin_node_x, origin_node_y)
        river_class = self._classify_rivers(accumulation, moisture)
        floodplain = self._floodplains(river_class, accumulation, elevation, width, height)

        domains: list[HydrologyDomain] = []
        for dy in range(min_dy, max_dy + 1):
            for dx in range(min_dx, max_dx + 1):
                slice_x = (dx - min_dx) * core
                slice_y = (dy - min_dy) * core
                domains.append(self._slice_domain(
                    dx, dy, width, height, origin_node_x, origin_node_y,
                    elevation, filled, flow_to, accumulation, watersheds, river_class, floodplain, outlets,
                    slice_x, slice_y,
                ))
        if progress:
            progress(4, 5, "persisting hydrology base plan")
        if persist:
            self._store_domains(domains)
        for domain in domains:
            self._remember(domain)
        if progress:
            progress(5, 5, f"prepared {len(domains)} hydrology domain(s)")
        return tuple(domains)

    def generate(self, domain_x: int, domain_y: int) -> HydrologyDomain:
        """Standalone deterministic domain generation for tools/tests.

        Startup/pregeneration should prefer ``prepare_window`` because a window
        gives adjacent domains one shared outer boundary and therefore a seam-
        consistent overlap.
        """
        core = HYDROLOGY_DOMAIN_NODES
        halo = HYDROLOGY_HALO_NODES
        spacing = HYDROLOGY_LATTICE_SPACING
        width = height = core + halo * 2
        origin_node_x = int(domain_x) * core - halo
        origin_node_y = int(domain_y) * core - halo
        elevation, moisture = self._sample_grid(width, height, origin_node_x, origin_node_y, spacing)
        filled, flood_parent, flood_rank = self._priority_flood(elevation, width, height, origin_node_x, origin_node_y)
        flow_to = self._assign_flow(elevation, filled, flood_parent, width, height, origin_node_x, origin_node_y)
        accumulation = self._accumulate(flow_to, filled, flood_rank, moisture)
        watersheds, outlets = self._watersheds(flow_to, filled, flood_rank, width, height, origin_node_x, origin_node_y)
        river_class = self._classify_rivers(accumulation, moisture)
        floodplain = self._floodplains(river_class, accumulation, elevation, width, height)
        payload = self._payload(
            int(domain_x), int(domain_y), origin_node_x, origin_node_y, width, height,
            elevation, filled, flow_to, accumulation, watersheds, river_class, floodplain, outlets,
        )
        fingerprint = canonical_hash(payload)
        return HydrologyDomain(
            int(domain_x), int(domain_y), self.version, spacing, core, halo, origin_node_x, origin_node_y,
            width, height, tuple(elevation), tuple(filled), tuple(flow_to), tuple(accumulation),
            tuple(watersheds), tuple(river_class), tuple(floodplain), tuple(outlets), fingerprint,
            HYDROLOGY_ALGORITHM,
        )

    def _sample_grid(self, width: int, height: int, ox: int, oy: int, spacing: int):
        total = width * height
        elevation = [0] * total
        moisture = [0] * total
        for ly in range(height):
            gy = oy + ly
            wy = gy * spacing
            row = ly * width
            for lx in range(width):
                gx = ox + lx
                fields = self.world_generator.sample_fields(WorldPos(gx * spacing, wy, 0))
                elevation[row + lx] = int(fields.elevation)
                moisture[row + lx] = int(fields.moisture)
        return elevation, moisture

    def _slice_domain(self, dx: int, dy: int, mega_width: int, mega_height: int, mega_ox: int, mega_oy: int,
                      elevation, filled, flow_to, accumulation, watersheds, river_class, floodplain, outlets,
                      slice_x: int, slice_y: int) -> HydrologyDomain:
        core = HYDROLOGY_DOMAIN_NODES
        halo = HYDROLOGY_HALO_NODES
        width = height = core + halo * 2
        origin_node_x = dx * core - halo
        origin_node_y = dy * core - halo

        mega_to_local: dict[int, int] = {}
        local_to_mega: list[int] = []
        for ly in range(height):
            my = slice_y + ly
            for lx in range(width):
                mx = slice_x + lx
                mi = my * mega_width + mx
                li = ly * width + lx
                mega_to_local[mi] = li
                local_to_mega.append(mi)

        def values(source):
            return [int(source[mi]) for mi in local_to_mega]

        local_flow: list[int] = []
        for mi in local_to_mega:
            target = int(flow_to[mi])
            local_flow.append(mega_to_local.get(target, -1) if target >= 0 else -1)

        basin_ids = set(values(watersheds))
        domain_outlets = [tuple(map(int, out)) for out in outlets if int(out[2]) in basin_ids]
        # A slice may not contain the actual planning-window outlet. Keep one
        # representative for every basin so cache/debug consumers retain basin
        # identity without inventing a second watershed authority.
        known = {b for _, _, b in domain_outlets}
        if basin_ids - known:
            reps: dict[int, tuple[int, int, int]] = {}
            for li, bid in enumerate(values(watersheds)):
                if bid in known or bid in reps:
                    continue
                gx = origin_node_x + (li % width)
                gy = origin_node_y + (li // width)
                reps[bid] = (gx, gy, bid)
            domain_outlets.extend(reps.values())

        payload = self._payload(
            dx, dy, origin_node_x, origin_node_y, width, height,
            values(elevation), values(filled), local_flow, values(accumulation), values(watersheds),
            values(river_class), values(floodplain), sorted(domain_outlets),
        )
        fingerprint = canonical_hash(payload)
        return HydrologyDomain(
            dx, dy, self.version, HYDROLOGY_LATTICE_SPACING, core, halo, origin_node_x, origin_node_y,
            width, height, tuple(payload["elevation"]), tuple(payload["filled_elevation"]),
            tuple(payload["flow_to"]), tuple(payload["accumulation"]), tuple(payload["watershed_id"]),
            tuple(payload["river_class"]), tuple(payload["floodplain_strength"]),
            tuple(tuple(v) for v in payload["outlets"]), fingerprint, HYDROLOGY_ALGORITHM,
        )

    def _payload(self, dx, dy, ox, oy, width, height, elevation, filled, flow_to, accumulation, watersheds,
                 river_class, floodplain, outlets) -> dict[str, Any]:
        return {
            "algorithm": HYDROLOGY_ALGORITHM,
            "domain_x": int(dx), "domain_y": int(dy), "version": self.version,
            "lattice_spacing": HYDROLOGY_LATTICE_SPACING,
            "core_nodes": HYDROLOGY_DOMAIN_NODES, "halo_nodes": HYDROLOGY_HALO_NODES,
            "origin_node_x": int(ox), "origin_node_y": int(oy),
            "width": int(width), "height": int(height),
            "elevation": list(map(int, elevation)), "filled_elevation": list(map(int, filled)),
            "flow_to": list(map(int, flow_to)), "accumulation": list(map(int, accumulation)),
            "watershed_id": list(map(int, watersheds)), "river_class": list(map(int, river_class)),
            "floodplain_strength": list(map(int, floodplain)),
            "outlets": [list(map(int, v)) for v in outlets],
        }

    def _store_domains(self, domains) -> None:
        storer = getattr(self.cache_source, "store_generated_hydrology_domain", None)
        if callable(storer):
            for domain in domains:
                storer(domain.domain_x, domain.domain_y, self.version, domain.to_payload(), domain.fingerprint)
            commit = getattr(self.cache_source, "commit_generated", None)
            if callable(commit):
                commit()

    @staticmethod
    def _neighbors(index: int, width: int, height: int):
        x, y = index % width, index // width
        for dx, dy in D8:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                yield ny * width + nx

    def _priority_flood(self, elevation: list[int], width: int, height: int, ox: int, oy: int):
        total = width * height
        filled = list(elevation)
        parent = [-1] * total
        rank = [-1] * total
        visited = bytearray(total)
        heap: list[tuple[int, int, int, int]] = []

        def push(i: int) -> None:
            if visited[i]:
                return
            visited[i] = 1
            x, y = i % width, i // width
            heapq.heappush(heap, (filled[i], oy + y, ox + x, i))

        for x in range(width):
            push(x)
            push((height - 1) * width + x)
        for y in range(1, height - 1):
            push(y * width)
            push(y * width + width - 1)

        order = 0
        while heap:
            level, _, _, cur = heapq.heappop(heap)
            rank[cur] = order
            order += 1
            for nxt in self._neighbors(cur, width, height):
                if visited[nxt]:
                    continue
                visited[nxt] = 1
                parent[nxt] = cur
                if filled[nxt] < level:
                    filled[nxt] = level
                x, y = nxt % width, nxt // width
                heapq.heappush(heap, (filled[nxt], oy + y, ox + x, nxt))
        return filled, parent, rank

    def _assign_flow(self, elevation, filled, parent, width, height, ox, oy):
        total = width * height
        flow = [-1] * total
        for i in range(total):
            x, y = i % width, i // width
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                continue
            lower = [n for n in self._neighbors(i, width, height) if filled[n] < filled[i]]
            if lower:
                flow[i] = min(lower, key=lambda n: (filled[n], elevation[n], oy + n // width, ox + n % width))
            else:
                flow[i] = parent[i]
        return flow

    @staticmethod
    def _runoff(moisture: int) -> int:
        return 1 + max(0, min(7, int(moisture) // 8192))

    def _accumulate(self, flow, filled, rank, moisture):
        acc = [self._runoff(m) for m in moisture]
        order = sorted(range(len(flow)), key=lambda i: (filled[i], rank[i]), reverse=True)
        for i in order:
            target = flow[i]
            if target >= 0:
                acc[target] += acc[i]
        return acc

    def _watersheds(self, flow, filled, rank, width, height, ox, oy):
        basins = [0] * len(flow)
        outlets: list[tuple[int, int, int]] = []
        order = sorted(range(len(flow)), key=lambda i: (filled[i], rank[i]))
        for i in order:
            target = flow[i]
            if target < 0:
                gx, gy = ox + i % width, oy + i // width
                bid = int(hash_u64(self.seed, "hydrology-basin-v1", self.version, gx, gy) & 0x7FFFFFFF) or 1
                basins[i] = bid
                outlets.append((gx, gy, bid))
            else:
                basins[i] = basins[target]
        return basins, sorted(outlets)

    @staticmethod
    def _classify_rivers(accumulation, moisture):
        out = [0] * len(accumulation)
        for i, value in enumerate(accumulation):
            dry = max(0, (65535 - int(moisture[i])) // 2048)
            minor = 72 + dry
            river = minor * 4
            major = minor * 12
            out[i] = 3 if value >= major else 2 if value >= river else 1 if value >= minor else 0
        return out

    def _floodplains(self, river_class, accumulation, elevation, width, height):
        result = [0] * len(river_class)
        for i, cls in enumerate(river_class):
            if cls <= 0:
                continue
            neighbors = list(self._neighbors(i, width, height))
            relief = 0 if not neighbors else max(elevation[n] for n in neighbors) - min(elevation[n] for n in neighbors)
            strength = max(0, min(100, cls * 24 + accumulation[i] // 48 - relief // 220))
            result[i] = strength
            if cls >= 2 and strength > 12:
                for n in neighbors:
                    result[n] = max(result[n], max(0, strength - 22))
        return result

    @staticmethod
    def _fingerprint_payload(raw: dict[str, Any]) -> str:
        data = dict(raw)
        expected = str(data.pop("fingerprint", ""))
        actual = canonical_hash(data)
        return actual if expected == actual or not expected else ""

    @staticmethod
    def _segment_contains(px: int, py: int, ax: int, ay: int, bx: int, by: int, radius: int) -> bool:
        """Integer-only point/segment radius test for deterministic projection."""
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        vv = vx * vx + vy * vy
        rr = int(radius) * int(radius)
        if vv <= 0:
            return wx * wx + wy * wy <= rr
        dot = wx * vx + wy * vy
        if dot <= 0:
            return wx * wx + wy * wy <= rr
        if dot >= vv:
            dx, dy = px - bx, py - by
            return dx * dx + dy * dy <= rr
        cross = wx * vy - wy * vx
        return cross * cross <= rr * vv

    def _meander_midpoint(self, gx: int, gy: int, tx: int, ty: int) -> tuple[int, int]:
        spacing = HYDROLOGY_LATTICE_SPACING
        ax, ay = gx * spacing, gy * spacing
        bx, by = tx * spacing, ty * spacing
        mx, my = (ax + bx) // 2, (ay + by) // 2
        jitter = int(hash_u64(self.seed, "hydrology-meander-v1", self.version, gx, gy, tx, ty) % 5) - 2
        dx, dy = bx - ax, by - ay
        if dx == 0:
            mx += jitter
        elif dy == 0:
            my += jitter
        else:
            mx += (-1 if dy > 0 else 1) * jitter
            my += (1 if dx > 0 else -1) * jitter
        return mx, my

    @staticmethod
    def _interpolate_field(domain: HydrologyDomain, field, x: int, y: int) -> int:
        spacing=domain.lattice_spacing
        gx=x//spacing;gy=y//spacing;rx=x%spacing;ry=y%spacing
        coords=((gx,gy),(gx+1,gy),(gx,gy+1),(gx+1,gy+1))
        idx=[domain.global_index(a,b) for a,b in coords]
        if any(i is None for i in idx):
            fallback=domain.global_index(gx,gy)
            return int(field[fallback]) if fallback is not None else 0
        a,b,c,d=(int(field[i]) for i in idx)
        top=a*(spacing-rx)+b*rx;bottom=c*(spacing-rx)+d*rx
        return (top*(spacing-ry)+bottom*ry)//(spacing*spacing)

    @staticmethod
    def _interpolate_fill_depth(domain: HydrologyDomain, x: int, y: int) -> int:
        """Interpolate depression fill depth without allocating a derived grid.

        ``surface_at`` is queried for every generated surface cell, so building a
        full ``filled-elevation`` array per query turns a cheap read model into an
        O(domain_cells * world_cells) operation.  Reading only the four bilinear
        corners keeps the Phase-3 projection bounded and deterministic.
        """
        spacing = domain.lattice_spacing
        gx, gy = x // spacing, y // spacing
        rx, ry = x % spacing, y % spacing
        coords = ((gx, gy), (gx + 1, gy), (gx, gy + 1), (gx + 1, gy + 1))
        idx = [domain.global_index(a, b) for a, b in coords]
        if any(i is None for i in idx):
            fallback = domain.global_index(gx, gy)
            if fallback is None:
                return 0
            return max(0, int(domain.filled_elevation[fallback]) - int(domain.elevation[fallback]))
        values = [max(0, int(domain.filled_elevation[i]) - int(domain.elevation[i])) for i in idx]
        a, b, c, d = values
        top = a * (spacing - rx) + b * rx
        bottom = c * (spacing - rx) + d * rx
        return (top * (spacing - ry) + bottom * ry) // (spacing * spacing)

    def surface_at(self, pos: WorldPos, *, prepared_only: bool = False) -> HydrologySurface | None:
        if pos.z != 0:
            return HydrologySurface()
        dx, dy = self.domain_for_world(pos.x, pos.y)
        domain = self.cached_domain(dx, dy) if prepared_only else self.load_or_generate(dx, dy)
        if domain is None:
            return None
        spacing = domain.lattice_spacing
        node_x = pos.x // spacing
        node_y = pos.y // spacing

        nearest_idx = domain.global_index(node_x, node_y)
        if nearest_idx is None:
            return HydrologySurface()
        watershed = int(domain.watershed_id[nearest_idx])
        fp = self._interpolate_field(domain,domain.floodplain_strength,pos.x,pos.y)
        fields = self.world_generator.sample_fields(pos)

        # Filled-depth marks natural depressions. Bilinear interpolation turns
        # the coarse depression lattice into contiguous basin contours; a low-
        # frequency deterministic threshold perturbation avoids square/grid lake
        # outlines without adding a second random water authority.
        fill_depth = self._interpolate_fill_depth(domain, pos.x, pos.y)
        lake_noise=self.world_generator._value_noise("hydrology-lake-edge-v1",pos.x+19031,pos.y-7717,48)
        lake_threshold=1350+((lake_noise-32768)*500//65535)
        lake=fields.moisture>=30000 and fields.elevation>=23800 and fill_depth>=lake_threshold
        if lake:
            wet = min(100, 65 + fill_depth // 120)
            return HydrologySurface(
                watershed_id=watershed, river_class=0, river_width=0, river_depth_class=3,
                floodplain_strength=max(fp, 70), wetland_probability=wet,
                water_access_score=100, flood_risk=90, crossing_cost=1000,
                lake=True, ford=False, terrain_override=(
                    ('core:lake_shallow' if fill_depth < lake_threshold+650 else 'core:lake_deep')
                    if self.world_generator.version>=6 else 'core:water'),
            )

        bank = False
        best_cls = 0
        best_width = 0
        best_inner = False
        best_ford = False
        best_acc = 0
        best_slope = 0
        best_fp = fp
        # A two-node neighborhood is enough because the longest D8 segment is
        # ~23 cells and the widest major channel is under 10 cells in this pass.
        for gy in range(node_y - 2, node_y + 3):
            for gx in range(node_x - 2, node_x + 3):
                idx = domain.global_index(gx, gy)
                if idx is None:
                    continue
                cls = int(domain.river_class[idx])
                target = int(domain.flow_to[idx])
                if cls <= 0 or target < 0:
                    continue
                tx, ty = domain.global_node_xy(target)
                ax, ay = gx * spacing, gy * spacing
                bx, by = tx * spacing, ty * spacing
                mx, my = self._meander_midpoint(gx, gy, tx, ty)
                width = 2 if cls == 1 else 4 if cls == 2 else 7
                on_channel = (
                    self._segment_contains(pos.x, pos.y, ax, ay, mx, my, width)
                    or self._segment_contains(pos.x, pos.y, mx, my, bx, by, width)
                )
                if not on_channel:
                    if self.world_generator.version>=6:
                        bank = bank or self._segment_contains(pos.x,pos.y,ax,ay,mx,my,width+2) or self._segment_contains(pos.x,pos.y,mx,my,bx,by,width+2)
                    continue
                acc = int(domain.accumulation[idx])
                inner_radius = 1 if cls == 1 else 2 if cls == 2 else 4
                inner = (
                    self._segment_contains(pos.x, pos.y, ax, ay, mx, my, inner_radius)
                    or self._segment_contains(pos.x, pos.y, mx, my, bx, by, inner_radius)
                )
                seg_hash = hash_u64(self.seed, "hydrology-ford-v1", self.version, gx, gy, tx, ty)
                ford_mod = 6 if cls == 1 else 11 if cls == 2 else 23
                ford = (seg_hash % ford_mod) == 0
                if cls > best_cls or (cls == best_cls and acc > best_acc):
                    best_cls, best_width, best_inner, best_ford, best_acc = cls, width, inner, ford, acc
                    best_slope = max(0,domain.filled_elevation[idx]-domain.filled_elevation[target])
                    best_fp = max(best_fp, int(domain.floodplain_strength[idx]))
                    watershed = int(domain.watershed_id[idx])

        if best_cls:
            # Minor streams and explicit ford segments are wadeable. Medium and
            # major channels have a deep core but retain shallow banks.
            shallow = best_cls == 1 or best_ford or not best_inner
            depth = 1 if shallow else 2 if best_cls == 2 else 3
            crossing = 2 if best_cls == 1 else 5 if shallow else 80 if best_cls == 2 else 1000
            terrain = "core:river_shallow" if shallow else "core:river"
            if self.world_generator.version>=6:
                if best_cls==1:terrain='core:stream'
                elif not shallow and best_slope>750:terrain='core:river_rapids' 
            return HydrologySurface(
                watershed_id=watershed, river_class=best_cls, river_width=best_width,
                river_depth_class=depth, floodplain_strength=max(best_fp, 20 + best_cls * 15),
                wetland_probability=max(0, min(100, best_fp // 2 + fields.moisture // 1800)),
                water_access_score=100, flood_risk=min(100, 45 + best_cls * 16 + best_fp // 3),
                crossing_cost=crossing, lake=False, ford=best_ford, terrain_override=terrain,
            )

        if bank and fields.elevation>=23800:
            return HydrologySurface(watershed_id=watershed, floodplain_strength=fp,
                water_access_score=80, flood_risk=55, terrain_override='core:riverbank')
        wetland = max(0, min(100, fp + (fields.moisture - 33000) // 600))
        if fp >= 30 and fields.moisture >= 39000 and fields.elevation >= 23800:
            return HydrologySurface(
                watershed_id=watershed, floodplain_strength=fp, wetland_probability=wetland,
                water_access_score=min(95, 45 + fp // 2), flood_risk=min(95, fp + 20),
                crossing_cost=4, terrain_override="core:wetland",
            )
        if fp >= 18 and fields.elevation >= 23800:
            return HydrologySurface(
                watershed_id=watershed, floodplain_strength=fp, wetland_probability=wetland,
                water_access_score=min(85, 30 + fp // 2), flood_risk=min(90, fp + 10),
                crossing_cost=1, terrain_override="core:floodplain",
            )
        return HydrologySurface(
            watershed_id=watershed, floodplain_strength=fp, wetland_probability=wetland,
            water_access_score=min(60, fp), flood_risk=min(80, fp), crossing_cost=0,
        )


def audit_domain(domain: HydrologyDomain) -> list[str]:
    """Return invariant violations for one generated hydrology domain."""
    issues: list[str] = []
    n = domain.width * domain.height
    if domain.algorithm != HYDROLOGY_ALGORITHM:
        issues.append("stale hydrology algorithm")
    if not all(len(v) == n for v in (
        domain.elevation, domain.filled_elevation, domain.flow_to, domain.accumulation,
        domain.watershed_id, domain.river_class, domain.floodplain_strength,
    )):
        return issues + ["array length mismatch"]

    for i in domain.core_indices():
        if domain.flow_to[i] < 0:
            issues.append(f"core sink at {domain.global_node_xy(i)}")
            if len(issues) >= 20:
                break
        seen: set[int] = set()
        cur = i
        for _ in range(n + 1):
            if cur < 0:
                break
            if cur in seen:
                issues.append(f"flow cycle from {domain.global_node_xy(i)}")
                break
            seen.add(cur)
            nxt = domain.flow_to[cur]
            if nxt >= 0 and domain.accumulation[nxt] < domain.accumulation[cur]:
                issues.append(f"accumulation decreases downstream at {domain.global_node_xy(cur)}")
                break
            cur = nxt
        else:
            issues.append(f"flow did not terminate from {domain.global_node_xy(i)}")
        if len(issues) >= 20:
            break

    river_cells = sum(1 for i in domain.core_indices() if domain.river_class[i] > 0)
    core_total = domain.core_nodes * domain.core_nodes
    if river_cells > core_total // 3:
        issues.append(f"river coverage too high: {river_cells}/{core_total}")
    if not domain.outlets:
        issues.append("domain has no outlets")
    return issues


def audit_window_seams(domains: tuple[HydrologyDomain, ...] | list[HydrologyDomain]) -> list[str]:
    """Verify overlapping prepared domains agree on shared base fields."""
    issues: list[str] = []
    by_key = {(d.domain_x, d.domain_y): d for d in domains}
    attrs = ("elevation", "filled_elevation", "accumulation", "watershed_id", "river_class", "floodplain_strength")
    for (dx, dy), a in sorted(by_key.items()):
        for nk in ((dx + 1, dy), (dx, dy + 1)):
            b = by_key.get(nk)
            if not b:
                continue
            amap = {a.global_node_xy(i): i for i in range(a.width * a.height)}
            bmap = {b.global_node_xy(i): i for i in range(b.width * b.height)}
            for g in sorted(amap.keys() & bmap.keys()):
                ia, ib = amap[g], bmap[g]
                # The outermost slice ring is an unresolved planning margin by
                # design; only the interior overlap can project into either
                # domain's authoritative core.
                if a.is_outer_boundary(ia) or b.is_outer_boundary(ib):
                    continue
                for attr in attrs:
                    if getattr(a, attr)[ia] != getattr(b, attr)[ib]:
                        issues.append(f"{attr} seam mismatch at {g} between {(dx,dy)} and {nk}")
                        break
                if len(issues) >= 20:
                    return issues
                fa, fb = a.flow_to[ia], b.flow_to[ib]
                ga = a.global_node_xy(fa) if fa >= 0 else None
                gb = b.global_node_xy(fb) if fb >= 0 else None
                if ga != gb:
                    issues.append(f"flow seam mismatch at {g} between {(dx,dy)} and {nk}")
                    if len(issues) >= 20:
                        return issues
    return issues
