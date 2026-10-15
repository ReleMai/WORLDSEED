"""GPU-first outdoor scene adapter: prepared terrain and explicit authorized actors.

Never generates chunks, mutates world state, creates hitboxes or uses a lifetime
exploration scan. The owning simulation supplies already-prepared tile/resource
views and LOS membership. This is a Windows GPU *visual playtest* bridge, not
an input/gameplay ownership migration.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from functools import lru_cache
from math import floor,ceil
from pathlib import Path
from typing import Callable, Mapping

from .gl_worldspace import MAX_COMMANDS, SpriteCommand
from .worldspace import WorldCamera, WorldFoot, VisualLayer
from .worldspace_adapter import PreparedActor, prepare_worldspace_scene
from .tree_art import layer_png

MAX_GROUND_CELLS=8192
MAX_MATERIALS=64
ASSET_BASE=Path(__file__).resolve().parents[1]/'assets'/'sprites'


def cell_bounds(camera:WorldCamera):
    corner0=camera.to_world(0,0,ground_z=camera.center.z)
    corner1=camera.to_world(camera.width_px,camera.height_px,ground_z=camera.center.z)
    left,top=floor(corner0.x),floor(corner0.y)
    right,bottom=ceil(corner1.x),ceil(corner1.y)
    if not 0 < (right-left)*(bottom-top) <= MAX_GROUND_CELLS:
        raise ValueError('GPU visual viewport exceeds bounded world-cell budget')
    return left,top,right,bottom


@lru_cache(maxsize=128)
def _terrain_path(kind: str, variant: int):
    candidate=ASSET_BASE/'terrain'/f'{kind}_hd_v{variant:02d}.png'
    if candidate.is_file():return candidate
    standard=ASSET_BASE/'terrain'/f'{kind}.png'
    if standard.is_file():return standard
    return ASSET_BASE/'terrain'/'forest_hd_v00.png'


def terrain_source(terrain_id:str,x:int,y:int):
    """Use authored terrain variants with one file-stat per unique material."""
    kind=terrain_id.removeprefix('core:')
    if not kind.replace('_','').isalnum():kind='forest'
    # Stable coordinates, no Python randomized hash().
    variant=((x*73856093)^(y*19349663))%10
    return _terrain_path(kind, variant)


class GpuMaterialSource:
    """Immutable source RGBA textures reused by all GPU tile instances."""
    def __init__(self,pg,max_entries=MAX_MATERIALS):
        if type(max_entries) is not int or not 12<=max_entries<=MAX_MATERIALS:
            raise ValueError('invalid asset source cache budget')
        self.pg=pg;self.limit=max_entries;self._cache=OrderedDict()

    def _read(self,key,load):
        old=self._cache.get(key)
        if old is not None:
            self._cache.move_to_end(key);return old
        row=load()
        while len(self._cache)>=self.limit:self._cache.popitem(last=False)
        self._cache[key]=row
        return row

    def asset(self,path:Path):
        name=str(path)
        def loader():
            surf=self.pg.image.load(name)
            return (f'asset:{name}',1,self.pg.image.tobytes(surf,'RGBA'),*surf.get_size())
        return self._read(('file',name),loader)

    def tree(self,species,layer,season):
        from io import BytesIO
        s=season if layer=='crown' else 'summer'
        def loader():
            surf=self.pg.image.load(BytesIO(layer_png(species,layer,s)),f'{species}_{layer}.png')
            return (f'worldspace:{species}:{layer}:{s}',1,self.pg.image.tobytes(surf,'RGBA'),*surf.get_size())
        return self._read(('tree',species,layer,s),loader)

    def player(self):
        return self.asset(ASSET_BASE/'characters'/'dev20_00.png')


@dataclass(frozen=True,slots=True)
class GPUPreparedFrame:
    ground: tuple[SpriteCommand,...]
    scenery: tuple[SpriteCommand,...]
    resources: int
    visible_ground_cells: int

    @property
    def commands(self):
        return (*self.ground,*self.scenery)


def prepare_gpu_frame(*,camera:WorldCamera, terrain_by:Mapping,
                      resource_by:Mapping,resource_defs:Mapping,
                      resource_style:Callable,visible_cells,discovered_cells,
                      viewer:WorldFoot,materials:GpuMaterialSource,
                      season='summer',show_player=True,fire_cells=()):
    """Build FOW-safe world visuals from one prepared viewport only."""
    if season not in ('spring','summer','autumn','winter'):
        raise ValueError('unsupported render season')
    left,top,right,bottom=cell_bounds(camera)
    if len(terrain_by)>MAX_GROUND_CELLS or len(resource_by)>1024:
        raise ValueError('GPU prepared geometry exceeds frame budget')
    ground=[]
    viewport=(0.,0.,float(camera.width_px),float(camera.height_px))
    for (x,y,z),terrain_id in terrain_by.items():
        if z!=camera.center.z or not(left<=x<right and top<=y<bottom):continue
        if (x,y,z) not in visible_cells:continue
        p=camera.to_screen(WorldFoot(x,y,z))
        # Tile geometry itself clips to its own location; shared viewport scissor
        # enables true GPU batching by art material without drawing hidden cells.
        tex=materials.asset(terrain_source(str(terrain_id),x,y))
        ground.append(SpriteCommand(f'ground:{z}:{x}:{y}',*tex,
                       (p[0],p[1],p[0]+camera.scale,p[1]+camera.scale),
                       (viewport,)))
    ground.sort(key=lambda c:(c.texture_id,c.visual_id))
    viewer_actor=PreparedActor('gpu-viewer','core:player',viewer,True,is_viewer=True)
    scene=prepare_worldspace_scene(camera=camera,resource_by=resource_by,
        resource_defs=resource_defs,resource_style=resource_style,
        current_cells=visible_cells,discovered_cells=discovered_cells,
        actors=(viewer_actor,),z=int(camera.center.z))
    from .gl_worldspace import commands_from_projected
    def source(projected):
        v=projected.instance
        if v.instance_id=='actor:gpu-viewer':
            if not show_player:return None
            return materials.player()
        if v.content_id not in ('core:oak_tree','core:pine_tree'):
            return None
        layer={VisualLayer.GROUNDED:'trunk',VisualLayer.GROUND_SHADOW:'shadow',
               VisualLayer.OVERHEAD:'crown'}.get(v.layer)
        if layer is None:return None
        return materials.tree('oak' if v.content_id=='core:oak_tree' else 'pine',layer,season)
    scenery=list(commands_from_projected(scene.projection,source))
    # Give each ground shadow a physically-grounded contact ellipse rather than
    # a floating full-tile sprite. The G1 solid trunk collision remains intact.
    visual_map={v.instance.instance_id:v for v in scene.projection.visuals}
    for index,c in enumerate(scenery):
        v=visual_map[c.visual_id]
        if v.instance.layer is VisualLayer.GROUND_SHADOW:
            cx,cy=v.screen_foot
            w=v.instance.width*camera.scale
            h=max(4,camera.scale*.56)
            scenery[index]=replace(c,bounds=(cx-w*.5,cy-h*.8,cx+w*.5,cy+h*.2))
        elif v.instance.layer is VisualLayer.OVERHEAD:
            scenery[index]=replace(c,sway_px=min(4.,camera.scale*.085))
    # Visible authored campfire sprites share their actual prepared fire cells.
    # The source simulation still controls fuel, collision and interaction.
    if len(fire_cells)>32:
        raise ValueError('too many prepared visual fires')
    fire_commands=[]
    for (x,y,z) in fire_cells:
        if (x,y,z) not in visible_cells:continue
        p=camera.to_screen(WorldFoot(x+.5,y+.9,z))
        w,h=camera.scale*1.2,camera.scale*1.0
        source=materials.asset(ASSET_BASE/'structures'/'campfire.png')
        fire_commands.append(SpriteCommand(f'fire:{z}:{x}:{y}',*source,
            (p[0]-w*.5,p[1]-h,p[0]+w*.5,p[1]),
            ((p[0]-camera.scale*.5,p[1]-camera.scale*.9,
              p[0]+camera.scale*.5,p[1]+camera.scale*.1),)))
    # Fire remains behind the canopy pass, never painted through its leaves.
    if fire_commands:
        first_crown=next((i for i,row in enumerate(scenery)
            if visual_map[row.visual_id].instance.layer is VisualLayer.OVERHEAD),len(scenery))
        scenery[first_crown:first_crown]=fire_commands
    if len(ground)+len(scenery)>MAX_COMMANDS:
        raise ValueError('GPU screen has more commands than the bounded renderer')
    return GPUPreparedFrame(tuple(ground),tuple(scenery),len(resource_by),len(ground))
