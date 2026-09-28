"""Own a check's descendants, including children that outlive their parent."""
from __future__ import annotations

import os
import signal
import subprocess


class ProcessTree:
    def __init__(self):
        self.job = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes as w

            class BasicLimits(ctypes.Structure):
                _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                            ('flags', w.DWORD), ('min_working_set', ctypes.c_size_t),
                            ('max_working_set', ctypes.c_size_t), ('active_processes', w.DWORD),
                            ('affinity', ctypes.c_size_t), ('priority', w.DWORD),
                            ('scheduling', w.DWORD)]

            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint64) for name in
                            ('reads', 'writes', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]

            class Limits(ctypes.Structure):
                _fields_ = [('basic', BasicLimits), ('io', IO),
                            ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                            ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]

            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
            self.kernel.CreateJobObjectW.restype = w.HANDLE
            self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
            self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            self.kernel.CloseHandle.argtypes = [w.HANDLE]
            self.job = self.kernel.CreateJobObjectW(None, None)
            if not self.job:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = Limits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self.kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                error = ctypes.WinError(ctypes.get_last_error())
                self.close()
                raise error

    def attach(self, process):
        if self.job:
            import ctypes
            if not self.kernel.AssignProcessToJobObject(self.job, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())

    def stop(self, process):
        if self.job:
            self.close()
        elif os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
