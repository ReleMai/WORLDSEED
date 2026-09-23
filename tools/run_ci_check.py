"""Run one CI command with streamed output, a heartbeat, and a hard deadline."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


def _annotation(message: str) -> str:
    return message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def _stop_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        import signal
        os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def run(name: str, command: list[str], timeout: float, heartbeat: float = 30) -> int:
    if not command or timeout <= 0 or heartbeat <= 0:
        raise ValueError('command, positive timeout, and positive heartbeat are required')
    started = time.monotonic()
    print(f'CHECK START {name}: {command!r} (limit {timeout:g}s)', flush=True)
    events: queue.Queue[str | None] = queue.Queue()
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors='replace',
                                   bufsize=1, start_new_session=(os.name != 'nt'),
                                   creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0))
    except OSError as exc:
        message = f'{name}: could not start {command[0]}: {exc}'
        print(f'::error::{_annotation(message)}', flush=True)
        return 1

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            events.put(line)
        events.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    next_beat = started + heartbeat
    deadline = started + timeout
    timed_out = False
    while True:
        now = time.monotonic()
        if now >= deadline and process.poll() is None:
            timed_out = True
            print(f'CHECK TIMEOUT {name}: exceeded {timeout:g}s; stopping child processes', flush=True)
            _stop_tree(process)
        try:
            line = events.get(timeout=max(0.01, min(0.5, next_beat - now)))
        except queue.Empty:
            line = ''
        if line is None:
            break
        if line:
            print(line, end='', flush=True)
        now = time.monotonic()
        if now >= next_beat and not timed_out:
            print(f'CHECK RUNNING {name}: {now - started:.0f}s elapsed, pid {process.pid}', flush=True)
            next_beat = now + heartbeat
    code = process.wait()
    assert process.stdout is not None
    process.stdout.close()
    elapsed = time.monotonic() - started
    status = 'TIMEOUT' if timed_out else 'PASS' if code == 0 else 'FAIL'
    summary = f'{name}: {status} ({elapsed:.1f}s, exit {code})'
    print(f'CHECK {summary}', flush=True)
    if status != 'PASS':
        print(f'::error::{_annotation(summary)}', flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as output:
            output.write(f'- {summary}\n')
    return 124 if timed_out else code if code > 0 else 1 if code < 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--timeout', type=float, required=True, help='maximum seconds for this check')
    parser.add_argument('--heartbeat', type=float, default=30, help='seconds between progress messages')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or args.timeout <= 0 or args.heartbeat <= 0:
        parser.error('provide -- command and positive timeout/heartbeat')
    return run(args.name, command, args.timeout, args.heartbeat)


if __name__ == '__main__':
    raise SystemExit(main())
