from __future__ import annotations

from collections import OrderedDict
from typing import Callable

from worldseed.core.coords import ChunkKey
from worldseed.world.chunk import Chunk


class ChunkCache:
    def __init__(self, max_chunks: int, loader: Callable[[ChunkKey], Chunk]) -> None:
        if max_chunks <= 0:
            raise ValueError("max_chunks must be positive")
        self.max_chunks = max_chunks
        self.loader = loader
        self._chunks: OrderedDict[ChunkKey, Chunk] = OrderedDict()
        self._pinned: set[ChunkKey] = set()

    def get(self, key: ChunkKey) -> Chunk:
        chunk = self._chunks.get(key)
        if chunk is not None:
            self._chunks.move_to_end(key)
            return chunk
        chunk = self.loader(key)
        self._chunks[key] = chunk
        self._evict()
        return chunk

    def put(self, key: ChunkKey, chunk: Chunk) -> None:
        """Insert a prepared chunk without invoking the loader."""
        self._chunks[key] = chunk
        self._chunks.move_to_end(key)
        self._evict()

    def pin(self, key: ChunkKey) -> None:
        self._pinned.add(key)

    def unpin(self, key: ChunkKey) -> None:
        self._pinned.discard(key)
        self._evict()

    def clear_pin(self, key: ChunkKey) -> None:
        self.unpin(key)

    def _evict(self) -> None:
        if len(self._chunks) <= self.max_chunks:
            return
        for key in list(self._chunks.keys()):
            if len(self._chunks) <= self.max_chunks:
                break
            if key in self._pinned:
                continue
            self._chunks.pop(key, None)

    def __len__(self) -> int:
        return len(self._chunks)

    def peek(self, key: ChunkKey) -> Chunk | None:
        """Observational lookup: never load a chunk or change LRU order."""
        return self._chunks.get(key)
