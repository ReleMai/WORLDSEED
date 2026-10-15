"""G1b read-only REAL resource fixture projection manifest (not a game renderer).

Run from a checkout with full WORLDSEED + data installed:
    python -m tools.worldspace_prepared_probe --scene forest --output scratch/g1b-forest.json
The existing pygame software reference captures remain the pixel baseline.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def capture(scene: str) -> dict:
    from tools.reference_scene_fixtures import build_fixture
    from worldseed.config import DATA_DIR
    from worldseed.content.registry import ContentRegistry
    from worldseed.core.coords import WorldPos
    from worldseed.presentation.visuals import VisualRegistry
    from worldseed.presentation.worldspace import VisualLayer, WorldCamera, WorldFoot
    from worldseed.presentation.worldspace_adapter import PreparedActor, prepare_worldspace_scene
    from worldseed.systems.state import pos_key

    if scene not in ('forest', 'camp'):
        raise ValueError('G1b prepared probe supports forest and camp only')
    registry = ContentRegistry.load(DATA_DIR)
    with TemporaryDirectory(prefix='worldseed-g1b-') as scratch:
        fixture = build_fixture(scene, registry, Path(scratch), width=640, height=480, zoom=28)
        try:
            sim = fixture.sim
            start = fixture.authority_fingerprint()
            px, py = sim.player_pos.x, sim.player_pos.y
            resources = {}
            for y in range(py-10, py+11):
                for x in range(px-10, px+11):
                    if pos_key(x, y, 0) not in sim.visible_tiles_set:
                        continue
                    view = sim.resources.feature_at(WorldPos(x, y, 0))
                    if view is not None and view.stage != 'depleted':
                        resources[(x, y, 0)] = (view, None)
            scene_snapshot = prepare_worldspace_scene(
                camera=WorldCamera(WorldFoot(px+0.5, py+0.5), 640, 480, 28),
                resource_by=resources, resource_defs=registry.resources,
                resource_style=VisualRegistry.load_default().resource_style,
                current_cells=sim.visible_tiles_set,
                discovered_cells=sim.discovered_tiles_set,
                visibility_key=pos_key,
                actors=(PreparedActor('player', 'core:player', WorldFoot(px+0.5, py+0.5),
                                      authorized_visible=True, is_viewer=True),),
            )
            if fixture.authority_fingerprint() != start:
                raise RuntimeError('G1b presentation modified authoritative game state')
            projected = scene_snapshot.projection
            parts = []
            for item in projected.visuals:
                v = item.instance
                parts.append(dict(id=v.instance_id, content=v.content_id, layer=v.layer.name,
                                  uid=v.resource_id, footprint=v.physical_cells,
                                  clips=len(item.clip_rects)))
            rows = dict(scene=scene, source='prepared-real-resources',
                        source_authority_sha256=start, unchanged=True,
                        camera_center=(px+0.5, py+0.5),
                        prepared_resources=len(resources),
                        count_projected=len(parts),
                        shadows=sum(v.instance.layer == VisualLayer.GROUND_SHADOW
                                    for v in projected.visuals),
                        crowns=sum(v.instance.layer == VisualLayer.OVERHEAD
                                   for v in projected.visuals),
                        fades=len(projected.cover_fades),
                        instances=parts)
            stable = json.dumps(rows, sort_keys=True, separators=(',', ':'))
            rows['sha256'] = sha256(stable.encode()).hexdigest()
            return rows
        finally:
            fixture.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', choices=('forest', 'camp'), default='forest')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    record = capture(args.scene)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'G1b {args.scene}: {record["count_projected"]} projected visuals, '
          f'{record["crowns"]} provisional crowns, '
          f'{record["fades"]} local fades; game authority unchanged')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
