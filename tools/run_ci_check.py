"""Run one CI command with bounded output buffering and a hard deadline."""
from __future__ import annotations

import argparse
import codecs
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

try:
    from tools.process_tree import ProcessTree
except ModuleNotFoundError:  # Direct invocation from tools/.
    from process_tree import ProcessTree


def _annotation(message: str) -> str:
    return message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def _console_print(*values, sep: str = ' ', end: str = '\n', flush: bool = False) -> None:
    """Write diagnostic output without crashing on a narrow Windows console codec."""
    text=sep.join(str(value) for value in values)+end
    stream=sys.stdout
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding=getattr(stream,'encoding',None) or 'utf-8'
        safe=text.encode(encoding,errors='backslashreplace').decode(encoding,errors='strict')
        stream.write(safe)
    if flush:
        stream.flush()


def run(name: str, command: list[str], timeout: float, heartbeat: float = 30) -> int:
    if not command or not all(math.isfinite(v) and v > 0 for v in (timeout, heartbeat)):
        raise ValueError('command, finite positive timeout, and heartbeat are required')
    started = time.monotonic()
    _console_print(f'CHECK START {name}: {command!r} (limit {timeout:g}s)', flush=True)
    events: queue.Queue[str | None] = queue.Queue(maxsize=256)
    stopping = threading.Event()
    tree = None
    process = None
    try:
        tree = ProcessTree()
        actual = command
        if os.name == 'nt':
            # Do not let the command spawn children before job assignment.
            gate = "import os,sys; token=sys.stdin.buffer.read(1); sys.exit(1) if token!=b'1' else os.execvp(sys.argv[1],sys.argv[1:])"
            actual = [sys.executable, '-u', '-c', gate, *command]
        process = subprocess.Popen(actual, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.PIPE if os.name == 'nt' else subprocess.DEVNULL,
                                   start_new_session=(os.name != 'nt'))
        tree.attach(process)
        if os.name == 'nt':
            process.stdin.write(b'1')
            process.stdin.close()
    except OSError as exc:
        if process is not None:
            tree.stop(process)
        if tree is not None:
            tree.close()
        _console_print(f'::error::{_annotation(f"{name}: could not start check: {exc}")}', flush=True)
        return 1

    def emit(value):
        while not stopping.is_set():
            try:
                events.put(value, timeout=.1)
                return
            except queue.Full:
                pass

    def read_output():
        # Fixed-size chunks also bound memory for output without newlines.
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            with process.stdout:
                while not stopping.is_set():
                    chunk = process.stdout.read1(4096)
                    if not chunk:
                        break
                    emit(decoder.decode(chunk))
                emit(decoder.decode(b'', final=True))
        finally:
            emit(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    next_beat = started + heartbeat
    deadline = started + timeout
    timed_out = False
    eof = False
    try:
        while not (eof and process.poll() is not None):
            now = time.monotonic()
            # Deadline applies to both process completion and output-pipe drain.
            if now >= deadline:
                timed_out = True
                _console_print(f'CHECK TIMEOUT {name}: exceeded {timeout:g}s; stopping child processes', flush=True)
                break
            delay = max(.001, min(.1, deadline - now, next_beat - now))
            if eof:
                stopping.wait(delay)
            else:
                try:
                    chunk = events.get(timeout=delay)
                except queue.Empty:
                    chunk = ''
                if chunk is None:
                    eof = True
                elif chunk:
                    _console_print(chunk, end='', flush=True)
            now = time.monotonic()
            if now >= next_beat:
                _console_print(f'CHECK RUNNING {name}: {now - started:.0f}s elapsed, pid {process.pid}', flush=True)
                next_beat = now + heartbeat
    finally:
        stopping.set()
        # Also clean up descendants after a parent exits successfully.
        tree.stop(process)
        tree.close()
        reader.join(timeout=.5)
    code = process.poll()
    elapsed = time.monotonic() - started
    status = 'TIMEOUT' if timed_out else 'PASS' if code == 0 else 'FAIL'
    summary = f'{name}: {status} ({elapsed:.1f}s, exit {code})'
    _console_print(f'CHECK {summary}', flush=True)
    if status != 'PASS':
        _console_print(f'::error::{_annotation(summary)}', flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as output:
            output.write(f'- {summary}\n')
    return 124 if timed_out else code if code is not None and code > 0 else 1 if code != 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--timeout', type=float, required=True, help='maximum seconds for this check')
    parser.add_argument('--heartbeat', type=float, default=30, help='seconds between progress messages')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or not all(math.isfinite(v) and v > 0 for v in (args.timeout, args.heartbeat)):
        parser.error('provide -- command and finite positive timeout/heartbeat')
    return run(args.name, command, args.timeout, args.heartbeat)


if __name__ == '__main__':
    raise SystemExit(main())
