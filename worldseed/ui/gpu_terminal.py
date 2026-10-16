"""Main-game OpenGL backend sharing the authoritative application and UI.

Only retained UI artwork is composed on a pygame Surface. World imagery is
captured from admitted live state and drawn by ModernGL; no software world
frame, second event pump, gameplay controller or save format exists here.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json
from math import ceil, sqrt
import os
from pathlib import Path
import time
from types import SimpleNamespace

from worldseed.entities.components import Vitals
from worldseed.presentation.gl_atmosphere import GLAtmospherePass
from worldseed.presentation.gl_context import create_sdl_context
from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer, GPUBackendUnavailable
from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.ui.pygame_terminal import PygameTerminal


class _Display:
    def __init__(self, owner):self.owner=owner
    def __getattr__(self, name):return getattr(self.owner._native_pg.display,name)
    def flip(self):self.owner._composite(upload=True)
    def update(self, rectangles=None):
        if rectangles is not None and (isinstance(rectangles,self.owner._native_pg.Rect) or
                (isinstance(rectangles,(tuple,list)) and len(rectangles)==4 and all(isinstance(v,(int,float)) for v in rectangles))):
            rectangles=[rectangles]
        self.owner._composite(upload=True,rectangles=rectangles)
    def get_surface(self):return self.owner.screen
    def set_mode(self, *args, **kwargs):
        raise RuntimeError('GPU window ownership forbids a second display/context')


class _Events:
    def __init__(self, owner):self.owner=owner
    def __getattr__(self,name):return getattr(self.owner._native_pg.event,name)
    def _accept(self,event):return self.owner._filter_event(event)
    def poll(self):return self._accept(self.owner._native_pg.event.poll())
    def wait(self,*args):return self._accept(self.owner._native_pg.event.wait(*args))
    def get(self,*args,**kwargs):
        return [result for event in self.owner._native_pg.event.get(*args,**kwargs)
                if (result:=self._accept(event)).type!=self.owner._native_pg.NOEVENT]


class _Pygame:
    def __init__(self, owner):self.owner=owner;self.display=_Display(owner);self.event=_Events(owner)
    def __getattr__(self,name):return getattr(self.owner._native_pg,name)


class GpuTerminal(PygameTerminal):
    """Complete main-game UI/commands with GPU world rendering in one window."""
    @staticmethod
    def available():
        import importlib.util
        return all(importlib.util.find_spec(name) is not None for name in ('pygame','moderngl','glcontext'))

    def __init__(self,width=1280,height=800):
        # The base initializes UI services only, never opens a window.
        super().__init__(width,height)
        self._native_pg=self.pg
        self.pg=_Pygame(self)
        self._gl=self._world_renderer=self._post=self._ui_gpu=None
        self._materials=None
        self._snapshot=None
        self._world_commands=()
        self._last_world=None
        self._gpu_viewport=None
        self._world_report=None
        self._focused=True
        self._focus_resume=False
        self._started=time.monotonic()
        self._gpu_presentations=0
        self._gpu_world_frames=0
        self._gpu_last_idle=0
        self._gpu_closed=False
        self._report_path=Path(os.environ.get('WORLDSEED_GPU_REPORT','logs/gpu-main-session.json'))
        self._smoke_frames=int(os.environ.get('WORLDSEED_GPU_SMOKE_FRAMES','0'))
        self._smoke_quit=False

    def enter(self):
        pg=self._native_pg
        from worldseed.presentation.gl_ui_surface import GPUUICompositor, make_ui_surface
        try:
            size=os.environ.get('WORLDSEED_GPU_SIZE')
            if size:self.width,self.height=(int(v) for v in size.lower().split('x'))
            if not 640<=self.width<=3840 or not 480<=self.height<=2160:
                raise ValueError('GPU startup size must be 640x480 through 3840x2160')
            pg.init()
            pg.display.gl_set_attribute(pg.GL_CONTEXT_MAJOR_VERSION,3)
            pg.display.gl_set_attribute(pg.GL_CONTEXT_MINOR_VERSION,3)
            pg.display.gl_set_attribute(pg.GL_CONTEXT_PROFILE_MASK,pg.GL_CONTEXT_PROFILE_CORE)
            pg.display.gl_set_attribute(pg.GL_DOUBLEBUFFER,1)
            pg.display.set_mode((self.width,self.height),pg.OPENGL|pg.DOUBLEBUF|pg.RESIZABLE)
            pg.display.set_caption('WORLDSEED | OpenGL main game')
            self._gl=create_sdl_context(pg,diagnostics=self._report_path.with_suffix('.context.json'))
            self._world_renderer=GLWorldspaceRenderer(self._gl,self.width,self.height)
            self._post=GLAtmospherePass(self._gl,self.width,self.height)
            self._ui_gpu=GPUUICompositor(self._gl,self.width,self.height)
            self._materials=GpuMaterialSource(pg,visuals=self._visuals)
            self.screen=make_ui_surface(pg,(self.width,self.height))
            self.clock=pg.time.Clock()
            pg.event.set_allowed([pg.QUIT,pg.VIDEORESIZE,getattr(pg,'WINDOWRESIZED',pg.NOEVENT),
                getattr(pg,'WINDOWFOCUSLOST',pg.NOEVENT),getattr(pg,'WINDOWFOCUSGAINED',pg.NOEVENT),
                pg.MOUSEMOTION,pg.MOUSEWHEEL,pg.MOUSEBUTTONDOWN,pg.MOUSEBUTTONUP,pg.KEYDOWN,pg.KEYUP])
            pg.key.set_repeat()
            self._rebuild_fonts()
            self._free_movement_last_ms=pg.time.get_ticks()
        except BaseException:
            self.restore()
            raise

    def _filter_event(self,event):
        pg=self._native_pg
        if event.type==getattr(pg,'WINDOWFOCUSLOST',-1):
            self._focused=False
            self._held_movement.clear();self._active_movement_key=None
            self._movement_next_repeat_ms=0
            driver=getattr(self._realtime_callback,'__self__',None)
            self._focus_resume=bool(driver is not None and not driver.paused)
            if self._focus_resume:driver.pause()
        elif event.type==getattr(pg,'WINDOWFOCUSGAINED',-2):
            self._focused=True
            self._free_movement_last_ms=pg.time.get_ticks()
            driver=getattr(self._realtime_callback,'__self__',None)
            # Restore only the focus hold. An open modal still blocks pumps
            # through its independent scoped pause until the user closes it.
            if self._focus_resume and driver is not None:driver.resume()
            self._focus_resume=False
        elif not self._focused and event.type in (pg.KEYDOWN,pg.MOUSEBUTTONDOWN,pg.MOUSEWHEEL):
            return pg.event.Event(pg.NOEVENT)
        elif event.type==pg.KEYDOWN and event.key==pg.K_F12:
            self._capture()
            return pg.event.Event(pg.NOEVENT)
        from worldseed.ui.gpu_hud import handle_hud_event
        if handle_hud_event(self,event):
            if self._last_world is not None:
                self.present_game(*self._last_world)
            return pg.event.Event(pg.NOEVENT)
        return event

    def read_key(self):
        while True:
            token=super().read_key()
            if token.startswith(('UI_WORLD_MENU:','UI_WORLD:','UI_TARGET_HOVER:')):
                try:
                    _,x,y=token.split(':')
                    cell=(int(float(x)),int(float(y)),int(self._snapshot.camera.center.z))
                except (ValueError,AttributeError):continue
                if cell not in self._snapshot.current_cells:continue
                token=token.split(':',1)[0]+f':{cell[0]}:{cell[1]}'
            elif token.startswith('UI_BUILDING_MENU:'):
                _,part,uid=token.split(':',2)
                if self._snapshot is None or not any(row.shell.uid==uid and
                    (part!='door' or row.door is not None) for row in self._snapshot.buildings):continue
            elif token.startswith(('INTERIOR_CONTEXT:','INTERIOR_PLACE:')):
                _,x,y=token.split(':')
                scene=getattr(self._snapshot,'interior_scene',None)
                if scene is None or not any(a<=int(x)<c and b<=int(y)<d
                    for tile in scene.tiles for a,b,c,d in (tile.bounds,)):continue
            elif token.startswith('INTERIOR_OBJECT:'):
                _,kind,uid=token.split(':',2)
                scene=getattr(self._snapshot,'interior_scene',None)
                if scene is None or not any(row.uid==uid and row.kind==kind for row in scene.objects):continue
                context=self._interior_context
                if context is not None:
                    ux,uy=context['camera'].to_units(*self._last_mouse)
                    hit=scene.hit_test(ux/1000.,uy/1000.)
                    if hit is None or hit.uid!=uid:continue
            return token

    def _pump_realtime(self):
        return super()._pump_realtime() if self._focused else False

    def _pump_free_movement(self,now_ms=None):
        return super()._pump_free_movement(now_ms) if self._focused else False

    def _resize(self,w,h):
        from worldseed.presentation.gl_ui_surface import make_ui_surface
        size=(max(1,min(3840,int(w))),max(1,min(2160,int(h))))
        if size==(self.width,self.height):return
        self.width,self.height=size
        self.screen=make_ui_surface(self._native_pg,size)
        self._world_renderer.resize(*size);self._post.resize(*size);self._ui_gpu.resize(*size)
        self._pointer_targets.clear();self._hover_context=None;self._interior_context=None
        self._floating_backdrop=None;self._menu_backdrop_cache.clear()
        self._snapshot=None;self._world_commands=()
        self._held_movement.clear();self._active_movement_key=None
        self._free_movement_last_ms=self.pg.time.get_ticks()

    def _composite(self,*,upload=False,rectangles=None):
        if self._gl is None or self._ui_gpu is None or self._smoke_quit:return
        elapsed=time.monotonic()-self._started
        if self._snapshot is not None:
            fx=self._snapshot.atmosphere(elapsed)
            rect=self._gpu_viewport
            fx=replace(fx,camera_pixel_x=fx.camera_pixel_x-rect.x,
                camera_pixel_y=fx.camera_pixel_y-rect.y,
                lights=tuple(replace(light,x=light.x+rect.x,y=light.y+rect.y) for light in fx.lights))
            self._world_report=self._world_renderer.draw(self._world_commands,target=self._post.scene_target,
                frame_time_seconds=elapsed,clear=(0.,0.,0.,0.))
            self._post.present(fx)
            self._gpu_world_frames+=1
        else:self._gl.screen.clear(0.,0.,0.,1.)
        if upload:self._ui_gpu.draw(self.screen,rectangles)
        else:self._ui_gpu.present_cached()
        self._native_pg.display.flip()
        self._gpu_presentations+=1
        if self._smoke_frames and self._gpu_presentations>=self._smoke_frames and not self._smoke_quit:
            self._capture()
            self._native_pg.event.post(self._native_pg.event.Event(self._native_pg.QUIT))
            self._smoke_quit=True

    def _animate_idle_effects(self,now):
        if not self._focused:return
        if self._snapshot is not None and now-self._gpu_last_idle>=50:
            self._gpu_last_idle=now
            self._composite()
        elif self._snapshot is None:
            self._animate_menu_effects(now)
            if self._smoke_frames and now-self._gpu_last_idle>=50:
                self._gpu_last_idle=now
                self._composite()

    def _animate_idle_water(self,now):return False

    def _capture(self):
        if self._gl is None:return
        path=Path(os.environ.get('WORLDSEED_GPU_SCREENSHOT','logs/gpu-main.png'))
        from tools.worldseed_gpu_gameplay import _screenshot
        _screenshot(self._native_pg,self._gl,(self.width,self.height),path)

    def _refresh_hover_only(self,*,force=False,update_display=True):
        # Hover is observational. Do not call the legacy world.tile_at tooltip
        # path or attempt to realize an unknown cell for a mouse position.
        return None

    def _hover_lines_for(self,*args,**kwargs):return []

    def present_game(self,registry,world,entities,sim,player_id,message='',cursor=None,
                     combat_overlay=None,stealth_overlay=None):
        pg=self.pg
        self._last_world=(registry,world,entities,sim,player_id,message,cursor,combat_overlay,stealth_overlay)
        self._drawing_target=cursor is not None
        self._combat_targeting=combat_overlay is not None
        ox,oy,ow,oh=self._draw_chrome('WORLDSEED // INTERIOR' if sim.interiors.player_presence() else 'WORLDSEED // LOCAL')
        width,height=self.screen.get_size()
        sidebar=min(300,max(160,width//4)) if width>=640 else 0
        footer=min(140,max(36,height//5))
        viewport=pg.Rect(max(0,ox),max(0,oy),max(1,ow-sidebar-10),max(1,oh-footer-8))
        viewport=viewport.clip(self.screen.get_rect())
        if viewport.width<1 or viewport.height<1:return
        self._gpu_viewport=viewport
        self.screen.fill((0,0,0,0),viewport)
        scale=max(28,min(56,self._tile_px),ceil(sqrt(viewport.width*viewport.height/1600)))
        camera=WorldCamera(player_foot(sim),viewport.width,viewport.height,scale)
        snapshot=capture_live_scene(sim,camera)
        from worldseed.presentation.gpu_objects import gpu_resource_style
        frame=snapshot.gpu_frame(materials=self._materials,registry=registry,
            resource_style=lambda fid:gpu_resource_style(fid,registry.resources.get(fid),self._visuals),
            show_explored_memory=True)  # Opt out only for an active blindness effect.
        self._snapshot=snapshot
        def shift(rect):return(rect[0]+viewport.x,rect[1]+viewport.y,rect[2]+viewport.x,rect[3]+viewport.y)
        self._world_commands=tuple(replace(command,bounds=shift(command.bounds),
            clip_rects=tuple(shift(rect) for rect in command.clip_rects),
            fade_center=(command.fade_center[0]+viewport.x,command.fade_center[1]+viewport.y))
            for command in frame.commands)
        self._set_pointer_context(snapshot,registry,world,sim,viewport,camera)
        if sidebar:
            side=pg.Rect(viewport.right+8,oy,max(1,width-viewport.right-26),max(1,oh))
            pg.draw.rect(self.screen,self._theme['panel2'],side)
            vit=entities.try_get(player_id,Vitals) or Vitals()
            from worldseed.ui.gpu_hud import draw_hud
            draw_hud(self,side,sim,vit)
        foot=pg.Rect(viewport.x,viewport.bottom+6,viewport.width,max(1,min(footer,height-viewport.bottom-8)))
        self._draw_footer(foot,message or (sim.log[-1].message if sim.log else 'The world continues around you.'),sim)
        self._draw_target_overlays(snapshot,viewport,camera,cursor,combat_overlay,stealth_overlay)
        from worldseed.ui.gpu_hud import draw_help_popup
        draw_help_popup(self)
        self._composite(upload=True)
        self.clock.tick(120)

    def _set_pointer_context(self,snapshot,registry,world,sim,viewport,camera):
        # Legacy input uses an exact cell origin and cell size; derive both
        # from this same fractional camera rather than a second grid transform.
        origin=camera.to_screen(WorldFoot(0,0,camera.center.z))
        self._hover_context={'used':viewport.copy(),'grid_x':round(origin[0])+viewport.x,
            'grid_y':round(origin[1])+viewport.y,'left':0,'top':0,'tile_px':camera.scale,
            'z':sim.player_pos.z,'known':sim.discovered_tiles_set,'visible':sim.visible_tiles_set,
            'registry':registry,'world':world,'sim':sim,'shell_hit_regions':[]}
        from worldseed.presentation.gpu_buildings import building_hit_regions
        self._hover_context['shell_hit_regions']=building_hit_regions(
            snapshot.buildings,self._world_commands,self.pg,viewport)
        self._interior_context=None
        scene=getattr(snapshot,'interior_scene',None)
        if scene is not None:
            self._set_interior_context(scene,sim,registry,viewport,camera)

    def _set_interior_context(self,scene,sim,registry,viewport,camera):
        # Filled by the GPU interior adapter protocol; the simulation's existing
        # interior commands own all transitions, furniture and collision.
        from worldseed.ui.interior_view import InteriorCamera
        plan=sim.interiors.current_plan()
        origin=camera.to_world(0,0,ground_z=camera.center.z)
        transform=InteriorCamera(origin.x*1000,origin.y*1000,camera.scale/1000,viewport.x,viewport.y)
        self._interior_context={'plan':plan,'sim':sim,'registry':registry,'used':viewport,
            'camera':transform,'object_regions':[], 'snapshot':self.screen.subsurface(viewport).copy(),'hover_uid':None}
        self._hover_context=None
        # Populated only from admitted detached rows; no hidden furniture scan.
        for row in getattr(scene,'objects',()):
            bounds=row.bounds
            x0,y0=camera.to_screen(WorldFoot(bounds[0],bounds[1],camera.center.z))
            x1,y1=camera.to_screen(WorldFoot(bounds[2],bounds[3],camera.center.z))
            rect=self.pg.Rect(round(x0)+viewport.x,round(y0)+viewport.y,max(1,round(x1-x0)),max(1,round(y1-y0))).clip(viewport)
            if not rect.width or not rect.height:continue
            kind=getattr(row,'kind','furniture')
            source=row if kind in ('furniture','stairs') else None
            if source is not None:
                self._interior_context['object_regions'].append({'uid':row.uid,'kind':kind,'rect':rect,'base':rect,'object':source})

    def _draw_target_overlays(self,snapshot,viewport,camera,cursor,combat,stealth):
        if cursor is not None and (cursor.x,cursor.y,cursor.z) in snapshot.current_cells:
            x,y=camera.to_screen(WorldFoot(cursor.x,cursor.y,cursor.z))
            self.pg.draw.rect(self.screen,self._theme['accent'],(round(x)+viewport.x,round(y)+viewport.y,round(camera.scale),round(camera.scale)),2)
        # Existing targeting commands remain authoritative. Only draw admitted
        # target cells; overlays cannot expand current sight.
        for overlay,color in ((combat,(215,92,68)),(stealth,(112,150,160))):
            if not isinstance(overlay,dict):continue
            for row in tuple(overlay.get('cells',()))[:1024]:
                if not isinstance(row,dict):continue
                cell=(row.get('x'),row.get('y'),row.get('z',int(camera.center.z)))
                if cell not in snapshot.current_cells:continue
                x,y=camera.to_screen(WorldFoot(*cell))
                self.pg.draw.rect(self.screen,color,(round(x)+viewport.x,round(y)+viewport.y,round(camera.scale),round(camera.scale)),1)

    def restore(self):
        if self._gpu_closed:return
        from worldseed.ui.gpu_hud import close_help_popup
        close_help_popup(self)
        self._gpu_closed=True
        try:
            if self._gl is not None:
                self._report_path.parent.mkdir(parents=True,exist_ok=True)
                self._report_path.write_text(json.dumps({'status':'gpu-main-session',
                    'backend':'gpu-main','source':'main-game','saved_world_support':True,
                    'render_frames':self._gpu_presentations,'world_frames':self._gpu_world_frames,
                    'native_hardware_accepted':False,
                    'gpu':{key:self._gl.info.get(key,'unknown') for key in ('GL_VENDOR','GL_RENDERER','GL_VERSION')},
                    'last_frame':asdict(self._world_report) if self._world_report else {},
                    'note':'Shared main-game commands/UI/saves. CPU submission is not hardware performance acceptance.'},indent=2)+'\n',encoding='utf-8')
        finally:
            for renderer in (self._ui_gpu,self._post,self._world_renderer):
                if renderer is not None:renderer.close()
            if self._gl is not None:self._gl.release()
            self._native_pg.quit()
