from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry


def _manifest_asset_references(node, trail=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _manifest_asset_references(value, (*trail, str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _manifest_asset_references(value, (*trail, str(index)))
    elif isinstance(node, str) and node.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        yield node.replace("\\", "/"), ".".join(trail)


def _references_for_path(path: Path, manifest_refs):
    normalized = path.as_posix().lower()
    return sorted(
        {
            trail
            for asset_path, trail in manifest_refs
            if normalized.endswith(asset_path.lower())
        }
    )


reg = ContentRegistry.load(DATA_DIR)
vis = VisualRegistry.load_default()
issues = vis.coverage_issues(reg)
transparent_bad = []
manifest_refs = tuple(_manifest_asset_references(vis.manifest))

for p in sorted(set(vis.iter_asset_paths()), key=lambda path: str(path)):
    refs = _references_for_path(p, manifest_refs)
    ref_context = f" referenced_by={','.join(refs)}" if refs else ""
    try:
        with Image.open(p) as im:
            # Force pixel decompression here. Image.open() alone is lazy and can
            # miss corrupt IDAT/image payloads that pygame/libpng will reject later.
            im.load()
            # Ground/terrain tiles are opaque by design and may be RGB. Entity,
            # resource, structure and decoration sprites are composited over
            # terrain and therefore must retain alpha.
            is_terrain = "terrain" in {part.lower() for part in p.parts}
            if not is_terrain and im.mode != "RGBA":
                transparent_bad.append(
                    f"{p}: mode={im.mode} (overlay sprite requires RGBA){ref_context}"
                )
            if im.width < 24 or im.height < 24:
                transparent_bad.append(f"{p}: too small {im.size}{ref_context}")
    except Exception as exc:
        transparent_bad.append(
            f"{p}: decode/open failed: {type(exc).__name__}: {exc}{ref_context}"
        )

issues.extend(transparent_bad)
print(
    f"items={len(reg.items)} terrain={len(reg.terrains)} resources={len(reg.resources)} "
    f"structures={len(reg.structures)} species={len(reg.species)} "
    f"npc_variants={len(vis.manifest.get('npc_variants', []))}"
)
if issues:
    print("\n".join(issues))
    raise SystemExit(1)
print("VISUAL AUDIT PASSED")
