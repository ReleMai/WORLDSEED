"""Bounded six-function QA of interiors derived from one real generated city."""
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
from pathlib import Path
import sys
import argparse
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tests.test_property_storage_casing import PropertyStorageCasingTests
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.building_shells import shell_from_plan
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.interiors import InteriorSystem, build_interior, position_clear
from worldseed.ui.pygame_terminal import PygameTerminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', default='dev47', help='QA output basename prefix.')
    parser.add_argument('--functions', default='residence,inn,barracks,smithy,school,clinic',
                        help='Comma-separated prepared building functions to render (up to six).')
    args = parser.parse_args()
    if not args.prefix.replace('-', '').isalnum():
        parser.error('Prefix must contain only letters, digits and hyphens')
    functions = args.functions.split(',')
    if not 1 <= len(functions) <= 6 or any(not f.replace('_', '').isalnum() for f in functions):
        parser.error('Select one to six valid building function names')
    PropertyStorageCasingTests.setUpClass()
    fixture=PropertyStorageCasingTests()
    state,town,physical,*_=fixture._fixture()
    region=physical.region_planner.plan(0,0,persist=False)
    skeleton=physical.skeleton_planner.plan(region,'settlement:dev47-interior-qa',240,persist=False)
    entities=EntityStore();player_id=entities.spawn(preferred_id=1)
    entities.add(player_id,Inventory());entities.add(player_id,Vitals())
    sim=SimpleNamespace(state=state,registry=fixture.registry,entities=entities,player_id=player_id,
                        player_pos=WorldPos(180,180,0),known_npc_ids=lambda:set(),log=[],
                        clock=SimpleNamespace(minute=720,label=lambda:'Y1 Spring 2, 12:00'))
    sim.interiors=InteriorSystem(sim)
    term=PygameTerminal(1280,832);term.enter()
    output_dir=Path('artifacts');output_dir.mkdir(parents=True,exist_ok=True)
    frames=[]
    try:
        for function in functions:
            structure=next((s for s in sorted(skeleton.structures,key=lambda s:s.uid) if s.function==function and s.enclosed),None)
            if structure is None:
                parser.error(f'No {function} in this prepared city economy; use preview_dev48_workstations.py for profile fixtures.')
            shell=shell_from_plan(structure,skeleton.plan.uid,skeleton.pieces)
            assert shell and shell.entrance and shell.door_uid,function
            door=SimpleNamespace(uid=shell.door_uid,property_id=structure.uid,x=shell.entrance[0],
                                 y=shell.entrance[1],z=0,owner_uid='')
            rooms=[r for r in skeleton.rooms if r.structure_plan_id==structure.uid]
            pieces=[p for p in skeleton.pieces if p.structure_plan_id==structure.uid]
            plan=build_interior(structure,door,rooms,pieces)
            state.interiors[plan.uid]=plan
            offsets=(0,250,-250,500,-500,1000,-1000)
            candidates=sorted(((dx*dx+dy*dy,plan.width//2+dx,plan.height//2+dy)
                              for dx in offsets for dy in offsets))
            point=next(((x,y) for _,x,y in candidates if position_clear(plan,x,y)),(plan.entry_x,plan.entry_y))
            sim.interiors._remove_actor('player')
            sim.interiors._put_actor('player',InteriorActor(plan.uid,*point))
            state.player_hunting_stance='normal'
            before=state.to_dict()
            term._tile_px=max(16,min(56,int(min(904000/plan.width,619000/plan.height)*.9)))
            term.present_game(fixture.registry,object(),entities,sim,player_id,
                              f'{plan.name} • generated building {structure.uid} • {len(plan.furniture)} original fixtures')
            assert state.to_dict()==before,'Rendering mutated simulation state'
            assert any(token=='UI_STANCE:aggressive' for _,token in term._pointer_targets),'Aggressive stance button missing'
            output=output_dir/f'{args.prefix}-interior-{function}-preview.png'
            term.pg.image.save(term.screen,str(output))
            frames.append((function,term.screen.copy()))
            print(f'{output.resolve()} ({len(plan.rooms)} rooms, {len(plan.furniture)} original fixtures; observational)')
            missing=[f.piece_id for f in plan.furniture
                     if term._visuals.resolve(term._visuals.ref('interiors',f.piece_id)) is None
                     and term._visuals.resolve(term._visuals.ref('settlement_pieces',f.piece_id)) is None]
            native = [pid for pid in missing if 'clutter' in fixture.registry.settlement_pieces[pid].tags]
            glyphs = [pid for pid in missing if pid not in native]
            if native:print('Native prop art: '+', '.join(sorted(set(native))))
            if glyphs:print('Explicit glyph fallbacks: '+', '.join(sorted(set(glyphs))))
        contact=term.pg.Surface((1280*2,872*3));contact.fill((13,16,18))
        for index,(function,frame) in enumerate(frames):
            x,y=(index%2)*1280,(index//2)*872
            contact.blit(term.title_font.render(function.title(),True,term._theme['accent']),(x+18,y+8))
            contact.blit(frame,(x,y+40))
        output=output_dir/f'{args.prefix}-interior-contact.png'
        term.pg.image.save(contact,str(output));print(output.resolve())
    finally:
        term.restore()


if __name__=='__main__':main()
