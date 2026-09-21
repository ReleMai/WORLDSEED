from __future__ import annotations

from hashlib import blake2b
from typing import Sequence, TypeVar

from worldseed.config import RNG_PROTOCOL_VERSION

T = TypeVar("T")
MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1


def _encode_part(value: object) -> bytes:
    if isinstance(value, bytes):
        raw = b"b" + value
    elif isinstance(value, str):
        raw = b"s" + value.encode("utf-8")
    elif isinstance(value, bool):
        raw = b"o1" if value else b"o0"
    elif isinstance(value, int):
        raw = b"i" + str(value).encode("ascii")
    elif value is None:
        raw = b"n"
    else:
        raise TypeError(f"Unsupported deterministic seed key: {type(value).__name__}")
    return len(raw).to_bytes(4, "little") + raw


def derive_seed(world_seed: bytes, namespace: str, *keys: object, version: int = RNG_PROTOCOL_VERSION) -> int:
    h = blake2b(digest_size=16, person=b"WORLDSEED-RNG-v1")
    h.update(_encode_part(version))
    h.update(_encode_part(world_seed))
    h.update(_encode_part(namespace))
    for key in keys:
        h.update(_encode_part(key))
    return int.from_bytes(h.digest(), "little")


def hash_u64(world_seed: bytes, namespace: str, *keys: object) -> int:
    h = blake2b(digest_size=8, person=b"WORLDSEED-HASHv1")
    h.update(_encode_part(world_seed))
    h.update(_encode_part(namespace))
    for key in keys:
        h.update(_encode_part(key))
    return int.from_bytes(h.digest(), "little")


class PCG32:
    """Small deterministic PCG-XSH-RR 32-bit generator."""

    __slots__ = ("state", "inc")

    def __init__(self, seed: int, stream: int = 1) -> None:
        self.state = 0
        self.inc = ((stream & MASK64) << 1 | 1) & MASK64
        self.u32()
        self.state = (self.state + (seed & MASK64)) & MASK64
        self.u32()

    def u32(self) -> int:
        oldstate = self.state
        self.state = (oldstate * 6364136223846793005 + self.inc) & MASK64
        xorshifted = (((oldstate >> 18) ^ oldstate) >> 27) & MASK32
        rot = (oldstate >> 59) & 31
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & MASK32

    def randbelow(self, stop: int) -> int:
        if stop <= 0:
            raise ValueError("stop must be positive")
        threshold = ((1 << 32) - stop) % stop
        while True:
            r = self.u32()
            if r >= threshold:
                return r % stop

    def choice(self, values: Sequence[T]) -> T:
        if not values:
            raise IndexError("Cannot choose from an empty sequence")
        return values[self.randbelow(len(values))]

    def chance(self, numerator: int, denominator: int) -> bool:
        if denominator <= 0 or numerator < 0 or numerator > denominator:
            raise ValueError("Invalid probability")
        return self.randbelow(denominator) < numerator
