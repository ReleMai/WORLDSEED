"""Current-SDL GL bootstrap ownership, rejection and crash-evidence contracts."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from worldseed.presentation.gl_context import create_sdl_context, native_gl_info
from worldseed.presentation.gl_worldspace import GPUBackendUnavailable
from tools.worldseed_gl_diagnostics import run_isolated


def pygame_stub():
    return SimpleNamespace(GL_CONTEXT_MAJOR_VERSION=17,GL_CONTEXT_MINOR_VERSION=18,
        GL_CONTEXT_PROFILE_MASK=21,GL_CONTEXT_FLAGS=20,GL_DOUBLEBUFFER=5,
        GL_DEPTH_SIZE=6,GL_STENCIL_SIZE=7,get_sdl_version=lambda:(2,32,10),
        display=SimpleNamespace(get_init=lambda:True,get_surface=lambda:object(),
            get_driver=lambda:'windows',gl_get_attribute=lambda attr:3))


def native_stub(**changes):
    return dict(api='wgl',library='opengl32.dll',current_context='0x1234',
                current_dc='0xabcd',version='4.6.0 Test',vendor='Test vendor',
                renderer='Test renderer',**changes)


def context_stub():
    return SimpleNamespace(version_code=460,info={'GL_VENDOR':'Test vendor',
                           'GL_RENDERER':'Test renderer','GL_VERSION':'4.6.0 Test'})


class _NativeFunction:
    def __init__(self,result):self.result=result;self.calls=[]
    def __call__(self,*args):
        self.calls.append(args)
        return self.result(*args) if callable(self.result) else self.result


class GLContextContracts(unittest.TestCase):
    def test_explicit_windows_detection_has_durable_preflight_before_native_loader(self):
        pg=pygame_stub()
        native=native_stub()
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()) as output:
            report=Path(folder)/'bootstrap.json'
            def probe():
                evidence=json.loads(report.read_text())
                self.assertEqual(evidence['stage'],'before_native_probe')
                self.assertEqual(evidence['events'][-1]['evidence']['sdl_video_driver'],'windows')
                return native
            def loader(**settings):
                self.assertEqual(settings,{'require':330,'libgl':'opengl32.dll'})
                evidence=json.loads(report.read_text())
                self.assertEqual(evidence['stage'],'before_moderngl')
                self.assertEqual(evidence['events'][-2]['evidence']['native'],native)
                return context_stub()
            context=create_sdl_context(pg,diagnostics=report,context_loader=loader,
                                       native_probe=probe)
            self.assertEqual(context.version_code,460)
            self.assertEqual(json.loads(report.read_text())['stage'],'ready')
            self.assertIn('before_moderngl',output.getvalue())

    def test_default_comparison_uses_existing_context_without_standalone_or_share(self):
        loader=Mock(return_value=context_stub())
        with redirect_stdout(io.StringIO()):
            create_sdl_context(pygame_stub(),loader='default',
                               context_loader=loader,native_probe=native_stub)
        loader.assert_called_once_with(require=330)

    def test_no_current_unsupported_or_uninitialized_sdl_never_enters_loader(self):
        for changes in ({'current_context':None},{'version':'2.1 Test'},
                        {'version':'OpenGL ES 3.3 Test'},{'version':None}):
            native=native_stub();native.update(changes)
            loader=Mock()
            with self.subTest(changes=changes),redirect_stdout(io.StringIO()), \
                    self.assertRaises(GPUBackendUnavailable):
                create_sdl_context(pygame_stub(),context_loader=loader,
                                   native_probe=lambda:native)
            loader.assert_not_called()
        pg=pygame_stub();pg.display.get_init=lambda:False
        with redirect_stdout(io.StringIO()),self.assertRaises(GPUBackendUnavailable):
            create_sdl_context(pg,context_loader=loader,native_probe=native_stub)
        loader.assert_not_called()

    def test_native_wgl_metadata_checks_context_before_reading_strings(self):
        get_string=_NativeFunction(lambda code:{0x1F00:b'Vendor',0x1F01:b'Driver',0x1F02:b'3.3'}[code])
        library=SimpleNamespace(wglGetCurrentContext=_NativeFunction(0),
                                wglGetCurrentDC=_NativeFunction(0),glGetString=get_string)
        with patch('worldseed.presentation.gl_context.ctypes.WinDLL',return_value=library,create=True):
            self.assertIsNone(native_gl_info('win32')['current_context'])
            self.assertEqual(get_string.calls,[])
            library.wglGetCurrentContext.result=0x1234
            library.wglGetCurrentDC.result=0xabcd
            evidence=native_gl_info('win32')
        self.assertEqual((evidence['current_context'],evidence['current_dc']),('0x1234','0xabcd'))
        self.assertEqual((evidence['version'],evidence['renderer']),('3.3','Driver'))

    def test_detection_failure_retains_raw_preflight_and_error(self):
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            report=Path(folder)/'bootstrap.json'
            loader=Mock(side_effect=RuntimeError('detector rejected context'))
            with self.assertRaisesRegex(GPUBackendUnavailable,'detector rejected context'):
                create_sdl_context(pygame_stub(),diagnostics=report,
                    context_loader=loader,native_probe=native_stub)
            evidence=json.loads(report.read_text())
            self.assertEqual(evidence['stage'],'failed')
            self.assertEqual(evidence['events'][1]['evidence']['native']['version'],'4.6.0 Test')
            self.assertIn('detector rejected context',evidence['events'][-1]['error'])

    def test_isolated_comparison_keeps_crash_evidence_and_attempts_other_mode(self):
        crash=SimpleNamespace(returncode=-1073741819,stdout='before_moderngl\n',stderr='access violation')
        success=SimpleNamespace(returncode=0,stdout='context detected\n',stderr='')
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()), \
                patch('tools.worldseed_gl_diagnostics.subprocess.run',side_effect=(crash,success)) as run:
            report=Path(folder)/'diagnostics.json'
            result=run_isolated(report=report,timeout=12)
            persisted=json.loads(report.read_text())
        self.assertEqual(len(run.call_args_list),2)
        commands=[call.args[0] for call in run.call_args_list]
        self.assertTrue(all('-X' in command and 'faulthandler' in command and '--child' in command for command in commands))
        self.assertNotEqual(commands[0],commands[1])
        self.assertEqual([row['exit_code'] for row in result['processes']],[-1073741819,0])
        self.assertEqual(persisted['processes'][0]['stderr'],'access violation')
        self.assertFalse(result['native_gpu_accepted'])

    def test_actual_egl_current_context_preflight_when_available(self):
        try:import moderngl
        except ImportError:self.skipTest('optional ModernGL unavailable')
        try:context=moderngl.create_standalone_context(require=330,backend='egl')
        except Exception as exc:self.skipTest('optional EGL driver unavailable: '+type(exc).__name__)
        try:
            if not __import__('sys').platform.startswith('linux'):
                self.skipTest('raw EGL preflight is Linux-specific')
            raw=native_gl_info()
            self.assertEqual(raw['api'],'egl')
            self.assertIsNotNone(raw['current_context'])
            self.assertTrue(raw['version'])
            # Detect the same current EGL context through the real explicit
            # function loader. The SDL helper never creates this test context.
            with redirect_stdout(io.StringIO()):
                detected=create_sdl_context(pygame_stub())
            self.assertEqual(detected.version_code,context.version_code)
            self.assertEqual(detected.info['GL_RENDERER'],context.info['GL_RENDERER'])
            self.assertEqual(native_gl_info()['current_context'],raw['current_context'])
            detected.release()
        finally:context.release()


if __name__=='__main__':unittest.main()
