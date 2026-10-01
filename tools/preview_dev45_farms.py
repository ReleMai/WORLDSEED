"""Headless QA of the actual prepared settlement-map presentation."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
from pathlib import Path
from types import SimpleNamespace

from tests.test_dev45_farm_compounds import FarmCompoundTests
from worldseed.core.coords import WorldPos
from worldseed.ui.atlas_map import AtlasControls, SettlementDetailData, _draw_settlement_detail
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.world.settlement_atlas import build_settlement_atlas


def main():
    FarmCompoundTests.setUpClass()
    skeleton=FarmCompoundTests().skeleton(population=45)
    town=SimpleNamespace(name="Dev45 Farmstead",population=45)
    snap=build_settlement_atlas(skeleton.plan,roads=skeleton.roads,parcels=skeleton.parcels,
                               structures=skeleton.structures,rooms=skeleton.rooms)
    state=AtlasControls((180,180))
    state.detail=SettlementDetailData(town,skeleton,snap)
    sim=SimpleNamespace(player_pos=WorldPos(180,180,0))
    output=Path("artifacts/dev45-farm-map-preview.png")
    output.parent.mkdir(parents=True,exist_ok=True)
    term=PygameTerminal(1440,940)
    term.enter()
    try:
        _draw_settlement_detail(term,sim,state)
        term.pg.image.save(term.screen,str(output))
        print(output.resolve())
    finally:
        term.restore()


if __name__=="__main__":
    main()
