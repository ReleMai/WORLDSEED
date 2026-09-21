from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry

reg = ContentRegistry.load(DATA_DIR)
vis = VisualRegistry.load_default()
issues = vis.coverage_issues(reg)
transparent_bad=[]
for p in vis.iter_asset_paths():
    try:
        with Image.open(p) as im:
            # Ground/terrain tiles are opaque by design and may be RGB. Entity,
            # resource, structure and decoration sprites are composited over
            # terrain and therefore must retain alpha.
            is_terrain = 'terrain' in {part.lower() for part in p.parts}
            if not is_terrain and im.mode != 'RGBA':
                transparent_bad.append(f'{p}: mode={im.mode} (overlay sprite requires RGBA)')
            if im.width < 24 or im.height < 24:
                transparent_bad.append(f'{p}: too small {im.size}')
    except Exception as exc:
        transparent_bad.append(f'{p}: {exc}')
issues.extend(transparent_bad)
print(f'items={len(reg.items)} terrain={len(reg.terrains)} resources={len(reg.resources)} structures={len(reg.structures)} species={len(reg.species)} npc_variants={len(vis.manifest.get("npc_variants", []))}')
if issues:
    print('\n'.join(issues)); raise SystemExit(1)
print('VISUAL AUDIT PASSED')
