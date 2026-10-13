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
