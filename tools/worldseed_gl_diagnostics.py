"""Isolated comparison of default versus explicit current-SDL GL detection.

Every mode runs in its own child process: a native access violation cannot erase
the other mode's diagnostics. Each child owns one SDL window/current context;
neither mode asks ModernGL for a standalone or shared context. Reports diagnose
startup only and establish no native GPU performance or release acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def _write(path,record):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as stream:
        json.dump(record,stream,indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    summary=dict(record)
    if 'processes' in summary:
        summary['processes']=[{key:row[key] for key in ('mode','exit_code','report','context_report')}
                              for row in summary['processes']]
    print(json.dumps(summary,sort_keys=True),flush=True)


def run_child(mode,report):
    """One minimal SDL bootstrap, executed only by an isolated child."""
    from worldseed.presentation.gl_context import create_sdl_context
    context=None
    pg=None
    result={'mode':mode,'status':'before_sdl_window','native_gpu_accepted':False}
    _write(report,result)
    try:
        import pygame as pg
        pg.init()
        pg.display.gl_set_attribute(pg.GL_CONTEXT_MAJOR_VERSION,3)
        pg.display.gl_set_attribute(pg.GL_CONTEXT_MINOR_VERSION,3)
        pg.display.gl_set_attribute(pg.GL_CONTEXT_PROFILE_MASK,pg.GL_CONTEXT_PROFILE_CORE)
        pg.display.gl_set_attribute(pg.GL_DOUBLEBUFFER,1)
        pg.display.set_mode((640,480),pg.DOUBLEBUF|pg.OPENGL)
        context=create_sdl_context(pg,loader=mode,
            diagnostics=Path(report).with_suffix('.context.json'))
        result.update(status='context_detected',version_code=context.version_code,
            driver={key:context.info.get(key,'unknown') for key in
                    ('GL_VENDOR','GL_RENDERER','GL_VERSION')})
        return_code=0
    except Exception as exc:
        result.update(status='unavailable',error=type(exc).__name__+': '+str(exc))
        return_code=1
    finally:
        if context is not None:context.release()
        if pg is not None:pg.quit()
    _write(report,result)
    return return_code


def run_isolated(*,mode='compare',report='scratch/gl-context-diagnostics.json',timeout=30):
    """Run bounded fresh processes and retain stdout/stderr/exit evidence."""
    if mode not in ('compare','default','explicit'):
        raise ValueError('diagnostic mode must be compare, default or explicit')
    if type(timeout) is not int or not 1<=timeout<=60:
        raise ValueError('diagnostic timeout must be 1..60 seconds per process')
    report=Path(report)
    modes=('default','explicit') if mode=='compare' else (mode,)
    result={'status':'diagnosing-current-sdl-context','native_gpu_accepted':False,
            'limitations':'startup diagnosis only; no screenshots, performance or release acceptance',
            'processes':[]}
    _write(report,result)
    for selected in modes:
        child_report=report.with_name(report.stem+'-'+selected+'.json')
        command=[sys.executable,'-X','faulthandler','-u','-m',
                 'tools.worldseed_gl_diagnostics','--mode',selected,
                 '--report',str(child_report),'--child']
        try:
            completed=subprocess.run(command,capture_output=True,text=True,
                                     timeout=timeout,check=False)
            row={'mode':selected,'exit_code':completed.returncode,
                 'stdout':completed.stdout,'stderr':completed.stderr}
        except subprocess.TimeoutExpired as exc:
            def decode(value):return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''
            row={'mode':selected,'timed_out':True,'exit_code':124,
                 'stdout':decode(exc.stdout),'stderr':decode(exc.stderr)}
        row['report']=str(child_report)
        row['context_report']=str(child_report.with_suffix('.context.json'))
        result['processes'].append(row)
        _write(report,result)
    result['status']='diagnosis-complete'
    _write(report,result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('compare','default','explicit'),default='compare')
    parser.add_argument('--report',type=Path,default=Path('scratch/gl-context-diagnostics.json'))
    parser.add_argument('--timeout',type=int,default=30)
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.child:
        if args.mode=='compare':parser.error('a child requires one concrete detection mode')
        return run_child(args.mode,args.report)
    result=run_isolated(mode=args.mode,report=args.report,timeout=args.timeout)
    return int(any(row['exit_code'] for row in result['processes']))


if __name__=='__main__':raise SystemExit(main())
