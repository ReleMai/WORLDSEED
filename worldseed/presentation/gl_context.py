"""Detect the caller's current SDL OpenGL context with durable diagnostics.

No window, standalone context or shared context is created here. Explicit
glcontext detection avoids ModernGL 5.11's separate DefaultLoader path; the
reported Windows access violation does not by itself establish a root cause.
"""
from __future__ import annotations

import ctypes
from ctypes.util import find_library
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys

from .gl_worldspace import GPUBackendUnavailable


def _version(name):
    try:return metadata.version(name)
    except metadata.PackageNotFoundError:return 'unavailable'


def _pointer(value):
    return hex(value) if value else None


def _function(library,name,result,args=()):
    function=getattr(library,name)
    function.restype=result
    function.argtypes=list(args)
    return function


def native_gl_info(platform_name=None):
    """Read raw current-context handles and GL strings; never make one current.

    Windows uses opengl32/WGL. Linux checks GLX, then an already-current EGL
    context. Function lookup never creates or changes the current context.
    Calling glGetString is allowed only after a native current handle exists.
    """
    target=platform_name or sys.platform
    egl_name=None
    if target=='win32':
        name='opengl32.dll'
        library=ctypes.WinDLL(name)
        current=_function(library,'wglGetCurrentContext',ctypes.c_void_p)()
        dc=_function(library,'wglGetCurrentDC',ctypes.c_void_p)()
        api='wgl'
    elif target.startswith('linux'):
        name=find_library('GL')
        if not name:raise OSError('desktop OpenGL library was not found')
        library=ctypes.CDLL(name)
        current=_function(library,'glXGetCurrentContext',ctypes.c_void_p)()
        dc=None
        api='glx'
        if not current:
            egl_name=find_library('EGL')
            if egl_name:
                egl=ctypes.CDLL(egl_name)
                current=_function(egl,'eglGetCurrentContext',ctypes.c_void_p)()
                if current:api='egl'
    elif target=='darwin':
        name='/System/Library/Frameworks/OpenGL.framework/OpenGL'
        library=ctypes.CDLL(name)
        current=_function(library,'CGLGetCurrentContext',ctypes.c_void_p)()
        dc=None
        api='cgl'
    else:
        raise OSError('unsupported native OpenGL platform: '+target)
    result={'api':api,'library':name,'current_context':_pointer(current),
            'current_dc':_pointer(dc)}
    if api=='egl':result['egl_library']=egl_name
    if current:
        get_string=_function(library,'glGetString',ctypes.c_char_p,(ctypes.c_uint,))
        for field,constant in (('vendor',0x1F00),('renderer',0x1F01),('version',0x1F02)):
            value=get_string(constant)
            result[field]=value.decode('utf-8',errors='replace') if value else None
    return result


class _CurrentEGLFunctions:
    """ModernGL function lookup against an existing EGL context only.

    SDL offscreen may use EGL while glcontext's Linux detector expects GLX.
    This explicit loader uses discovered sonames rather than assuming unversioned
    libEGL.so development links exist. release never destroys SDL's context.
    """
    def __init__(self,egl_library,gl_library):
        self._egl=ctypes.CDLL(egl_library)
        self._gl=ctypes.CDLL(gl_library)
        self._proc=_function(self._egl,'eglGetProcAddress',ctypes.c_void_p,(ctypes.c_char_p,))

    def load_opengl_function(self,name):
        pointer=self._proc(name.encode('ascii'))
        if pointer:return pointer
        function=getattr(self._gl,name,None)
        if function is None:return 0
        return ctypes.cast(function,ctypes.c_void_p).value or 0

    def __enter__(self):return self
    def __exit__(self,*args):pass
    def release(self):pass


def inspect_sdl_context(pg, *, native_probe=None, before_native=None):
    """Collect existing SDL/native context evidence without ModernGL calls."""
    result={'platform':sys.platform,'python':sys.version.split()[0],
            'dependencies':{name:_version(name) for name in ('pygame-ce','moderngl','glcontext')}}
    attributes={}
    for name in ('GL_CONTEXT_MAJOR_VERSION','GL_CONTEXT_MINOR_VERSION',
                 'GL_CONTEXT_PROFILE_MASK','GL_CONTEXT_FLAGS','GL_DOUBLEBUFFER',
                 'GL_DEPTH_SIZE','GL_STENCIL_SIZE'):
        constant=getattr(pg,name,None)
        if constant is None:continue
        try:attributes[name]=pg.display.gl_get_attribute(constant)
        except Exception as exc:attributes[name]={'error':type(exc).__name__+': '+str(exc)}
    result['sdl_gl_attributes']=attributes
    try:
        result['sdl_initialized']=bool(pg.display.get_init())
        result['sdl_surface_present']=pg.display.get_surface() is not None
        result['sdl_video_driver']=pg.display.get_driver() if result['sdl_initialized'] else None
        result['sdl_version']=list(pg.get_sdl_version())
    except Exception as exc:
        result['sdl_error']=type(exc).__name__+': '+str(exc)
    if before_native is not None:before_native(dict(result))
    try:result['native']=(native_probe or native_gl_info)()
    except Exception as exc:result['native']={'error':type(exc).__name__+': '+str(exc)}
    return result


class _DiagnosticLog:
    def __init__(self,path):
        self.path=Path(path) if path is not None else None
        self.events=[]

    def write(self,stage,**fields):
        record={'event':'worldseed-gl-bootstrap','stage':stage,**fields}
        self.events.append(record)
        # Flush before entering native code: Python cannot catch an access
        # violation. stdout remains useful when no diagnostic path was supplied.
        print(json.dumps(record,sort_keys=True),flush=True)
        if self.path is not None:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.path.open('w',encoding='utf-8') as stream:
                json.dump({'stage':stage,'events':self.events},stream,indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())


def create_sdl_context(pg, *, require=330, diagnostics=None, loader='explicit',
                       context_loader=None, native_probe=None):
    """Wrap the already-current SDL context and return its ModernGL wrapper.

    ``loader='default'`` is reserved for a fresh diagnostic child process.
    ``context_loader``/``native_probe`` allow controlled embedding and tests;
    a supplied loader must detect the existing context, never create one.
    Evidence is flushed to stdout and optional JSON before context detection.
    """
    if type(require) is not int or require<330:
        raise ValueError('a desktop OpenGL 3.3 or newer requirement is mandatory')
    if loader not in ('explicit','default'):
        raise ValueError('context loader must be explicit or default')
    log=_DiagnosticLog(diagnostics)
    preflight=inspect_sdl_context(pg,native_probe=native_probe,
        before_native=lambda evidence:log.write('before_native_probe',evidence=evidence))
    log.write('preflight',evidence=preflight)
    native=preflight['native']
    failure=None
    version=re.match(r'^\s*(\d+)\.(\d+)',native.get('version') or '')
    version_code=int(version[1])*100+int(version[2])*10 if version else 0
    if not preflight.get('sdl_initialized') or not preflight.get('sdl_surface_present'):
        failure='an existing initialized SDL OpenGL window is required'
    elif not native.get('current_context'):
        failure='no native OpenGL context is current on this thread'
    elif version_code<require:
        failure=f'current desktop OpenGL version does not satisfy {require}: {native.get("version")!r}'
    if failure:
        log.write('rejected',error=failure)
        raise GPUBackendUnavailable(failure)
    settings={'require':require}
    if loader=='explicit':
        if native.get('api')=='egl' and context_loader is None:
            settings['context']=_CurrentEGLFunctions(native['egl_library'],native['library'])
        else:
            settings['libgl']=native['library']
    diagnostic_settings={key:value if type(value) in (str,int) else type(value).__name__
                         for key,value in settings.items()}
    log.write('before_moderngl',loader=loader,settings=diagnostic_settings)
    try:
        if context_loader is None:
            import moderngl
            context_loader=moderngl.create_context
        context=context_loader(**settings)
        log.write('ready',version_code=context.version_code,
                  driver={key:context.info.get(key,'unknown') for key in
                          ('GL_VENDOR','GL_RENDERER','GL_VERSION')})
        return context
    except Exception as exc:
        log.write('failed',error=type(exc).__name__+': '+str(exc))
        raise GPUBackendUnavailable('current SDL OpenGL context detection failed: '+str(exc)) from exc
