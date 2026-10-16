"""GPU-first outdoor scene adapter: prepared terrain and explicit authorized actors.

Never generates chunks, mutates world state, creates hitboxes or uses a lifetime
exploration scan. The owning simulation supplies already-prepared tile/resource
views and LOS membership. The live-game producer remains responsible for every
visibility and gameplay decision; this module projects frozen visual rows.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from functools import lru_cache
from hashlib import blake2b
from math import floor,ceil
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .gl_worldspace import MAX_COMMANDS, SpriteCommand
from .worldspace import WorldCamera, WorldFoot, VisualLayer, WorldVisualInstance, project_scene, visual_sort_key, SceneVisibility, LocalCoverFade
from .worldspace_adapter import MAX_PREPARED_ACTORS, PreparedActor, prepare_worldspace_scene
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


@lru_cache(maxsize=1)
def _terrain_visuals():
    from .visuals import VisualRegistry
    return VisualRegistry.load_default()


@lru_cache(maxsize=128)
def _terrain_path(content_id: str, variant: int, visuals=None):
    """Resolve one exact namespaced material from the existing art catalog.

    The visual service is immutable during a render session. The bounded cache
    avoids filesystem checks per cell while retaining the catalog's current
    contextual water/cave assets rather than guessing their filenames.
    """
    catalog=visuals if visuals is not None else _terrain_visuals()
    path=catalog.resolve(catalog.ref('terrain',content_id),variant)
    if path is not None and path.is_file():return path
    # Compatibility for an unmapped core asset only. A mod namespace may never
    # accidentally select a similarly named core file.
    if content_id.startswith('core:'):
        kind=content_id[5:]
        if kind and kind.replace('_','').isalnum():
            candidate=ASSET_BASE/'terrain'/f'{kind}_hd_v{variant%10:02d}.png'
            if candidate.is_file():return candidate
            standard=ASSET_BASE/'terrain'/f'{kind}.png'
            if standard.is_file():return standard
    return None


def terrain_source(terrain_id:str,x:int,y:int,*,terrain_defs=None,visuals=None):
    """Resolve admitted ground art; missing art never invents forest terrain.

    New ground definitions inherit an existing material from their physical
    tags. Hard features need explicit artwork and retain an unknown marker if
    absent. This chooses presentation only and never changes the terrain ID.
    """
    # Stable coordinates, no Python randomized hash().
    variant=((x*73856093)^(y*19349663))%10
    exact=_terrain_path(terrain_id,variant,visuals)
    if exact is not None:return exact
    definition=terrain_defs.get(terrain_id) if terrain_defs is not None else None
    tags=set(getattr(definition,'tags',()))
    material=None
    if tags.intersection(('surface','underground')) and not tags.intersection(('shaft','ore','loot')):
        if 'water' in tags:
            depth='shallow' if 'shallow' in tags else 'deep'
            family='ocean' if 'saltwater' in tags else 'estuary' if 'brackish' in tags else 'lake'
            material=f'core:{family}_{depth}'
        elif 'underground' in tags:
            material='core:cave_wall' if 'rock' in tags and not getattr(definition,'passable',True) else 'core:cave_floor'
        elif 'wetland' in tags:material='core:wetland'
        elif 'rock' in tags:material='core:rock'
        elif 'sand' in tags:material='core:sand'
        else:material='core:grass'
    if material is not None:
        fallback=_terrain_path(material,variant,visuals)
        if fallback is not None:return fallback
    catalog=visuals if visuals is not None else _terrain_visuals()
    return catalog.special('unknown') or ASSET_BASE/'special'/'unknown.png'


class GpuMaterialSource:
    """Immutable source RGBA textures reused by all GPU tile instances."""
    def __init__(self,pg,max_entries=MAX_MATERIALS,*,visuals=None):
        if type(max_entries) is not int or not 12<=max_entries<=MAX_MATERIALS:
            raise ValueError('invalid asset source cache budget')
        self.pg=pg;self.limit=max_entries;self._cache=OrderedDict()
        self._visuals=visuals

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

    def actor(self,content_id:str):
        """Resolve stable actor content IDs through the existing visual catalog.

        The catalog may be injected for mod content. Unknown species use its
        existing procedural-species fallback; no gameplay entity is invented.
        """
        if content_id=='core:player':return self.player()
        if self._visuals is None:
            from .visuals import VisualRegistry
            self._visuals=VisualRegistry.load_default()
        visuals=self._visuals
        variant=int.from_bytes(blake2b(content_id.encode('utf-8'),digest_size=4).digest(),'big')
        if content_id in ('core:npc','core:npc:male','core:npc:female'):
            sex=content_id.rsplit(':',1)[1] if content_id.count(':')==2 else None
            paths=visuals.npc_paths(sex)
            path=paths[variant%len(paths)] if paths else visuals.special('unknown')
        else:
            ref=visuals.ref('species',content_id)
            path=visuals.resolve(ref,variant)
            if path is None:
                paths=visuals.procedural_species_paths()
                path=paths[variant%len(paths)] if paths else visuals.special('unknown')
        return self.asset(path) if path is not None else None


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
                      season='summer',show_player=True,fire_cells=(),
                      actors:Sequence[PreparedActor]=(), buildings=(), terrain_defs=None,
                      objects=(), show_explored_memory=True,
                      remembered_resources=(), remembered_buildings=(), remembered_objects=(),
                      sun_minute=None):
    """Build FOW-safe world visuals from one prepared viewport only."""
    if season not in ('spring','summer','autumn','winter'):
        raise ValueError('unsupported render season')
    left,top,right,bottom=cell_bounds(camera)
    if len(terrain_by)>MAX_GROUND_CELLS or len(resource_by)>1024:
        raise ValueError('GPU prepared geometry exceeds frame budget')
    if len(actors)>=MAX_PREPARED_ACTORS:
        raise ValueError('GPU prepared actors exceed frame budget')
    if any(not isinstance(actor,PreparedActor) or actor.is_viewer or
           actor.uid=='gpu-viewer' for actor in actors):
        raise ValueError('additional GPU actors must not replace the viewer')
    if len(fire_cells)>32:
        raise ValueError('too many prepared visual fires')
    ground=[]
    visible_ground=0
    from .gpu_ground import ground_material
    memory_cells=frozenset(discovered_cells)-frozenset(visible_cells)
    viewport=(0.,0.,float(camera.width_px),float(camera.height_px))
    for (x,y,z),terrain_id in terrain_by.items():
        if z!=camera.center.z or not(left<=x<right and top<=y<bottom):continue
        current=(x,y,z) in visible_cells
        if not current and (not show_explored_memory or (x,y,z) not in discovered_cells):
            continue  # Unexplored ground and blindness-mode memory stay black.
        if current:visible_ground+=1
        p=camera.to_screen(WorldFoot(x,y,z))
        # Tile geometry itself clips to its own location; shared viewport scissor
        # enables true GPU batching by art material without drawing hidden cells.
        prepared=ground_material(materials,(x,y,z),str(terrain_id),terrain_by,
            visible_cells if current else memory_cells,terrain_defs)
        tex,blend=prepared if prepared is not None else (materials.asset(terrain_source(str(terrain_id),x,y,terrain_defs=terrain_defs,visuals=getattr(materials,'_visuals',None))),None)
        # Only current pixels ease inward at a sight boundary. Never sample
        # or draw a neighboring unknown tile, and keep remembered geometry
        # frozen. A soft fade at the outgoing tile edge removes hard stair
        # stepping without leaking any undiscovered coordinates.
        edges=(tuple(0. if (x+dx,y+dy,z) in visible_cells
                     else (.36 if (x+dx,y+dy,z) in discovered_cells else .62)
                     for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)))
               if current and blend is not None else (0.,0.,0.,0.))
        ground.append(SpriteCommand(f'ground:{z}:{x}:{y}',*tex,
                       (p[0],p[1],p[0]+camera.scale,p[1]+camera.scale),
                       (viewport,), opacity=1.0 if current else .62, ground=blend,
                       remembered=not current,sight_edges=edges))
    ground.sort(key=lambda c:(c.texture_id,c.visual_id))
    viewer_actor=PreparedActor('gpu-viewer','core:player',viewer,True,is_viewer=True)
    scene=prepare_worldspace_scene(camera=camera,resource_by=resource_by,
        resource_defs=resource_defs,resource_style=resource_style,
        current_cells=visible_cells,discovered_cells=discovered_cells,
        actors=(viewer_actor,*actors),z=int(camera.center.z))
    # Harvest stages retain their resource identity and authoritative foot.
    # Stumps must not retain the mature tree's full-height visual rectangle.
    stage_by={instance.resource_id:instance.instance_id.rsplit(':',2)[-2]
              for instance in scene.instances if instance.resource_id is not None}
    instances=[]
    reproject=False
    for instance in scene.instances:
        if stage_by.get(instance.resource_id)=='stump':
            instance=replace(instance,width=min(.9,instance.width),height=.55,visual_height=.55)
            reproject=True
        instances.append(instance)
    from .gpu_objects import object_instances, object_source, resource_source
    object_by={'object:'+row.uid:row for row in objects}
    normal_objects=tuple(row for row in objects if row.kind!='roof')
    roofs=tuple(row for row in objects if row.kind=='roof')
    if normal_objects:
        instances.extend(object_instances(normal_objects))
        reproject=True
    # Project fires with the same per-cell FOW mask as actors and resources.
    # Anchor visibility alone cannot authorize the neighboring sprite pixels.
    for x,y,z in fire_cells:
        if any(type(value) is not int for value in (x,y,z)):
            raise ValueError('fire cells must be integer xyz world cells')
        if z!=camera.center.z or (x,y,z) not in visible_cells:continue
        instances.append(WorldVisualInstance(f'fire:{z}:{x}:{y}','core:campfire',
            WorldFoot(x+.5,y+.9,z),1.2,1.,1.,VisualLayer.GROUNDED))
        reproject=True
    projection=(project_scene(instances,camera,scene.visibility,viewer_id='actor:gpu-viewer')
                if reproject else scene.projection)
    if show_player:
        projection = _readable_player_cover(projection, camera)
    from .gl_worldspace import commands_from_projected
    def source(projected):
        v=projected.instance
        if v.instance_id=='actor:gpu-viewer':
            if not show_player:return None
            return materials.player()
        if v.instance_id.startswith('actor:'):
            return materials.actor(v.content_id)
        if v.instance_id.startswith('fire:'):
            return materials.asset(ASSET_BASE/'structures'/'campfire.png')
        if v.instance_id in object_by:
            return object_source(materials,object_by[v.instance_id])
        if v.content_id not in ('core:oak_tree','core:pine_tree'):
            return resource_source(materials,v)
        stage=stage_by.get(v.resource_id)
        if stage=='stump':
            return materials.asset(ASSET_BASE/'resources'/'rotten_stump_cache.png')
        if stage=='sapling':
            return materials.asset(ASSET_BASE/'settlement'/'dev43'/'logging_sapling.png')
        if stage!='mature':return None
        layer={VisualLayer.GROUNDED:'trunk',VisualLayer.GROUND_SHADOW:'shadow',
               VisualLayer.OVERHEAD:'crown'}.get(v.layer)
        if layer is None:return None
        return materials.tree('oak' if v.content_id=='core:oak_tree' else 'pine',layer,season)
    scenery=list(commands_from_projected(projection,source))
    # Give each ground shadow a physically-grounded contact ellipse rather than
    # a floating full-tile sprite. The G1 solid trunk collision remains intact.
    visual_map={v.instance.instance_id:v for v in projection.visuals}
    for index,c in enumerate(scenery):
        v=visual_map[c.visual_id]
        if v.instance.layer is VisualLayer.GROUND_SHADOW:
            cx,cy=v.screen_foot
            w=v.instance.width*camera.scale
            h=max(4,camera.scale*.56)
            scenery[index]=replace(c,bounds=(cx-w*.5,cy-h*.8,cx+w*.5,cy+h*.2))
        elif v.instance.layer is VisualLayer.OVERHEAD:
            scenery[index]=replace(c,sway_px=min(4.,camera.scale*.085))
    keys={uid:visual_sort_key(v.instance) for uid,v in visual_map.items()}
    if roofs:
        roof_projection=project_scene(object_instances(roofs),camera,
            SceneVisibility(frozenset(row.foot.cell for row in roofs)))
        scenery.extend(commands_from_projected(roof_projection,source))
        keys.update({v.instance.instance_id:visual_sort_key(v.instance) for v in roof_projection.visuals})
    if buildings:
        from .gpu_buildings import building_commands, building_sort_keys
        keys.update(building_sort_keys(buildings))
        scenery.extend(building_commands(buildings,camera,materials))
    if buildings or roofs:
        scenery.sort(key=lambda command:keys[command.visual_id])
    if show_explored_memory and (remembered_resources or remembered_buildings or remembered_objects):
        # This second projection receives detached LAST-SEEN rows only. Making
        # the memory mask its admitted view cannot query current hidden state,
        # and never allows actors, weather sources or speculative cells.
        if len(remembered_resources) > 1024 or len(remembered_objects) > 1024 or len(remembered_buildings) > 64:
            raise ValueError('GPU static memory exceeds bounded frame budget')
        frozen_buildings=[]
        for row in remembered_buildings:
            admitted=row.visible_cells & memory_cells
            if not admitted:continue
            door=row.door if row.door is not None and row.door.cell in admitted else None
            frozen_buildings.append(replace(row,visible_cells=frozenset(admitted),door=door))
        # A remembered closed shell/roof admits its exterior art, never the
        # ground beneath it or a neighboring resource stretched over that roof.
        public_memory=memory_cells & frozenset(terrain_by)
        frozen_resources={cell:(feature,None) for cell,feature in remembered_resources
                          if cell in public_memory}
        frozen_objects=tuple(row for row in remembered_objects
            if row.foot.cell in memory_cells and
            (row.kind=='roof' or row.foot.cell in public_memory))
        memory=prepare_gpu_frame(camera=camera,terrain_by={},resource_by=frozen_resources,
            resource_defs=resource_defs,resource_style=resource_style,
            visible_cells=public_memory,discovered_cells=public_memory,
            viewer=viewer,materials=materials,season=season,show_player=False,
            buildings=tuple(frozen_buildings),objects=frozen_objects,
            terrain_defs=terrain_defs,show_explored_memory=False)
        scenery[:0]=[replace(command,visual_id='memory:'+command.visual_id,
                     opacity=.62,fade_radius=0.,local_alpha=1.,sway_px=0.,remembered=True)
                     for command in memory.scenery]
    if sun_minute is not None and show_player and visible_cells:
        from .gpu_sun_shadows import sunlight_commands
        # Shadows draw above admitted ground, below people, roofs and props.
        # Their clips are exact live exterior ground; unknown and roofed
        # interiors remain unread and unaffected by this sunlight effect.
        scenery[:0]=list(sunlight_commands(camera,viewer,buildings,
                    frozenset(visible_cells)&frozenset(terrain_by),materials,sun_minute))
    if len(ground)+len(scenery)>MAX_COMMANDS:
        raise ValueError('GPU screen has more commands than the bounded renderer')
    return GPUPreparedFrame(tuple(ground),tuple(scenery),len(resource_by),visible_ground)


def _readable_player_cover(projection, camera):
    """Clear the viewer's whole body locally, even under several overlapping crowns.

    The old foot-centered 48% fade left the head behind opaque leaves and
    compounded into near opacity in dense woodland. Only already admitted
    canopy pixels are altered; trunks, rooms and hidden actors are untouched.
    """
    viewer=next((row for row in projection.visuals
                 if row.instance.instance_id=='actor:gpu-viewer' and not row.remembered_only),None)
    if viewer is None:return projection
    vx,vy=viewer.screen_foot
    center=(vx,vy-camera.scale*.76)
    player_bounds=viewer.screen_bounds
    fades=[]
    for row in projection.visuals:
        cover=row.instance
        if (cover.layer is not VisualLayer.OVERHEAD or cover.cover is None
                or cover.room_id!=viewer.instance.room_id or row.remembered_only):continue
        a,b,c,d=row.screen_bounds
        x0,y0,x1,y1=player_bounds
        if c<=x0 or a>=x1 or d<=y0 or b>=y1:continue
        # The viewer's body and this cover must overlap currently admitted
        # pixels, never merely a world-space cover polygon across a wall.
        if not any(min(c,x1,rx1)>max(a,x0,rx0) and min(d,y1,ry1)>max(b,y0,ry0)
                   for rx0,ry0,rx1,ry1 in row.clip_rects):continue
        fades.append(LocalCoverFade(cover.instance_id,viewer.instance.instance_id,
                                   center,camera.scale*1.12,.08))
        if len(fades)==8:break
    return replace(projection,cover_fades=tuple(fades))
