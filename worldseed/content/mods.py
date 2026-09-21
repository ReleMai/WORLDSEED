from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModManifest:
    id: str
    version: str
    name: str
    path: Path
    dependencies: tuple[str, ...] = ()
    load_after: tuple[str, ...] = ()
    engine_min: str = "0"


class ModError(RuntimeError):
    pass


class ModManager:
    """Deterministic manifest/dependency resolver.

    v1.0 RC1 intentionally separates dependency/load-order stability from arbitrary
    code execution. Mods are data packages; executable Python is not loaded.
    """

    def __init__(self, mods_dir: Path):
        self.mods_dir = mods_dir
        self.manifests: dict[str, ModManifest] = {}

    def discover(self) -> dict[str, ModManifest]:
        self.manifests = {}
        if not self.mods_dir.exists():
            return self.manifests
        for manifest_path in sorted(self.mods_dir.glob("*/manifest.json")):
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            mod_id = str(raw.get("id", "")).strip()
            if not mod_id or ":" in mod_id or " " in mod_id:
                raise ModError(f"Invalid mod id in {manifest_path}: {mod_id!r}")
            if mod_id in self.manifests:
                raise ModError(f"Duplicate mod id: {mod_id}")
            self.manifests[mod_id] = ModManifest(
                id=mod_id,
                version=str(raw.get("version", "0.0.0")),
                name=str(raw.get("name", mod_id)),
                path=manifest_path.parent,
                dependencies=tuple(str(x) for x in raw.get("dependencies", [])),
                load_after=tuple(str(x) for x in raw.get("load_after", [])),
                engine_min=str(raw.get("engine_min", "0")),
            )
        return dict(self.manifests)

    def resolve(self) -> list[ModManifest]:
        if not self.manifests:
            self.discover()
        for mod in self.manifests.values():
            missing = [d for d in mod.dependencies if d not in self.manifests]
            if missing:
                raise ModError(f"{mod.id} missing dependencies: {', '.join(missing)}")
        edges: dict[str, set[str]] = {mid: set() for mid in self.manifests}
        indegree = {mid: 0 for mid in self.manifests}
        for mod in self.manifests.values():
            for dep in (*mod.dependencies, *mod.load_after):
                if dep not in self.manifests:
                    if dep in mod.dependencies:
                        raise ModError(f"{mod.id} missing dependency {dep}")
                    continue
                if mod.id not in edges[dep]:
                    edges[dep].add(mod.id);indegree[mod.id]+=1
        ready = sorted(mid for mid,n in indegree.items() if n==0)
        order: list[str] = []
        while ready:
            mid=ready.pop(0);order.append(mid)
            for nxt in sorted(edges[mid]):
                indegree[nxt]-=1
                if indegree[nxt]==0:
                    ready.append(nxt);ready.sort()
        if len(order)!=len(self.manifests):
            cyclic=sorted(mid for mid,n in indegree.items() if n>0)
            raise ModError(f"Mod dependency cycle: {', '.join(cyclic)}")
        return [self.manifests[mid] for mid in order]

    def content_hash(self, order: list[ModManifest] | None = None) -> str:
        order = self.resolve() if order is None else order
        h=hashlib.blake2b(digest_size=16,person=b"WORLDSEED-MODS")
        for mod in order:
            h.update(mod.id.encode());h.update(b"\0");h.update(mod.version.encode());h.update(b"\0")
            for path in sorted(mod.path.rglob("*.json")):
                h.update(str(path.relative_to(mod.path)).encode());h.update(path.read_bytes())
        return h.hexdigest()
