"""Transient, mutation-maintained spatial lookup for realized creatures.

The authoritative CreatureState instances live in this ordinary dict subclass.
Its 16-cell buckets only contain references; they are not persisted or a second
population authority. In-place coordinate changes must call refresh(creature)
on the same simulation mutation path. Never repair the index from rendering.
"""
from __future__ import annotations


_MISSING = object()


class CreatureSpatialMap(dict):
    CELL = 16

    def __init__(self, source=(), **kwargs):
        super().__init__()
        self._buckets = {}
        self._positions = {}
        self._ordinals = {}
        self._next_ordinal = 0
        self.update(source, **kwargs)

    @staticmethod
    def _bucket(obj):
        return (int(obj.x) // 16, int(obj.y) // 16, int(obj.z))

    def _discard(self, uid):
        previous = self._positions.pop(uid, None)
        if previous is None:
            return
        bucket = self._buckets.get(previous)
        if bucket is not None:
            bucket.pop(uid, None)
            if not bucket:
                self._buckets.pop(previous, None)

    def refresh(self, creature):
        """Apply a gameplay-authoritative relocation; never called by UI."""
        uid = creature.uid
        if dict.get(self, uid) is not creature:
            return
        current = self._bucket(creature)
        previous = self._positions.get(uid)
        if previous != current:
            self._discard(uid)
        self._buckets.setdefault(current, {})[uid] = creature
        self._positions[uid] = current

    def __setitem__(self, uid, creature):
        if creature.uid != uid:
            raise ValueError("Creature identity must match its mapping key")
        self._discard(uid)
        if uid not in self._ordinals:
            self._ordinals[uid] = self._next_ordinal
            self._next_ordinal += 1
        dict.__setitem__(self, uid, creature)
        self.refresh(creature)

    def __delitem__(self, uid):
        dict.__delitem__(self, uid)
        self._discard(uid)
        self._ordinals.pop(uid, None)

    def pop(self, uid, default=_MISSING):
        if uid not in self:
            if default is _MISSING:
                raise KeyError(uid)
            return default
        obj = dict.pop(self, uid)
        self._discard(uid)
        self._ordinals.pop(uid, None)
        return obj

    def popitem(self):
        uid, obj = dict.popitem(self)
        self._discard(uid)
        self._ordinals.pop(uid, None)
        return uid, obj

    def clear(self):
        dict.clear(self)
        self._buckets.clear()
        self._positions.clear()
        self._ordinals.clear()
        self._next_ordinal = 0

    def update(self, source=(), **kwargs):
        for uid, creature in dict(source, **kwargs).items():
            self[uid] = creature

    def __ior__(self, values):
        self.update(values)
        return self

    def setdefault(self, uid, default=None):
        if uid in self:
            return dict.__getitem__(self, uid)
        self[uid] = default
        return default

    def order_of(self, uid):
        return self._ordinals.get(uid, self._next_ordinal)

    def near_rect(self, x0, y0, x1, y1, z):
        """Index-only read, retaining original insertion order and exact bounds."""
        x0, y0, x1, y1, z = map(int, (x0, y0, x1, y1, z))
        if x1 < x0 or y1 < y0:
            return ()
        found = []
        for by in range(y0 // self.CELL, y1 // self.CELL + 1):
            for bx in range(x0 // self.CELL, x1 // self.CELL + 1):
                for uid, creature in self._buckets.get((bx, by, z), {}).items():
                    if (dict.get(self, uid) is creature
                            and creature.z == z
                            and x0 <= creature.x <= x1
                            and y0 <= creature.y <= y1):
                        found.append(creature)
        return tuple(sorted(found, key=lambda creature: self._ordinals[creature.uid]))

class SpatialObjectMap(dict):
    """Transient, mutation-maintained 32-cell index for physical objects.

    Mapping keys need not equal object UIDs. Mutation keeps buckets current;
    in-place coordinate changes must call refresh_key on the authoritative path.
    This index is derived runtime data, never serialized.
    """
    CELL = 32

    def __init__(self, source=(), **kwargs):
        super().__init__()
        self._buckets = {}
        self._positions = {}
        self._ordinals = {}
        self._next_ordinal = 0
        self.update(source, **kwargs)

    def _discard(self, key):
        previous = self._positions.pop(key, None)
        if previous is not None:
            bucket = self._buckets.get(previous)
            if bucket is not None:
                bucket.pop(key, None)
                if not bucket:
                    del self._buckets[previous]

    def refresh_key(self, key):
        """Register an in-place move after its state mutation completes."""
        obj = dict.get(self, key)
        if obj is None:
            self._discard(key)
            return
        current = (int(obj.x) // self.CELL, int(obj.y) // self.CELL, int(obj.z))
        if self._positions.get(key) != current:
            self._discard(key)
        self._buckets.setdefault(current, {})[key] = obj
        self._positions[key] = current

    def __setitem__(self, key, obj):
        self._discard(key)
        if key not in self._ordinals:
            self._ordinals[key] = self._next_ordinal
            self._next_ordinal += 1
        dict.__setitem__(self, key, obj)
        self.refresh_key(key)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._discard(key)
        self._ordinals.pop(key, None)

    def pop(self, key, default=_MISSING):
        if key not in self:
            if default is _MISSING:
                raise KeyError(key)
            return default
        obj = dict.pop(self, key)
        self._discard(key)
        self._ordinals.pop(key, None)
        return obj

    def popitem(self):
        key, obj = dict.popitem(self)
        self._discard(key)
        self._ordinals.pop(key, None)
        return key, obj

    def clear(self):
        dict.clear(self)
        self._buckets.clear()
        self._positions.clear()
        self._ordinals.clear()
        self._next_ordinal = 0

    def update(self, source=(), **kwargs):
        for key, obj in dict(source, **kwargs).items():
            self[key] = obj

    def __ior__(self, values):
        self.update(values)
        return self

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)

    def near_rect(self, left, top, right, bottom, z):
        """Read intersecting buckets only, preserving original insertion order."""
        left, top, right, bottom, z = map(int, (left, top, right, bottom, z))
        if right < left or bottom < top:
            return ()
        found = []
        for by in range(top // self.CELL, bottom // self.CELL + 1):
            for bx in range(left // self.CELL, right // self.CELL + 1):
                for key, obj in self._buckets.get((bx, by, z), {}).items():
                    if (dict.get(self, key) is obj and int(obj.z) == z
                            and left <= int(obj.x) <= right and top <= int(obj.y) <= bottom):
                        found.append((self._ordinals[key], obj))
        found.sort(key=lambda row: row[0])
        return tuple(obj for _, obj in found)
