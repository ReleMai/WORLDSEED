from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worldseed.persistence.database import WorldDatabase


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/verify_save.py saves/world.db")
        return 2
    db = WorldDatabase.open(Path(sys.argv[1]))
    try:
        issues = db.verify()
        if issues:
            print("SAVE ISSUES:")
            for issue in issues:
                print(" -", issue)
            return 1
        print("Save integrity: OK")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
