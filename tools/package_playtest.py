"""Build a clean, deterministic WORLDSEED playtest archive."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldseed.config import ENGINE_VERSION  # noqa: E402


ROOT_FILES = (
    "README.md",
    "RUN_WORLDSEED.bat",
    "RUN_WORLDSEED_TERMINAL.bat",
    "pyproject.toml",
    "requirements.txt",
    "requirements-pygame-ce.txt",
    "run_worldseed.py",
    "run_npc_job_lab.py",
    "RUN_NPC_JOB_LAB.bat",
)
CONTENT_DIRECTORIES = ("worldseed", "docs")
EXCLUDED_PARTS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".db", ".db-wal", ".db-shm"}
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def iter_package_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    for directory in CONTENT_DIRECTORIES:
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())
    return sorted(
        path
        for path in files
        if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
        and path.suffix.lower() not in EXCLUDED_SUFFIXES
    )


def build_archive(output_directory: Path) -> Path:
    package_name = f"WORLDSEED-{ENGINE_VERSION}-playtest"
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / f"{package_name}.zip"

    with zipfile.ZipFile(
        destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for source in iter_package_files():
            relative = source.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"{package_name}/{relative}", FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)

    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
        names = set(archive.namelist())
        required = {
            f"{package_name}/README.md",
            f"{package_name}/RUN_WORLDSEED.bat",
            f"{package_name}/worldseed/app.py",
            f"{package_name}/docs/README.md",
            f"{package_name}/docs/handoffs/DEV41_REALTIME_SOCIAL_WORLD_HANDOFF.md",
        }
        missing = sorted(required - names)
        if missing:
            raise RuntimeError(f"ZIP is missing required files: {missing}")
        forbidden = (".git/", "artifacts/", "tests/", "tools/", "saves/")
        leaked = sorted(
            name
            for name in names
            if any(name.startswith(f"{package_name}/{prefix}") for prefix in forbidden)
        )
        if leaked:
            raise RuntimeError(f"ZIP contains development/runtime files: {leaked[:5]}")

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(destination)
    print(f"files={len(iter_package_files())}")
    print(f"bytes={destination.stat().st_size}")
    print(f"sha256={digest}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="Destination directory (default: repository dist directory)",
    )
    args = parser.parse_args()
    build_archive(args.output_dir.resolve())


if __name__ == "__main__":
    main()
