"""Headless whole-shell QA projected from the real generated settlement plan."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
from pathlib import Path
import argparse
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_property_storage_casing import PropertyStorageCasingTests
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import draw_shells
from worldseed.ui.pygame_terminal import PygameTerminal


def catalog_gallery(term, registry):
    """Label source catalog images for QA; never alter a source sprite."""
    pg = term.pg
    groups = [('building_shells', sorted(term._visuals.manifest.get('building_shells',{})))]
    buildings = [(kind, key) for kind, keys in groups for key in keys]
    buildings += [('building_doors', key) for key in sorted(term._visuals.manifest.get('building_doors',{}))]
    furniture = [('interiors', piece.id) for piece in sorted(registry.settlement_pieces.values(),key=lambda piece:piece.id)
                 if piece.category == 'furniture' and piece.id.startswith('core:')]
    for name, entries in [('building-art',buildings),('furniture-art',furniture)]:
        if not entries or len(entries)>96:
            raise ValueError(f'{name} catalog must contain between 1 and 96 QA entries')
        cols, cell_w, cell_h = 6, 160, 180
        rows = (len(entries)+cols-1)//cols
        canvas = pg.Surface((cols*cell_w, rows*cell_h))
        canvas.fill((16,20,23))
        for index,(kind,key) in enumerate(entries):
            col,row = index%cols,index//cols
            image_rect = pg.Rect(col*cell_w+6,row*cell_h+8,cell_w-12,cell_h-44)
            for yy in range(image_rect.top,image_rect.bottom,16):
                for xx in range(image_rect.left,image_rect.right,16):
                    color=(42,47,50) if ((xx-image_rect.left)//16+(yy-image_rect.top)//16)%2 else (58,62,64)
                    pg.draw.rect(canvas,color,pg.Rect(xx,yy,16,16).clip(image_rect))
            path = term._visuals.resolve(term._visuals.ref(kind,key))
            if path is None or not path.is_file():
                raise FileNotFoundError(f'Missing {kind} artwork: {key}')
            sprite = term._load_sprite(path,image_rect.width-10,image_rect.height-10,smooth=True)
            if sprite is None:
                raise ValueError(f'Unreadable {kind} artwork: {key}')
            canvas.blit(sprite,sprite.get_rect(center=image_rect.center))
            label = key.removeprefix('core:').removesuffix('_piece').replace('_',' ').title()
            label = term._fit_ui_text(label,term.small_font,cell_w-12)
            text = term.small_font.render(label,True,term._theme['text'])
            canvas.blit(text,text.get_rect(center=(col*cell_w+cell_w//2,row*cell_h+cell_h-23)))
        output=Path(f'artifacts/dev47-{name}-gallery.png')
        pg.image.save(canvas,str(output))
        print(f'{output.resolve()} ({len(entries)} catalog sprites)')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-gallery',action='store_true',help='Also render labelled building/door and furniture source-art QA sheets.')
    args=parser.parse_args()
    PropertyStorageCasingTests.setUpClass()
    fixture = PropertyStorageCasingTests()
    base, security = fixture._security_fixture()
    state, town, physical, *_ = base
    skeleton = physical.skeleton_for(town.uid)
    house = next(s for s in physical.shells_in_bounds(-10000,-10000,10000,10000) if s.function == 'residence')
    before = state.to_dict()
    term = PygameTerminal(1280,832)
    term.enter()
    output = Path('artifacts/dev47-exterior-preview.png')
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        pg = term.pg
        ox,oy,ow,oh = term._draw_chrome('WORLDSEED // LOCAL')
        used = pg.Rect(ox,oy,ow,oh-58)
        size = 28
        left,top = house.bounds[0]-8, house.bounds[1]-7
        cols,rows = used.width//size+1, used.height//size+1
        right,bottom = left+cols-1,top+rows-1
        cells = {(c.x,c.y,0):c for c in physical.cells_in_bounds(left,top,right,bottom)}
        shells = physical.shells_in_bounds(left,top,right,bottom)
        shell_set = {(x,y,0) for shell in shells for x,y in shell.footprint}
        grass = term._load_terrain_sprite(term._visuals.resolve(term._visuals.ref('terrain','core:grass')),size)
        old_clip = term.screen.get_clip()
        term.screen.set_clip(used)
        for sy in range(rows):
            for sx in range(cols):
                rect = pg.Rect(used.x+sx*size,used.y+sy*size,size,size)
                if grass:term.screen.blit(grass,rect)
                else:pg.draw.rect(term.screen,(66,76,48),rect)
        for key,cell in cells.items():
            if key in shell_set or not cell.ground_piece_id:continue
            piece = fixture.registry.settlement_pieces.get(cell.ground_piece_id)
            bits = term._settlement_connection_bits(key,cell,cells,fixture.registry,ground=True)
            sprite = term._settlement_ground_surface(piece,size,bits)
            if sprite:term.screen.blit(sprite,(used.x+(cell.x-left)*size,used.y+(cell.y-top)*size))
        known = {pos_key(x,y,0) for y in range(top,bottom+1) for x in range(left,right+1)}
        draw_shells(term,shells,used,left,top,size,known,known)
        term.screen.set_clip(old_clip)
        label = 'Prepared settlement plan • whole roofed buildings • independent entrance doors • authoritative frontage paths'
        term.screen.blit(term.small_font.render(label,True,term._theme['text']),(ox+10,used.bottom+18))
        assert state.to_dict()==before,'Rendering mutated authoritative state'
        pg.image.save(term.screen,str(output))
        print(f'{output.resolve()}\n{len(shells)} prepared shells; observational projection passed')
        if args.catalog_gallery:
            catalog_gallery(term,fixture.registry)
    finally:
        term.restore()


if __name__=='__main__':main()
