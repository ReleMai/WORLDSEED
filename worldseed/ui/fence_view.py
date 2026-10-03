"""Connected split rails projected from prepared fence/gate cells only."""
from __future__ import annotations


def is_fence(piece):
    return bool(piece and {'fence', 'gate'} & set(getattr(piece, 'tags', ())))


def connection_bits(key, cells, registry):
    x, y, z = key
    bits = 0
    for bit, dx, dy in ((1, 0, -1), (2, 1, 0), (4, 0, 1), (8, -1, 0)):
        neighbor = cells.get((x + dx, y + dy, z))
        if neighbor is not None and is_fence(registry.settlement_pieces.get(neighbor.structure_piece_id)):
            bits |= bit
    return bits


def fence_surface(term, piece, size, bits):
    """Rails meet exactly at tile edges; open gates retain a visible leaf."""
    gate = 'gate' in set(getattr(piece, 'tags', ()))
    cache = getattr(term, '_fence_surface_cache', None)
    if cache is None:
        cache = term._fence_surface_cache = {}
    key = (str(piece.id), size, bits, gate)
    if key in cache:
        return cache[key]
    pg = term.pg
    surface = pg.Surface((size, size), pg.SRCALPHA)
    mid = size // 2
    rail = max(2, size // 12)
    separation = max(2, size // 7)
    low, wood, high = (66, 44, 27), (138, 99, 56), (190, 146, 89)

    def timber(a, b, thickness=rail):
        pg.draw.line(surface, (*low, 130), (a[0] + 1, a[1] + 2), (b[0] + 1, b[1] + 2), thickness + 2)
        pg.draw.line(surface, wood, a, b, thickness)
        pg.draw.line(surface, high, (a[0], a[1] - 1), (b[0], b[1] - 1), 1)

    horizontal = bool(bits & 10) and not bool(bits & 5)
    if gate:
        # Gate cells are passable in the physical plan. Paint the leaf swung
        # against a side post, not a closed barrier across that corridor.
        if horizontal or not bits:
            for x in (max(1, size // 8), size - max(2, size // 8)):
                timber((x, mid - separation), (x, mid + separation), rail + 1)
            timber((size // 8, mid), (size // 3, max(1, mid - separation * 2)))
        else:
            for y in (max(1, size // 8), size - max(2, size // 8)):
                timber((mid - separation, y), (mid + separation, y), rail + 1)
            timber((mid, size // 8), (max(1, mid - separation * 2), size // 3))
    else:
        for bit, end in ((1, (mid, 0)), (2, (size - 1, mid)), (4, (mid, size - 1)), (8, (0, mid))):
            if not bits & bit:
                continue
            for offset in (-separation // 2, separation // 2):
                if bit in (1, 4):
                    timber((mid + offset, mid), (end[0] + offset, end[1]))
                else:
                    timber((mid, mid + offset), (end[0], end[1] + offset))
        timber((mid, mid - separation), (mid, mid + separation), max(3, size // 9))
        pg.draw.circle(surface, low, (mid, mid), max(1, size // 20))
    if len(cache) >= 128:
        cache.clear()
    cache[key] = surface
    return surface
