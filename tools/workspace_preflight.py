"""Reject partial/stale workspaces before development or validation begins."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                          text=True, timeout=15, check=True).stdout.strip()


def check_snapshot(root: Path, manifest: dict, expected_head: str) -> list[str]:
    issues = []
    if manifest.get('commit') != expected_head:
        issues.append('snapshot commit differs from the freshly verified remote main')
    entries = manifest.get('tree', [])
    if not entries:
        return issues + ['empty snapshot tree']
    for entry in entries:
        path = root / entry['path']
        if not path.resolve().is_relative_to(root.resolve()):
            issues.append(f'unsafe snapshot path: {entry["path"]}')
            continue
        if not path.is_file():
            issues.append(f'missing: {entry["path"]}')
            continue
        data = path.read_bytes()
        digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        if digest != entry['sha']:
            issues.append(f'modified: {entry["path"]}')
    return issues


def check_git(root: Path, expected_head: str) -> list[str]:
    issues = []
    if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root.resolve():
        issues.append('selected directory is not the checkout root')
    origin = git(root, 'remote', 'get-url', 'origin').rstrip('/')
    if '://' not in origin and ':' in origin:
        origin = 'ssh://' + origin.replace(':', '/', 1)
    remote = urlparse(origin)
    if remote.hostname not in {'github.com', 'git.chatgpt-team.site'} or remote.path.strip('/').removesuffix('.git').lower() != 'relemai/worldseed':
        issues.append('origin is not the canonical ReleMai/WORLDSEED repository')
    if git(root, 'rev-parse', 'HEAD') != expected_head:
        issues.append('HEAD differs from freshly verified remote main')
    if git(root, 'status', '--porcelain'):
        issues.append('workspace has changes: preserve them and reconcile before starting a new task')
    branch = git(root, 'branch', '--show-current')
    if branch and branch != 'main':
        issues.append(f'non-main checkout: {branch}; do not resume an old branch automatically')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--expected-head', required=True, help='SHA obtained from a fresh remote-main read, never guessed')
    parser.add_argument('--snapshot', type=Path, help='complete GitHub recursive tree manifest for a connector-only snapshot')
    parser.add_argument('--check-dependencies', action='store_true', help='also require pygame-ce and Pillow for graphical/asset validation')
    args = parser.parse_args()
    try:
        issues = (check_snapshot(args.root, json.loads(args.snapshot.read_text()), args.expected_head)
                  if args.snapshot else check_git(args.root, args.expected_head))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        issues = [f'workspace verification failed: {exc}']
    if args.check_dependencies:
        for module, package in [('pygame', 'pygame-ce'), ('PIL', 'Pillow')]:
            if importlib.util.find_spec(module) is None:
                issues.append(f'missing test dependency: {package}; install before running graphical/asset checks')
    for issue in issues:
        print(f'PREFLIGHT FAIL: {issue}')
    if not issues:
        print(f'PREFLIGHT PASS: complete baseline {args.expected_head}')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
