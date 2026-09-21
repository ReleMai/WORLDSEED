from dataclasses import dataclass
from worldseed.config import CHUNK_SIZE, REGION_CHUNKS


@dataclass(frozen=True, slots=True)
class WorldPos:
    x: int
    y: int
    z: int = 0

    def moved(self, dx: int, dy: int, dz: int = 0) -> "WorldPos":
        return WorldPos(self.x + dx, self.y + dy, self.z + dz)


@dataclass(frozen=True, slots=True)
class ChunkKey:
    x: int
    y: int
    z: int = 0


@dataclass(frozen=True, slots=True)
class RegionKey:
    x: int
    y: int
    z: int = 0


def split_world(pos: WorldPos) -> tuple[ChunkKey, int, int]:
    cx = pos.x // CHUNK_SIZE
    cy = pos.y // CHUNK_SIZE
    lx = pos.x % CHUNK_SIZE
    ly = pos.y % CHUNK_SIZE
    return ChunkKey(cx, cy, pos.z), lx, ly


def chunk_origin(key: ChunkKey) -> WorldPos:
    return WorldPos(key.x * CHUNK_SIZE, key.y * CHUNK_SIZE, key.z)


def region_for_chunk(key: ChunkKey) -> RegionKey:
    return RegionKey(key.x // REGION_CHUNKS, key.y // REGION_CHUNKS, key.z)
