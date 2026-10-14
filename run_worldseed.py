"""WORLDSEED entry point for game, local diagnostic report and bundled self-check."""
import sys


def main() -> int:
    if '--playtest-export' in sys.argv:
        from worldseed.playtest_report import export_report
        destination = export_report()
        print('WORLDSEED_PLAYTEST_REPORT ' + str(destination))
        return 0
    if '--playtest-selfcheck' in sys.argv:
        from worldseed.playtest_report import self_check
        return self_check()
    from worldseed.app import main as game_main
    return game_main()


if __name__ == '__main__':
    raise SystemExit(main())
