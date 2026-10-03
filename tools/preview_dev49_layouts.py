"""Headless QA of five synthetic-terrain plans in the real settlement map.

This is prepared planner/presentation evidence, not a real-world geography or
live-game claim. Images are written only to an explicitly supplied QA folder.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.audit_settlement_layouts import ARCHETYPES, synthetic_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.ui.atlas_map import AtlasControls, SettlementDetailData, _draw_settlement_detail
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.world.settlement_atlas import build_settlement_atlas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--population", type=int, default=110)
    args = parser.parse_args()
    if not 21 <= args.population <= 300:
        parser.error("Population must be bounded to 21..300 for this QA tool")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    registry = ContentRegistry.load(DATA_DIR)
    term = PygameTerminal(1440, 940)
    term.enter()
    try:
        for archetype in ARCHETYPES:
            world, region, uid = synthetic_fixture(registry, archetype, args.population, version=11)
            skeleton = SettlementSkeletonPlanner(world).plan(region, uid, args.population, persist=False)
            snapshot = build_settlement_atlas(skeleton.plan, roads=skeleton.roads, parcels=skeleton.parcels,
                                              structures=skeleton.structures, rooms=skeleton.rooms)
            town = SimpleNamespace(name=f"Dev49 {archetype.title()} — synthetic QA", population=args.population)
            controls = AtlasControls((256, 256))
            controls.detail = SettlementDetailData(town, skeleton, snapshot)
            sim = SimpleNamespace(player_pos=WorldPos(256, 256, 0))
            before = skeleton.to_dict()
            _draw_settlement_detail(term, sim, controls)
            assert skeleton.to_dict() == before, "Map drawing mutated authoritative plan"
            output = output_dir / f"dev49-{archetype}-settlement-map.png"
            term.pg.image.save(term.screen, str(output))
            fields = sum(len(p.cells) for p in skeleton.parcels if p.purpose == "field")
            print(f"{output} ({skeleton.plan.morphology}; {len(skeleton.roads)} roads; "
                  f"{fields} field cells; {', '.join(skeleton.plan.resource_specializations)}; observational)")
    finally:
        term.restore()


if __name__ == "__main__":
    main()
