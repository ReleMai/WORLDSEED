"""Audit every registered facade against physical geometry; render review sheets."""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
from worldseed.config import DATA_DIR
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import draw_shells, shell_at_pointer, _anchor_catalog
from worldseed.ui.homestead_art import cabin_asset_path, topdown_cabin_asset_path, topdown_manifest
from worldseed.systems.homestead_blueprints import catalog as homestead_catalog
from worldseed.ui.pygame_terminal import PygameTerminal


def audit(output):
    output.mkdir(parents=True,exist_ok=True)
    root=Path(DATA_DIR).parent
    refs=json.loads((root/'assets/visuals.json').read_text(encoding='utf-8'))['building_shells']
    paths=sorted(set(refs.values()))
    term=PygameTerminal(1280,960);term.enter()
    cases=0;report=[]
    try:
        pg=term.pg
        # A registered facade, an authored homestead sprite, and a door leaf
        # have different geometry contracts. Audit each instead of assuming
        # every non-facade PNG is a door.
        facade_paths={(root/p).resolve() for p in paths}
        cabins={style_id for style_id,style in homestead_catalog()[1].items()
                if style['home_id']=='log_cabin'}
        homestead_paths=set()
        for style_id in sorted(cabins):
            asset=cabin_asset_path(style_id)
            assert asset is not None,style_id+' has no legacy cabin artwork'
            homestead_paths.add(asset.resolve())
        for style_id in sorted(topdown_manifest()['style_family']):
            assert style_id in cabins,style_id+' is not in the cabin catalog'
            for orientation in range(4):
                asset=topdown_cabin_asset_path(style_id,orientation)
                assert asset is not None,(style_id,orientation,'missing directional cabin')
                homestead_paths.add(asset.resolve())
        doors=[];homesteads=[]
        for path in sorted((root/'assets/sprites/buildings').rglob('*.png')):
            resolved=path.resolve()
            if resolved in facade_paths:continue
            source=pg.image.load(str(path)).convert_alpha()
            if resolved in homestead_paths:
                assert source.get_width()>0 and source.get_height()>0,str(path)+' has invalid dimensions'
                assert pg.mask.from_surface(source,16).count()>0,str(path)+' has no visible cabin'
                homesteads.append(str(path.relative_to(root)))
                continue
            assert path.stem.startswith('door_'),str(path)+' is an unaudited building asset'
            assert source.get_bounding_rect(16).width>0,str(path)+' has no visible door'
            for size in (16,28,56):
                fitted=pg.transform.smoothscale(source,(size,max(3,size*2)))
                assert pg.mask.from_surface(fitted,16).count()>0,str(path)+' has no selectable pixels'
            doors.append(str(path.relative_to(root)))
        assert len(homesteads)==len(homestead_paths),(len(homesteads),len(homestead_paths))
        review_screen=term.screen
        audit_screen=pg.Surface(review_screen.get_size())
        for index,relative in enumerate(paths):
            term.screen=audit_screen
            path=root/relative
            assert path.is_file(),relative
            assert path.stem in _anchor_catalog()['assets'],relative+' has no authored door anchor'
            full=tuple((x,y) for y in range(6) for x in range(6))
            shapes={'rectangle':full,
                    'l_house':tuple(p for p in full if not(p[0]>=4 and p[1]<2)),
                    'courtyard':tuple(p for p in full if p not in {(2,2),(2,3),(3,2),(3,3)})}
            for shape,cells in shapes.items():
                base=BuildingShell('audit:'+path.stem,'audit','residence','core:house',cells,(2,5),
                                   'door:'+path.stem,0,shape,(0,0,5,5))
                known={pos_key(x,y,0) for x,y in cells}
                for size in (16,28,56):
                    for entrance in ((2,5),(2,0),(0,3),(5,3)):
                        shell=replace(base,entrance=entrance)
                        used=pg.Rect(10,10,800,600);hits=[]
                        with patch('worldseed.ui.exterior_view._art_ref',return_value=(path.stem,path)):
                            draw_shells(term,(shell,),used,0,0,size,known,known,hit_regions=hits)
                        body=next(h for h in hits if h['kind']=='body')
                        door=next(h for h in hits if h['kind']=='door')
                        assert door['target']==entrance,(relative,shape,entrance)
                        assert body['rect'].contains(door['rect']),(relative,'door outside footprint bounds')
                        ctx={'used':used,'shell_hit_regions':hits}
                        assert shell_at_pointer(ctx,door['rect'].center)==(shell,'door'),relative
                        mask=body['mask']
                        for x,y in set(full)-set(cells):
                            for py in range(y*size,(y+1)*size):
                                assert all(not mask.get_at((px,py)) for px in range(x*size,(x+1)*size)),(relative,shape,'painted cutout')
                            assert shell_at_pointer(ctx,(used.x+x*size+size//2,used.y+y*size+size//2)) is None
                        assert mask.count()>size*size,(relative,'empty facade')
                        cases+=1
            # Real renderer contact sheets, including one irregular example per page.
            term.screen=review_screen
            if index%12==0:term.screen.fill((31,44,34))
            column,row=index%4,(index%12)//4
            used=pg.Rect(column*320+24,row*300+35,280,245)
            shell=replace(base,footprint=full,building_form='rectangle',entrance=(2,5))
            if index%12==0:shell=replace(shell,footprint=shapes['l_house'],building_form='l_house')
            known={pos_key(x,y,0) for x,y in shell.footprint}
            hits=[]
            with patch('worldseed.ui.exterior_view._art_ref',return_value=(path.stem,path)):
                draw_shells(term,(shell,),used,0,0,36,known,known,hit_regions=hits)
            for x,y in shell.footprint:pg.draw.rect(term.screen,(82,148,115),(used.x+x*36,used.y+y*36,36,36),1)
            door=next(h for h in hits if h['kind']=='door')
            pg.draw.rect(term.screen,(247,200,90),door['rect'],1)
            term.screen.blit(term.small_font.render(path.stem,True,(235,223,190)),(used.x,used.y+222))
            report.append({'asset':relative,'cases':36})
            if index%12==11 or index==len(paths)-1:
                target=output/f'facades-{index//12+1}.png';pg.image.save(term.screen,str(target))
        result={'assets':len(paths),'door_assets':doors,'homestead_assets':homesteads,'geometry_cases':cases,'rows':report}
        (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'assets':len(paths),'door_assets':len(doors),'homestead_assets':len(homesteads),'geometry_cases':cases,'output':str(output)}))
    finally:term.restore()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    audit(parser.parse_args().output)
