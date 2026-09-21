from __future__ import annotations

from array import array
from dataclasses import dataclass

from worldseed.config import CHUNK_SIZE
from worldseed.core.coords import ChunkKey


@dataclass(slots=True)
class Chunk:
    key: ChunkKey
    terrain: array

    @classmethod
    def empty(cls, key: ChunkKey) -> "Chunk":
        return cls(key=key, terrain=array("H", [0]) * (CHUNK_SIZE * CHUNK_SIZE))

    @staticmethod
    def index(lx: int, ly: int) -> int:
        if not (0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_SIZE):
            raise IndexError((lx, ly))
        return ly * CHUNK_SIZE + lx

    def get(self, lx: int, ly: int) -> int:
        return self.terrain[self.index(lx, ly)]

    def set(self, lx: int, ly: int, terrain_index: int) -> None:
        self.terrain[self.index(lx, ly)] = terrain_index
