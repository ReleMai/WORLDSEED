"""Launch the isolated NPC job lab or run a reproducible headless experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldseed.labs.npc_jobs import NPCJobLab, SCENARIOS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=tuple(SCENARIOS), default="supply_chain")
    parser.add_argument("--seed", default="npc-lab", help="Deterministic seed for worker profiles")
    parser.add_argument("--workers", type=int, default=1, help="Workers per job (1–8)")
    parser.add_argument("--headless", action="store_true", help="Run without importing pygame")
    parser.add_argument("--minutes", type=int, default=None,
                        help="Minutes to simulate (default: 720 headless, 0 in viewer; max 10080)")
    parser.add_argument("--output", type=Path, help="Write final snapshot JSON to this file")
    parser.add_argument("--list-scenarios", action="store_true")
    args = parser.parse_args(argv)
    if args.list_scenarios:
        for name, description in SCENARIOS.items():
            print(f"{name}: {description}")
        return 0
    try:
        lab = NPCJobLab(scenario=args.scenario, seed=args.seed, workers=args.workers)
        minutes = args.minutes if args.minutes is not None else (720 if args.headless else 0)
        lab.run(minutes)
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    if not args.headless:
        from worldseed.labs.npc_job_viewer import run_viewer
        lab = run_viewer(lab)
    snapshot = lab.snapshot()
    payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    if args.headless:
        print(payload, end="")
    return 1 if snapshot["metrics"]["warnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
