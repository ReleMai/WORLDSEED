"""WORLDSEED entry point for game, local diagnostic report and bundled self-check."""
import sys


def _enable_bundled_playtest_profiling() -> bool:
    """Enable timing in the packaged test build, including direct EXE launches.

    Normal/source builds remain opt-in. A bundle marker is checked only for
    frozen executables; report export and self-check never enter this path.
    """
    import json
    import os
    from pathlib import Path

    if not getattr(sys, 'frozen', False):
        return False
    try:
        identity = json.loads((Path(sys.executable).resolve().parent / 'PLAYTEST_BUILD.json')
                              .read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(identity, dict) or identity.get('build_kind') != 'windows-one-dir':
        return False
    commit = identity.get('commit')
    if not isinstance(commit, str) or len(commit) != 40 or any(
        character not in '0123456789abcdef' for character in commit
    ):
        return False
    os.environ['WORLDSEED_PROFILE'] = '1'
    return True


def main() -> int:
    if '--playtest-export' in sys.argv:
        from worldseed.playtest_report import export_report
        destination = export_report()
        print('WORLDSEED_PLAYTEST_REPORT ' + str(destination))
        return 0
    if '--playtest-selfcheck' in sys.argv:
        from worldseed.playtest_report import self_check
        return self_check()
    _enable_bundled_playtest_profiling()
    from worldseed.app import main as game_main
    return game_main()


if __name__ == '__main__':
    raise SystemExit(main())
