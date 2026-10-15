"""G0/G1a deterministic SVG/JSON synthetic canopy + actor viewport probe.

No pygame, GPU, save loading, resource generation or asset catalog dependencies.
The diagram illustrates G1a scene contracts, not approved final game art.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from worldseed.presentation.worldspace import (
    CoverRegion, SceneVisibility, VisualLayer, WorldCamera, WorldFoot,
    WorldVisualInstance, project_scene,
)


def build_demo(width: int = 640, height: int = 480, zoom: float = 1.0):
    if not 160 <= width <= 1920 or not 160 <= height <= 1080 or not 0.25 <= zoom <= 4:
        raise ValueError('probe width/height/zoom outside bounded development range')
    crown = CoverRegion(((0.5, 0.5), (4.5, 0.5), (4.5, 4.5), (0.5, 4.5)))
    def instance(uid, foot, width_cells, height_cells, layer, *, physical=(),
                 cover=None, parent=None, authorized=True):
        return WorldVisualInstance(uid, 'core:' + uid.split(':')[0], foot, width_cells,
                                   height_cells, height_cells, layer,
                                   physical_cells=physical, cover=cover, parent_id=parent,
                                   resource_id='oak:legacy-resource-0001' if uid.startswith('oak:') else None,
                                   authorized_visible=authorized)
    instances = (
        instance('oak:ground_shadow', WorldFoot(2.5, 2.9), 3.5, 1.0,
                 VisualLayer.GROUND_SHADOW, parent='oak:trunk'),
        instance('oak:trunk', WorldFoot(2.5, 2.9), 1.0, 2.2,
                 VisualLayer.GROUNDED, physical=((2, 2, 0),)),
        instance('player:main', WorldFoot(3.4, 2.25), 0.75, 1.45, VisualLayer.UPRIGHT),
        instance('npc:visible', WorldFoot(2.1, 3.8), 0.75, 1.45, VisualLayer.UPRIGHT),
        instance('npc:hidden', WorldFoot(1.8, 1.8), 0.75, 1.45,
                 VisualLayer.UPRIGHT, authorized=False),
        instance('oak:crown', WorldFoot(2.5, 2.9), 4.0, 3.8,
                 VisualLayer.OVERHEAD, cover=crown, parent='oak:trunk'),
    )
    current = frozenset((x, y, 0) for x in range(-7, 12) for y in range(-7, 12))
    camera = WorldCamera(WorldFoot(2.5, 2.5), width, height, 32, zoom=zoom)
    scene = project_scene(instances, camera, SceneVisibility(current), viewer_id='player:main')
    return camera, scene


def probe_record(camera, scene) -> dict:
    record = {'kind': 'synthetic-g0-g1a-contract', 'camera': {
        'center': [camera.center.x, camera.center.y, camera.center.z],
        'size': [camera.width_px, camera.height_px], 'zoom': camera.zoom},
        'visuals': [{'id': p.instance.instance_id, 'layer': p.instance.layer.name,
                     'foot': list(p.screen_foot),
                     'bounds': list(p.screen_bounds), 'clip_cells': len(p.clip_rects),
                     'resource_id': p.instance.resource_id}
                    for p in scene.visuals],
        'fades': [{'id': f.cover_instance_id, 'for': f.viewer_instance_id,
                   'alpha': f.local_alpha, 'center': list(f.screen_center),
                   'radius_px': f.radius_px} for f in scene.cover_fades]}
    payload = json.dumps(record, sort_keys=True, separators=(',', ':')).encode()
    record['sha256'] = hashlib.sha256(payload).hexdigest()
    return record


def probe_svg(camera, scene) -> str:
    """Presentation-only diagram: clips art to current visibility cells."""
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{camera.width_px}" height="{camera.height_px}" viewBox="0 0 {camera.width_px} {camera.height_px}">',
             '<defs>']
    for j, part in enumerate(scene.visuals):
        lines.append(f'<clipPath id="clip{j}">')
        for l, t, r, b in part.clip_rects:
            lines.append(f'<rect x="{l:.2f}" y="{t:.2f}" width="{r-l:.2f}" height="{b-t:.2f}"/>')
        lines.append('</clipPath>')
    for j, fade in enumerate(scene.cover_fades):
        x, y = fade.screen_center
        shade = int(round(fade.local_alpha * 255))
        gray = f"#{shade:02x}{shade:02x}{shade:02x}"
        lines.append(f'<radialGradient id="fade{j}" cx="{x:.2f}" cy="{y:.2f}" r="{fade.radius_px:.2f}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{gray}"/><stop offset="0.75" stop-color="{gray}"/><stop offset="1" stop-color="white"/></radialGradient>')
        lines.append(f'<mask id="fademask{j}" maskUnits="userSpaceOnUse" x="0" y="0" width="{camera.width_px}" height="{camera.height_px}"><rect width="100%" height="100%" fill="url(#fade{j})"/></mask>')
    lines.extend(['</defs>', '<rect width="100%" height="100%" fill="#d9ddc0"/>'])
    for x in range(-6, 12):
        for y in range(-6, 12):
            sx, sy = camera.to_screen(WorldFoot(x, y))
            if -camera.scale < sx < camera.width_px and -camera.scale < sy < camera.height_px:
                lines.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{camera.scale:.1f}" height="{camera.scale:.1f}" fill="none" stroke="#a1ac91" stroke-width="0.5"/>')
    for i, item in enumerate(scene.visuals):
        uid = item.instance.instance_id
        x, y, r, b = item.screen_bounds
        w, h = r-x, b-y
        lines.append(f'<g clip-path="url(#clip{i})">')
        if uid == 'oak:ground_shadow':
            lines.append(f'<ellipse cx="{(x+r)/2:.1f}" cy="{(y+b)/2:.1f}" rx="{w/2:.1f}" ry="{h/2:.1f}" fill="#394a34" opacity="0.28"/>')
        elif uid == 'oak:trunk':
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="#795436" stroke="#4b3224" stroke-width="3"/>')
        elif uid.startswith(('player:', 'npc:')):
            color = '#d2a14f' if uid.startswith('player:') else '#557ca8'
            fx, fy = item.screen_foot
            lines.append(f'<ellipse cx="{fx:.1f}" cy="{fy:.1f}" rx="8" ry="4" fill="#333" opacity="0.25"/>')
            lines.append(f'<rect x="{x:.1f}" y="{y+9:.1f}" width="{w:.1f}" height="{max(h-9,1):.1f}" rx="11" fill="{color}" stroke="#374449" stroke-width="2"/>')
            lines.append(f'<circle cx="{(x+r)/2:.1f}" cy="{y+10:.1f}" r="9" fill="#dcb48b"/>')
        elif uid == 'oak:crown':
            mask = ' mask="url(#fademask0)"' if scene.cover_fades else ''
            lines.append(f'<ellipse cx="{(x+r)/2:.1f}" cy="{(y+b)/2:.1f}" rx="{w/2:.1f}" ry="{h/2:.1f}" fill="#47783f" opacity="0.82"{mask}/>')
        lines.append('</g>')
    lines.append(f'<text x="16" y="27" font-family="sans-serif" font-size="14" fill="#263824">{escape("WORLDSEED G0/G1a — synthetic viewport (not approved game art)")}</text>')
    lines.append('</svg>')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--zoom', type=float, default=1.0)
    parser.add_argument('--output-prefix', type=Path, default=Path('scratch/worldspace-g01'))
    args = parser.parse_args(argv)
    camera, scene = build_demo(args.width, args.height, args.zoom)
    record = probe_record(camera, scene)
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    args.output_prefix.with_suffix('.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    args.output_prefix.with_suffix('.svg').write_text(probe_svg(camera, scene), encoding='utf-8')
    print(json.dumps({'sha256': record['sha256'], 'visual_count': len(scene.visuals),
                      'local_fades': len(scene.cover_fades), 'output': str(args.output_prefix)}))


if __name__ == '__main__':
    main()
