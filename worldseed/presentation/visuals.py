from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from worldseed.content.registry import ContentRegistry


@dataclass(frozen=True, slots=True)
class VisualRef:
    visual_id: str
    kind: str
    paths: tuple[str, ...]
    fallback_glyph: str = "?"


class VisualRegistry:
    """Data-driven map from simulation/content IDs to presentation assets.

    No simulation system imports this module.  Missing assets degrade to glyphs;
    release audits can require 100% authored/generated coverage independently.
    """

    def __init__(self, manifest: dict, base_dir: Path) -> None:
        self.manifest = manifest
        self.base_dir = base_dir

    @classmethod
    def load_default(cls) -> "VisualRegistry":
        base = Path(__file__).resolve().parents[1]
        path = base / "assets" / "visuals.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        # Item visuals are derived from data/items.json so adding, removing, or
        # renaming an icon does not require maintaining a second 100+ entry map.
        item_path = base / "data" / "items.json"
        if item_path.exists():
            item_visuals: dict[str, str] = {}
            for raw in json.loads(item_path.read_text(encoding="utf-8")):
                content_id = str(raw["id"])
                asset = str(raw.get("asset") or content_id.split(":", 1)[-1])
                item_visuals[content_id] = f"assets/sprites/items/{asset}.png"
            manifest["items"] = item_visuals
        return cls(manifest, base)

    def _paths(self, kind: str, content_id: str) -> tuple[str, ...]:
        raw = self.manifest.get(kind, {}).get(content_id)
        if isinstance(raw, str):
            return (raw,)
        if isinstance(raw, list):
            return tuple(str(x) for x in raw)
        return ()

    def ref(self, kind: str, content_id: str, fallback_glyph: str = "?") -> VisualRef:
        return VisualRef(content_id, kind, self._paths(kind, content_id), fallback_glyph)

    def special(self, name: str) -> Path | None:
        raw = self.manifest.get("special", {}).get(name)
        return self.base_dir / raw if raw else None

    def resource_style(self, content_id: str) -> dict:
        return self.manifest.get('resource_rendering', {}).get(content_id, {})

    def resource_atlas_path(self, content_id: str) -> Path | None:
        """Return an optional presentation atlas for one resource type.

        Resource atlases are presentation-only. World generation still decides
        which resource occupies a cell; the renderer deterministically selects
        one visual frame for that generated cell.
        """
        raw = self.resource_style(content_id).get('atlas')
        return self.base_dir / str(raw) if raw else None

    def player_paths(self, sex: str = 'male') -> tuple[Path, ...]:
        groups = self.manifest.get('player_variants', {})
        raw = groups.get((sex or 'male').lower()) or groups.get('male') or []
        return tuple(self.base_dir / p for p in raw)

    def player_path(self, sex: str = 'male', index: int = 0) -> Path | None:
        paths = self.player_paths(sex)
        if paths:
            return paths[index % len(paths)]
        return self.special('player')

    def npc_paths(self, sex: str | None = None) -> tuple[Path, ...]:
        paths=self.manifest.get("npc_variants", [])
        if sex in ('male','female'):
            labels=self.manifest.get('npc_variant_sexes', [])
            if len(labels)==len(paths):
                return tuple(self.base_dir / p for p,label in zip(paths,labels) if label==sex)
        return tuple(self.base_dir / p for p in paths)

    def procedural_species_paths(self) -> tuple[Path, ...]:
        return tuple(self.base_dir / p for p in self.manifest.get('procedural_species', []))

    def resolve(self, ref: VisualRef, variant: int = 0) -> Path | None:
        if not ref.paths:
            return None
        return self.base_dir / ref.paths[variant % len(ref.paths)]

    def coverage_issues(self, registry: ContentRegistry) -> list[str]:
        issues: list[str] = []
        tables = {
            "items": registry.items,
            "terrain": registry.terrains,
            "resources": registry.resources,
            "structures": registry.structures,
            "species": registry.species,
            "crops": registry.crops,
        }
        for kind, table in tables.items():
            for cid in sorted(table):
                paths = self._paths(kind, cid)
                if not paths:
                    issues.append(f"missing {kind} visual: {cid}")
                    continue
                for raw in paths:
                    p = self.base_dir / raw
                    if not p.exists():
                        issues.append(f"missing visual file: {raw} ({cid})")
        player_groups = self.manifest.get('player_variants', {})
        for sex in ('male', 'female'):
            if len(player_groups.get(sex, [])) < 10:
                issues.append(f'fewer than 10 {sex} player variants')
            for raw in player_groups.get(sex, []):
                if not (self.base_dir / raw).exists():
                    issues.append(f'missing {sex} player visual file: {raw}')
        if len(self.manifest.get("npc_variants", [])) < 12:
            issues.append("fewer than 12 NPC variants")
        labels=self.manifest.get('npc_variant_sexes', [])
        if labels and (len(labels)!=len(self.manifest.get('npc_variants', [])) or
                       set(labels)-{'male','female'} or not {'male','female'}<=set(labels)):
            issues.append('NPC sex labels must match every variant and include both sexes')
        for raw in self.manifest.get("npc_variants", []):
            if not (self.base_dir / raw).exists():
                issues.append(f"missing NPC visual file: {raw}")
        if len(self.manifest.get("procedural_species", [])) < 4:
            issues.append("fewer than 4 procedural-species fallback variants")
        for raw in self.manifest.get("procedural_species", []):
            if not (self.base_dir / raw).exists():
                issues.append(f"missing procedural species visual file: {raw}")
        for cid, style in self.manifest.get('resource_rendering', {}).items():
            raw = style.get('atlas') if isinstance(style, dict) else None
            if raw and not (self.base_dir / str(raw)).exists():
                issues.append(f"missing resource atlas: {raw} ({cid})")
        return issues

    def iter_asset_paths(self) -> Iterable[Path]:
        for kind in ("items", "terrain", "resources", "structures", "species", "crops"):
            for raw in self.manifest.get(kind, {}).values():
                vals = [raw] if isinstance(raw, str) else raw
                for p in vals or []:
                    yield self.base_dir / p
        for sex in ('male', 'female'):
            for p in self.manifest.get('player_variants', {}).get(sex, []):
                yield self.base_dir / p
        for p in self.manifest.get("npc_variants", []):
            yield self.base_dir / p
        for p in self.manifest.get("procedural_species", []):
            yield self.base_dir / p
        for style in self.manifest.get('resource_rendering', {}).values():
            raw = style.get('atlas') if isinstance(style, dict) else None
            if raw:
                yield self.base_dir / str(raw)
