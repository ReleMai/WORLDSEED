from __future__ import annotations

import os
import shutil
import sys
import time
import ctypes

CSI = "\x1b["

WINDOWS_EXTENDED_KEYS={"H":"UP","P":"DOWN","K":"LEFT","M":"RIGHT","I":"PGUP","Q":"PGDN","G":"HOME","O":"END"}

def decode_windows_extended(code:str)->str:
    """Pure decoder for msvcrt extended keys; testable off Windows."""
    return WINDOWS_EXTENDED_KEYS.get(code, "")


def normalize_raw_key(key: str) -> str:
    """Normalize backend-specific key values into WORLDSEED's canonical vocabulary.

    Windows ``msvcrt.getwch`` returns the physical Escape key as the literal
    ``\x1b`` character, while the Unix escape-sequence parser historically
    returned ``ESC``.  UI code must never care which backend produced a key.
    """
    if key in {"\x1b", "ESC", "Esc", "escape", "Escape"}:
        return "ESC"
    return key


class Terminal:
    def __init__(self) -> None:
        self.use_unicode = True
        self.use_color = True
        self._old_termios = None
        self._win_input_mode = None
        self._win_input_handle = None
        self._realtime_callback = None

    def set_realtime_callback(self, callback) -> None:
        self._realtime_callback = callback

    def _pump_realtime(self) -> bool:
        callback=self._realtime_callback
        return bool(callback and callback())

    def size(self) -> tuple[int, int]:
        s = shutil.get_terminal_size((100, 30))
        return s.columns, s.lines

    def enter(self) -> None:
        os.system("")  # Enables ANSI processing in modern Windows terminals.
        # Mouse tracking prevents terminal hosts from interpreting right-click
        # as a paste action while WORLDSEED owns the alternate screen. Mouse
        # reports are consumed and ignored by read_key().
        sys.stdout.write(CSI + "?1049h" + CSI + "?25l" + CSI + "?1000h" + CSI + "?1006h" + CSI + "?2004h")
        sys.stdout.flush()
        if os.name == "nt":
            kernel=ctypes.windll.kernel32
            handle=kernel.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode=ctypes.c_uint()
            if handle and kernel.GetConsoleMode(handle,ctypes.byref(mode)):
                self._win_input_handle=handle;self._win_input_mode=int(mode.value)
                ENABLE_EXTENDED_FLAGS=0x0080;ENABLE_QUICK_EDIT_MODE=0x0040;ENABLE_MOUSE_INPUT=0x0010;ENABLE_VIRTUAL_TERMINAL_INPUT=0x0200
                # WORLDSEED reads Windows keys with msvcrt. Enabling VT input at
                # the same time makes arrows arrive as ESC-prefixed byte sequences;
                # under key-repeat the ESC byte can be observed before the rest and
                # falsely open Pause. Keep the native Windows extended-key path.
                new_mode=(int(mode.value)|ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE & ~ENABLE_MOUSE_INPUT & ~ENABLE_VIRTUAL_TERMINAL_INPUT
                kernel.SetConsoleMode(handle,new_mode)
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            self._old_termios = termios.tcgetattr(fd)
            tty.setcbreak(fd)

    def restore(self) -> None:
        try:
            if os.name != "nt" and self._old_termios is not None:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_termios)
        finally:
            if os.name == "nt" and self._win_input_handle and self._win_input_mode is not None:
                try:ctypes.windll.kernel32.SetConsoleMode(self._win_input_handle,self._win_input_mode)
                except Exception:pass
            sys.stdout.write("\x1b[0m" + CSI + "?1000l" + CSI + "?1006l" + CSI + "?2004l" + CSI + "?25h" + CSI + "?1049l")
            sys.stdout.flush()

    def read_key(self) -> str:
        if os.name == "nt":
            import msvcrt
            while not msvcrt.kbhit():
                if self._pump_realtime():return "UI_REDRAW"
                time.sleep(0.05)
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                code = msvcrt.getwch()
                return decode_windows_extended(code)
            if ch == "\x1b":
                # With ENABLE_VIRTUAL_TERMINAL_INPUT disabled, physical arrows
                # arrive through the native extended-key branch above. ESC can
                # therefore be returned immediately with no timing ambiguity.
                return "ESC"
            return normalize_raw_key(ch)
        import select
        while not select.select([sys.stdin], [], [], 0.05)[0]:
            if self._pump_realtime():return "UI_REDRAW"
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            # Minimal arrow-sequence parser.
            if select.select([sys.stdin], [], [], 0.03)[0]:
                a = sys.stdin.read(1)
                if a == "[" and select.select([sys.stdin], [], [], 0.03)[0]:
                    b = sys.stdin.read(1)
                    if b == "<":
                        # SGR mouse report; consume through final M/m.
                        while select.select([sys.stdin], [], [], 0.03)[0]:
                            q=sys.stdin.read(1)
                            if q in {"M","m"}:break
                        return "MOUSE"
                    if b in {"A","B","C","D","H","F"}:
                        return {"A":"UP","B":"DOWN","C":"RIGHT","D":"LEFT","H":"HOME","F":"END"}.get(b,"ESC")
                    if b == "2":
                        rest="";deadline=time.monotonic()+0.05
                        while time.monotonic()<deadline and len(rest)<3 and select.select([sys.stdin], [], [], 0.01)[0]:rest+=sys.stdin.read(1)
                        if rest=="00~":
                            tail="";deadline=time.monotonic()+1.0
                            while time.monotonic()<deadline and len(tail)<65536:
                                if select.select([sys.stdin], [], [], 0.02)[0]:
                                    tail=(tail+sys.stdin.read(1))[-8:]
                                    if tail.endswith("\x1b[201~"):break
                            return "PASTE"
                    if b in {"5","6","1","4"} and select.select([sys.stdin], [], [], 0.03)[0]:
                        tail=sys.stdin.read(1)
                        if tail=="~":return {"5":"PGUP","6":"PGDN","1":"HOME","4":"END"}.get(b,"ESC")
                    return "ESC"
            return "ESC"
        return normalize_raw_key(ch)

    def discard_pending_input(self) -> None:
        return

    def present(self, text: str) -> None:
        # Clear everything below the new frame so a previous taller modal cannot
        # bleed through/overlap the current UI.  Clearing *after* writing is much
        # less flickery than a full-screen clear before every map frame.
        sys.stdout.write(CSI + "H" + "\x1b[0m" + text + CSI + "J")
        sys.stdout.flush()
