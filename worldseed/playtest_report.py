"""Local, privacy-conscious WORLDSEED playtest report for player-approved sharing.

No networking, automatic upload, save/database collection or raw key logging.
The existing session JSONL and profiler are summarized without copying raw
messages, world names, player names, full tracebacks, or absolute paths.
"""
from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import re
import sys
import zipfile

from worldseed.config import DATA_DIR, PACKAGE_ROOT, ENGINE_VERSION

MAX_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 50000
MAX_TIMELINE = 240
TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")


def safe_label(value: object) -> str:
    """Allow only neutral event/stage identifiers; never leak freeform text."""
    label = str(value)
    return label if TOKEN.fullmatch(label) else 'redacted'


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    left = int(index)
    return round(values[left] + (values[min(left + 1, len(values) - 1)] - values[left]) * (index - left), 2)


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 2) if 0 <= number <= 3600000 else None


def summarize_jsonl(lines, *, source_label='latest-session') -> dict:
    counts = Counter()
    commands = Counter()
    ui_groups = Counter()
    stages: dict[str, list[float]] = {}
    recent = deque(maxlen=MAX_TIMELINE)
    last = {}
    profiles = {}
    profile_recorded = False
    saves = {'autosave': [], 'checkpoint': [], 'unclassified': []}
    errors = []
    processed = 0
    for raw in lines:
        if processed >= MAX_EVENTS:
            break
        if len(raw) > 65536:
            continue
        try:
            event = json.loads(raw)
        except (json.JSONDecodeError, UnicodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        processed += 1
        kind = safe_label(event.get('kind', 'unknown'))
        counts[kind] += 1
        row = {'event': kind}
        elapsed = _number(event.get('elapsed_ms'))
        if elapsed is not None:
            row['elapsed_ms'] = elapsed
        if kind in ('command_start', 'command_end'):
            command = safe_label(event.get('command', 'unknown'))
            if kind == 'command_end':
                commands[command] += 1
            row['command'] = command
        if kind == 'ui_input':
            # UI event tokens may contain names, text entry or other secrets.
            # Only an allowlisted coarse input category is retained.
            key = str(event.get('key', ''))
            group = ('movement' if key.lower() in ('w','a','s','d','up','down','left','right')
                     else 'ui_action' if key.startswith(('UI_ACTION:', 'UI_SELECT:', 'UI_WINDOW_'))
                     else 'redraw' if key == 'UI_REDRAW'
                     else 'other')
            ui_groups[group] += 1
            row['input_category'] = group
        if kind == 'stage':
            label = safe_label(event.get('name', 'unnamed'))
            row['stage'] = label
            if elapsed is not None:
                bucket = stages.setdefault(label, [])
                if len(bucket) < 5000:
                    bucket.append(elapsed)
            if event.get('slow') is True:
                row['slow'] = True
        if kind == 'save' and elapsed is not None:
            # Never copy world paths, timestamps, or save-state content.
            # Count *all* bounded session saves, not just the recent timeline.
            group = ('checkpoint' if event.get('backup') is True else
                     'autosave' if event.get('backup') is False else 'unclassified')
            saves[group].append(elapsed)
        if kind in ('save', 'command_end', 'playtest_session_end', 'simulation_init'):
            for key in ('turn', 'minute', 'clock_minute'):
                value = event.get(key)
                if type(value) is int and 0 <= value < 1000000000:
                    last[key] = value
        if kind == 'exception':
            if len(errors) < 30:
                # Never copy exception messages or paths from tracebacks.
                error = str(event.get('error', ''))
                match = re.match(r"^([A-Za-z_][A-Za-z_0-9.]*)", error)
                errors.append({'where': safe_label(event.get('where', 'unknown')),
                               'exception_type': safe_label(match.group(1)) if match else 'unknown'})
        if kind == 'profile_summary' and isinstance(event.get('profile'), dict):
            profile_recorded = True
            profile = event['profile']
            for name, item in list(profile.get('stages', {}).items())[:96]:
                if not isinstance(item, dict):
                    continue
                label = safe_label(name)
                profiles[label] = {key: number for key in
                    ('count', 'p50_ms', 'p95_ms', 'p99_ms', 'lifetime_worst_ms', 'lifetime_over_100ms_count')
                    if (number := _number(item.get(key))) is not None}
        if kind not in ('ui_input', 'profile_summary'):
            t = _number(event.get('t_ms'))
            if t is not None:
                row['time_ms'] = t
            recent.append(row)
    stage_stats = {name: {'samples': len(values),
                          'p50_ms': percentile(values, 0.5),
                          'p95_ms': percentile(values, 0.95),
                          'worst_ms': round(max(values), 2)}
                   for name, values in sorted(stages.items()) if values}
    save_stats = {group: {'samples': len(values),
                          'p50_ms': percentile(values, 0.5),
                          'p95_ms': percentile(values, 0.95),
                          'worst_ms': round(max(values), 2),
                          'over_100ms': sum(value > 100 for value in values)}
                  for group, values in saves.items() if values}
    return {
        'source': source_label, 'events_read': processed,
        'event_counts': dict(sorted(counts.items())),
        'command_counts': dict(sorted(commands.items())),
        'input_categories': dict(sorted(ui_groups.items())),
        'stage_timings': stage_stats, 'runtime_profile': profiles,
        'profile_status': 'captured' if profile_recorded else 'not_recorded',
        'save_timings': save_stats,
        'last_progress': last, 'exceptions': errors, 'recent_events': list(recent),
    }


def _latest_session(root: Path) -> Path | None:
    folder = root / 'logs'
    candidates = list(folder.glob('WORLDSEED_DEBUG_*.jsonl')) if folder.is_dir() else []
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _log_lines(path: Path):
    """Read only the most recent bounded tail from an already rotated log."""
    with path.open('rb') as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - MAX_BYTES))
        if size > MAX_BYTES:
            handle.readline()  # Drop partial first JSONL event.
        for row in handle:
            yield row.decode('utf-8', errors='replace')


def report_payload(root: Path) -> dict:
    root = Path(root)
    build_path = root / 'PLAYTEST_BUILD.json'
    build = {}
    if build_path.is_file():
        try:
            info = json.loads(build_path.read_text(encoding='utf-8'))
            build = {k: safe_label(info[k]) for k in ('commit', 'build_kind')
                     if k in info}
        except (ValueError, OSError, TypeError):
            pass
    source = _latest_session(root)
    session = summarize_jsonl(_log_lines(source)) if source else summarize_jsonl([])
    crash = root / 'WORLDSEED_CRASH.log'
    return {
        'schema': 'worldseed-playtest-report-v1', 'engine_version': ENGINE_VERSION,
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'build': build,
        'platform': {'os': platform.system(), 'release': platform.release(),
                     'architecture': platform.machine(),
                     'python': platform.python_version()},
        'session_found': source is not None,
        'crash_file_present': crash.is_file(), 'session': session,
        'privacy': {
            'automatic_upload': False, 'saves_included': False,
            'raw_logs_included': False, 'text_input_included': False,
            'absolute_paths_included': False,
        },
    }


def export_report(root: Path = Path.cwd()) -> Path:
    """Only writes a shareable, sanitized report in a local ZIP; no uploads."""
    root = Path(root).resolve()
    out = root / 'playtest_reports'
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    destination = out / f'WORLDSEED_PLAYTEST_REPORT_{stamp}.zip'
    payload = report_payload(root)
    guidance = (
        'WORLDSEED local playtest report\n\n'
        'Upload this ZIP to your ChatGPT WORLDSEED conversation to request analysis.\n'
        'No files were transmitted by the game or report exporter.\n'
        'The default report does not contain your saves, raw debug logs,\n'
        'typed input, names, file paths or raw exception tracebacks.\n'
        'The report summarizes one most-recent session; review it before sharing.\n'
        'If a crash needs deeper diagnosis, you can separately choose to send\n'
        'specific logs or a save after inspecting them.\n'
    )
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('report.json', json.dumps(payload, indent=2, sort_keys=True) + '\n')
        archive.writestr('HOW_TO_SHARE.txt', guidance)
    return destination


def self_check() -> int:
    """Quick bundled asset/import smoke; never generates a world or touches saves."""
    import pygame
    from worldseed.content.registry import ContentRegistry
    checks = {
        'items': (DATA_DIR / 'items.json').is_file(),
        'recipes': (DATA_DIR / 'recipes.json').is_file(),
        'sprites': (PACKAGE_ROOT / 'assets' / 'sprites').is_dir(),
    }
    if not all(checks.values()):
        print('WORLDSEED_PLAYTEST_SELFCHECK_FAILED ' + json.dumps(checks))
        return 2
    registry = ContentRegistry.load(DATA_DIR)
    if not registry.items or not registry.terrains:
        print('WORLDSEED_PLAYTEST_SELFCHECK_FAILED missing content definitions')
        return 2
    print('WORLDSEED_PLAYTEST_SELFCHECK_OK ' + json.dumps({
        'engine': ENGINE_VERSION, 'pygame': pygame.version.ver,
        'items': len(registry.items), 'terrain_types': len(registry.terrains),
        'assets_present': checks['sprites'],
    }, sort_keys=True))
    return 0
