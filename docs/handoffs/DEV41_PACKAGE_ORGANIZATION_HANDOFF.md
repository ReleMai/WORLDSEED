# Dev41 documentation and playtest-package handoff

## Scope / modules changed

- Moved top-level development notes, handoffs, and reference documents into `docs/development/`, `docs/handoffs/`, and `docs/reference/`.
- Kept `README.md` and `AGENTS.md` at repository root as the human and agent entry points.
- Added `docs/README.md` as the documentation index.
- Added `tools/package_playtest.py` for clean playtest ZIP creation.

## Public APIs / contracts

- The development workflow now lives at `docs/development/DEVELOPMENT.md`.
- Playtest ZIPs contain launchers, dependency metadata, `worldseed/`, and `docs/`.
- Playtest ZIPs exclude Git metadata, development artifacts, tests, tools, saves, databases, caches, and logs.

## Persistent fields / migration

None. Save schema, world-generation versions, and simulation state are unchanged.

## RNG namespaces

None.

## Tests added / changed

- The package script performs ZIP CRC validation and checks required and forbidden paths.
- Documentation links and repository path references were updated for the new layout.

## Performance implications

None in gameplay. Packaging reads the selected files once and uses ZIP deflate compression.

## UI exposure

None. This work only reorganizes repository documentation and packaging output.

## Known limitations

- The playtest ZIP is a source distribution and still requires Python 3.11 plus the declared dependencies.
- Developer-only tests, tools, screenshots, and validation artifacts remain available in Git but are intentionally absent from the playtest ZIP.

## Next dependency

Use `python tools/package_playtest.py` after a validated build to produce the next clean test archive under `dist/`.
