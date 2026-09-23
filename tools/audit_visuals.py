from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.validate_image_assets import image_issues
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry

reg = ContentRegistry.load(DATA_DIR)
vis = VisualRegistry.load_default()
issues = vis.coverage_issues(reg)
asset_count, asset_errors = image_issues(vis.iter_asset_paths(), root=Path(__file__).resolve().parents[1])
issues.extend(asset_errors)
print(f'items={len(reg.items)} terrain={len(reg.terrains)} resources={len(reg.resources)} structures={len(reg.structures)} species={len(reg.species)} npc_variants={len(vis.manifest.get("npc_variants", []))} unique_assets={asset_count}')
if issues:
    print('\n'.join(issues)); raise SystemExit(1)
print('VISUAL AUDIT PASSED')
