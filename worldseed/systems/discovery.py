"""Cell-exact exploration memory, stored as compact 32x32 chunk bitsets.

The list and set interfaces are compatibility views. They expand tokens only
when explicitly iterated; adding a cell updates one chunk and its surface view.
Current visibility belongs to Simulation and is deliberately absent here.
"""
from __future__ import annotations

from collections.abc import Collection, MutableSet, Set
from collections import OrderedDict

DISCOVERY_FORMAT_VERSION = 1
CHUNK_SIDE = 32
CHUNK_CELLS = CHUNK_SIDE * CHUNK_SIDE
MEMBERSHIP_CACHE_LIMIT = 8192


def _coordinates(token: str) -> tuple[int, int, int]:
    if not isinstance(token, str):
        raise ValueError('discovered cell must be an x,y,z string')
    try:
        parts = token.split(',')
        if len(parts) != 3:
            raise ValueError
        coordinates = tuple(int(part) for part in parts)
    except (TypeError, ValueError):
        raise ValueError(f'invalid discovered cell: {token!r}') from None
    if token != ','.join(map(str, coordinates)):
        raise ValueError(f'noncanonical discovered cell: {token!r}')
    return coordinates


def validate_discovery_chunks(chunks, version) -> list[str]:
    """Validate optional additive schema-3 fields before importing any memory."""
    issues = []
    if type(version) is not int or version != DISCOVERY_FORMAT_VERSION:
        issues.append('unsupported discovered_format_version')
    if not isinstance(chunks, dict):
        return issues + ['discovered_chunks must be an object']
    for key, encoded in chunks.items():
        try:
            _coordinates(key)
        except ValueError:
            issues.append(f'invalid discovered chunk key: {key!r}')
        if (not isinstance(encoded, str) or not 1 <= len(encoded) <= CHUNK_CELLS // 4
                or any(char not in '0123456789abcdefABCDEF' for char in encoded)):
            issues.append(f'invalid discovered chunk mask: {key!r}')
            continue
        if not int(encoded, 16):
            issues.append(f'empty discovered chunk mask: {key!r}')
    return issues


class ChunkCells(Set[int]):
    """Compact read-only set view used by atlas chunk queries."""
    __slots__ = ('mask',)

    def __init__(self, mask=0):
        self.mask = mask

    @classmethod
    def _from_iterable(cls, values):
        # Set algebra returns an independent read-only value, never a view
        # whose integer bitmask was accidentally replaced by a generator.
        return frozenset(values)

    def __len__(self):
        return self.mask.bit_count()

    def __contains__(self, index):
        return (isinstance(index, int) and 0 <= index < CHUNK_CELLS
                and bool(self.mask & (1 << index)))

    def __iter__(self):
        mask = self.mask
        while mask:
            bit = mask & -mask
            yield bit.bit_length() - 1
            mask ^= bit


class DiscoveryTiles(Collection[str]):
    """Unique explored cells with legacy list-compatible reads and append.

    Discovery has no ordering authority. Iteration is stable chunk insertion
    order, then cell order; explicit legacy export can request lexical order.
    No token list or lifetime-sized per-cell set is retained in memory.
    """
    def __init__(self, tokens=()):
        self._chunks: dict[tuple[int, int, int], int] = {}
        self._count = 0
        self._membership_cache: OrderedDict[str, bool] = OrderedDict()
        self.surface_chunks: set[tuple[int, int]] = set()
        self.surface_cells: dict[tuple[int, int], ChunkCells] = {}
        self.extend(tokens)

    @classmethod
    def from_chunks(cls, chunks, version=DISCOVERY_FORMAT_VERSION):
        issues = validate_discovery_chunks(chunks, version)
        if issues:
            raise ValueError('; '.join(issues))
        out = cls()
        for token, encoded in chunks.items():
            key = _coordinates(token)
            mask = int(encoded, 16)
            out._chunks[key] = mask
            out._count += mask.bit_count()
            if key[2] == 0:
                surface_key = key[:2]
                out.surface_chunks.add(surface_key)
                out.surface_cells[surface_key] = ChunkCells(mask)
        return out

    def to_chunks(self) -> dict[str, str]:
        return {','.join(map(str, key)): format(mask, 'x')
                for key, mask in self._chunks.items()}

    def export_legacy(self, *, sorted_tokens=False) -> list[str]:
        """Explicit, uncapped legacy cell-list export (potentially expensive)."""
        return sorted(self) if sorted_tokens else list(self)

    def __len__(self):
        return self._count

    def __contains__(self, token):
        if not isinstance(token, str):
            return False
        cached = self._membership_cache.get(token)
        if cached is not None:
            return cached
        try:
            x, y, z = _coordinates(token)
        except ValueError:
            return False
        index = (y % CHUNK_SIDE) * CHUNK_SIDE + x % CHUNK_SIDE
        found = bool(self._chunks.get((x // CHUNK_SIDE, y // CHUNK_SIDE, z), 0)
                     & (1 << index))
        # Repeated viewport membership reads avoid parsing coordinate strings.
        # The cache is transient and bounded independently of explored history.
        if len(self._membership_cache) >= MEMBERSHIP_CACHE_LIMIT:
            self._membership_cache.popitem(last=False)
        self._membership_cache[token] = found
        return found

    def __iter__(self):
        for (cx, cy, z), mask in self._chunks.items():
            for index in ChunkCells(mask):
                yield f'{cx * CHUNK_SIDE + index % CHUNK_SIDE},{cy * CHUNK_SIDE + index // CHUNK_SIDE},{z}'

    def __getitem__(self, index):
        return list(self)[index]

    def __eq__(self, other):
        if isinstance(other, DiscoveryTiles):
            return self._chunks == other._chunks
        if isinstance(other, (list, tuple)):
            return list(self) == list(other)
        return NotImplemented

    def append(self, token: str) -> bool:
        x, y, z = _coordinates(token)
        key = (x // CHUNK_SIDE, y // CHUNK_SIDE, z)
        bit = 1 << ((y % CHUNK_SIDE) * CHUNK_SIDE + x % CHUNK_SIDE)
        previous = self._chunks.get(key, 0)
        if previous & bit:
            return False
        mask = previous | bit
        self._chunks[key] = mask
        self._membership_cache.pop(token, None)
        self._count += 1
        if z == 0:
            surface_key = key[:2]
            self.surface_chunks.add(surface_key)
            cells = self.surface_cells.get(surface_key)
            if cells is None:
                self.surface_cells[surface_key] = ChunkCells(mask)
            else:
                cells.mask = mask
        return True

    def extend(self, tokens):
        for token in tokens:
            self.append(token)

    def discard(self, token):
        if token not in self:
            return
        x, y, z = _coordinates(token)
        key = (x // CHUNK_SIDE, y // CHUNK_SIDE, z)
        mask = self._chunks[key] & ~(1 << ((y % CHUNK_SIDE) * CHUNK_SIDE + x % CHUNK_SIDE))
        self._count -= 1
        self._membership_cache.pop(token, None)
        if mask:
            self._chunks[key] = mask
        else:
            del self._chunks[key]
        if z == 0:
            if mask:
                self.surface_cells[key[:2]].mask = mask
            else:
                self.surface_chunks.discard(key[:2])
                self.surface_cells.pop(key[:2], None)

    def clear(self):
        self._chunks.clear()
        self._count = 0
        self._membership_cache.clear()
        self.surface_chunks.clear()
        self.surface_cells.clear()


class DiscoverySet(MutableSet[str]):
    """Set-compatible membership view over compact exploration memory."""
    def __init__(self, tiles: DiscoveryTiles):
        self.tiles = tiles if isinstance(tiles, DiscoveryTiles) else DiscoveryTiles(tiles)

    def __contains__(self, token):
        return token in self.tiles

    def __iter__(self):
        return iter(self.tiles)

    def __len__(self):
        return len(self.tiles)

    def add(self, token):
        self.tiles.append(token)

    def update(self, tokens):
        self.tiles.extend(tokens)

    def discard(self, token):
        self.tiles.discard(token)

    def clear(self):
        self.tiles.clear()

    def copy(self):
        return set(self)

    def difference(self, *others):
        return set(self).difference(*others)

    def intersection(self, *others):
        return set(self).intersection(*others)

    def union(self, *others):
        return set(self).union(*others)

    def symmetric_difference(self, other):
        return set(self).symmetric_difference(other)

    def issubset(self, other):
        return all(token in other for token in self)

    def issuperset(self, other):
        return all(token in self for token in other)
