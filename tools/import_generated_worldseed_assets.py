from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps, ImageFilter, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FOREST_SHEET = ROOT / 'artifacts' / 'source-art' / 'top_down_forest_asset_sprite_sheet.png'
LOOT_SHEET = ROOT / 'artifacts' / 'source-art' / 'hand_painted_rpg_loot_sprite_sheet.png'

# Hand-tuned crop boxes from the generated prompt sheets.
FOREST_BOXES = {
    'oak_tree': (0, 20, 370, 520),
    'pine_tree': (350, 20, 790, 540),
    'birch_tree': (730, 20, 1120, 530),
    'sapling_leaf': (0, 480, 240, 770),
    'berry_bush': (240, 480, 560, 800),
    'green_bush': (560, 500, 860, 790),
    'cattail': (850, 470, 1150, 800),
    'grass_tuft': (1130, 500, 1438, 800),
    'fern': (0, 730, 250, 1080),
    'flowers': (250, 760, 560, 1045),
    'white_herb': (560, 760, 860, 1045),
    'mushrooms': (830, 760, 1140, 1045),
    'thorny_bush': (935, 760, 1220, 1080),
    'leaf_litter': (1210, 830, 1448, 1045),
}

LOOT_BOXES = {
    'single_branch': (20, 40, 290, 330),
    'bundle_sticks': (280, 40, 580, 330),
    'forked_branch': (570, 40, 880, 340),
    'log': (875, 40, 1145, 340),
    'firewood': (1140, 40, 1448, 340),
    'stone': (10, 345, 290, 585),
    'stone_flake': (300, 340, 540, 590),
    'clay_lump': (560, 350, 840, 590),
    'ore_rock': (840, 350, 1135, 590),
    'fiber': (1130, 330, 1448, 595),
    'herb_bundle': (5, 560, 280, 860),
    'berries': (275, 585, 560, 855),
    'mushroom_loot': (555, 575, 860, 855),
    'bone': (845, 585, 1145, 875),
    'feathers': (1130, 560, 1448, 875),
    'hide': (250, 825, 630, 1086),
    'seeds': (780, 860, 1140, 1086),
}


def trim_alpha(img: Image.Image) -> Image.Image:
    img = img.convert('RGBA')
    alpha = img.getchannel('A')
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img


def crop_component(sheet: Image.Image, box) -> Image.Image:
    return trim_alpha(sheet.crop(box))


def tint(img: Image.Image, color=(255, 255, 255), amount=0.2) -> Image.Image:
    """Tint visible pixels while preserving a completely transparent background."""
    img = img.convert('RGBA')
    alpha = img.getchannel('A')
    rgb = img.convert('RGB')
    solid = Image.new('RGB', img.size, color)
    mixed = Image.blend(rgb, solid, max(0.0, min(1.0, amount))).convert('RGBA')
    mixed.putalpha(alpha)
    return mixed


def add_berries(img: Image.Image, berry_color=(64, 110, 200), seed=0) -> Image.Image:
    img = img.convert('RGBA')
    draw = ImageDraw.Draw(img)
    w, h = img.size
    points = [
        (int(w * 0.35), int(h * 0.25)), (int(w * 0.52), int(h * 0.32)),
        (int(w * 0.62), int(h * 0.52)), (int(w * 0.42), int(h * 0.58)),
        (int(w * 0.70), int(h * 0.42)), (int(w * 0.28), int(h * 0.48)),
    ]
    for x, y in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=berry_color + (220,), outline=(255, 255, 255, 90))
    return img


def add_markers(img: Image.Image, color=(240, 220, 110), points=None, radius=4) -> Image.Image:
    img = img.convert('RGBA')
    draw = ImageDraw.Draw(img)
    w, h = img.size
    points = points or [(0.36,0.30),(0.55,0.26),(0.66,0.48),(0.43,0.57),(0.28,0.50)]
    for fx, fy in points:
        x, y = int(w * fx), int(h * fy)
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color + (225,))
    return img


def brighten(img: Image.Image, factor=1.06) -> Image.Image:
    return ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.05)).enhance(factor)


def prepare_on_canvas(img: Image.Image, canvas_size=(96, 96), inner_max=(86, 86), align='bottom') -> Image.Image:
    img = trim_alpha(img)
    img.thumbnail(inner_max, Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', canvas_size, (0, 0, 0, 0))
    x = (canvas.width - img.width) // 2
    if align == 'bottom':
        y = canvas.height - img.height - 2
    else:
        y = (canvas.height - img.height) // 2
    canvas.alpha_composite(img, (x, max(0, y)))
    return canvas


def save_asset(img: Image.Image, rel_path: str, canvas=(96, 96), inner=(86, 86), align='bottom'):
    target = ROOT / 'worldseed' / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    out = prepare_on_canvas(brighten(img), canvas, inner, align)
    out.save(target, optimize=True)
    return target


def main():
    forest = Image.open(FOREST_SHEET).convert('RGBA')
    loot = Image.open(LOOT_SHEET).convert('RGBA')

    f = {name: crop_component(forest, box) for name, box in FOREST_BOXES.items()}
    l = {name: crop_component(loot, box) for name, box in LOOT_BOXES.items()}

    changed = []

    # Resources / world objects
    changed.append(save_asset(f['oak_tree'], 'assets/sprites/resources/oak_tree.png', canvas=(104, 112), inner=(98, 104)))
    changed.append(save_asset(f['pine_tree'], 'assets/sprites/resources/pine_tree.png', canvas=(104, 112), inner=(98, 104)))
    changed.append(save_asset(f['birch_tree'], 'assets/sprites/resources/birch_tree.png', canvas=(104, 112), inner=(98, 104)))
    willow_src = f['oak_tree']
    willow = willow_src.resize((max(1, int(willow_src.width * 0.78)), max(1, int(willow_src.height * 1.12))), Image.Resampling.LANCZOS)
    willow = tint(willow, (70, 105, 45), 0.10)
    changed.append(save_asset(willow, 'assets/sprites/resources/willow_tree.png', canvas=(104, 112), inner=(98, 104)))
    changed.append(save_asset(f['berry_bush'], 'assets/sprites/resources/raspberry_cane.png', canvas=(96, 96), inner=(88, 88)))
    strawberry = add_markers(tint(f['green_bush'], (80, 120, 55), 0.08), (200, 45, 55), radius=5)
    changed.append(save_asset(strawberry, 'assets/sprites/resources/strawberry_patch.png', canvas=(92, 86), inner=(80, 74)))
    blueberry = add_berries(tint(f['green_bush'], (30, 40, 110), 0.05), (70, 110, 210))
    changed.append(save_asset(blueberry, 'assets/sprites/resources/blueberry_bush.png', canvas=(96, 96), inner=(88, 88)))
    changed.append(save_asset(f['cattail'], 'assets/sprites/resources/cattail_bed.png', canvas=(96, 104), inner=(86, 96)))
    changed.append(save_asset(f['grass_tuft'], 'assets/sprites/resources/reed_bed.png', canvas=(96, 104), inner=(86, 96)))
    yarrow_patch = tint(f['white_herb'], (220, 235, 185), 0.08)
    changed.append(save_asset(yarrow_patch, 'assets/sprites/resources/yarrow_patch.png', canvas=(92, 84), inner=(82, 74)))
    changed.append(save_asset(f['sapling_leaf'], 'assets/sprites/resources/plantain_patch.png', canvas=(88, 84), inner=(76, 72)))
    nettle_patch = tint(f['thorny_bush'], (45, 95, 45), 0.14)
    changed.append(save_asset(nettle_patch, 'assets/sprites/resources/nettle_patch.png', canvas=(92, 90), inner=(82, 80)))
    dandelion_patch = tint(f['flowers'], (240, 200, 55), 0.22)
    changed.append(save_asset(dandelion_patch, 'assets/sprites/resources/dandelion_patch.png', canvas=(92, 84), inner=(82, 74)))
    carrot_patch = add_markers(tint(f['fern'], (120, 150, 75), 0.08), (235, 235, 210), radius=3)
    changed.append(save_asset(carrot_patch, 'assets/sprites/resources/wild_carrot_patch.png', canvas=(92, 84), inner=(82, 74)))
    onion_patch = add_markers(tint(f['sapling_leaf'], (90, 135, 105), 0.12), (220, 205, 235), radius=3)
    changed.append(save_asset(onion_patch, 'assets/sprites/resources/wild_onion_patch.png', canvas=(92, 84), inner=(82, 74)))
    grain_patch = tint(f['grass_tuft'], (205, 170, 65), 0.22)
    changed.append(save_asset(grain_patch, 'assets/sprites/resources/wild_grain_patch.png', canvas=(92, 84), inner=(82, 74)))
    changed.append(save_asset(tint(f['mushrooms'], (190, 145, 95), 0.08), 'assets/sprites/resources/bolete_patch.png', canvas=(92, 84), inner=(82, 74)))
    morel_patch = tint(ImageOps.mirror(f['mushrooms']), (110, 80, 55), 0.24)
    changed.append(save_asset(morel_patch, 'assets/sprites/resources/morel_patch.png', canvas=(86, 80), inner=(72, 68)))
    changed.append(save_asset(l['bundle_sticks'], 'assets/sprites/resources/fallen_branches.png', canvas=(96, 84), inner=(86, 74)))
    changed.append(save_asset(l['stone'], 'assets/sprites/resources/surface_boulder.png', canvas=(92, 90), inner=(82, 80)))
    changed.append(save_asset(l['stone_flake'], 'assets/sprites/resources/loose_stone.png', canvas=(88, 84), inner=(72, 72)))
    changed.append(save_asset(l['clay_lump'], 'assets/sprites/resources/clay_bank.png', canvas=(92, 84), inner=(82, 74)))

    # Items / ground loot
    item_map = {
        'assets/sprites/items/branch.png': l['single_branch'],
        'assets/sprites/items/brush.png': l['bundle_sticks'],
        'assets/sprites/items/wood.png': l['log'],
        'assets/sprites/items/bark.png': l['forked_branch'],
        'assets/sprites/items/stone.png': l['stone'],
        'assets/sprites/items/stone_flake.png': l['stone_flake'],
        'assets/sprites/items/clay.png': l['clay_lump'],
        'assets/sprites/items/iron_ore.png': l['ore_rock'],
        'assets/sprites/items/fiber.png': l['fiber'],
        'assets/sprites/items/cordage.png': l['fiber'],
        'assets/sprites/items/berries.png': l['berries'],
        'assets/sprites/items/raspberries.png': l['berries'],
        'assets/sprites/items/bolete.png': l['mushroom_loot'],
        'assets/sprites/items/morel.png': l['mushroom_loot'],
        'assets/sprites/items/bone.png': l['bone'],
        'assets/sprites/items/feather.png': l['feathers'],
        'assets/sprites/items/hide.png': l['hide'],
        'assets/sprites/items/rawhide.png': l['hide'],
        'assets/sprites/items/fresh_hide.png': l['hide'],
        'assets/sprites/items/scraped_hide.png': l['hide'],
        'assets/sprites/items/wild_grain.png': l['seeds'],
        'assets/sprites/items/yarrow.png': l['herb_bundle'],
        'assets/sprites/items/medical_herb.png': l['herb_bundle'],
        'assets/sprites/items/nettle.png': l['herb_bundle'],
        'assets/sprites/items/dandelion.png': l['herb_bundle'],
        'assets/sprites/items/plantain.png': f['sapling_leaf'],
        'assets/sprites/items/wild_onion.png': f['white_herb'],
    }
    # Distinguish look-alike foraged items with consistent silhouette + palette cues.
    item_map['assets/sprites/items/morel.png'] = tint(ImageOps.mirror(l['mushroom_loot']), (105, 78, 55), 0.25)
    item_map['assets/sprites/items/medical_herb.png'] = tint(l['herb_bundle'], (75, 135, 70), 0.14)
    item_map['assets/sprites/items/nettle.png'] = tint(l['herb_bundle'], (45, 95, 45), 0.24)
    item_map['assets/sprites/items/yarrow.png'] = tint(l['herb_bundle'], (210, 225, 175), 0.12)
    item_map['assets/sprites/items/dandelion.png'] = tint(l['herb_bundle'], (185, 160, 55), 0.16)
    for rel_path, img in item_map.items():
        changed.append(save_asset(img, rel_path, canvas=(80, 80), inner=(68, 68)))

    blueberries = tint(l['berries'], (25, 35, 120), 0.2)
    blueberries = ImageEnhance.Color(blueberries).enhance(0.85)
    changed.append(save_asset(blueberries, 'assets/sprites/items/blueberries.png', canvas=(80, 80), inner=(68, 68)))

    print('Updated assets:')
    for path in changed:
        print(path.relative_to(ROOT))


if __name__ == '__main__':
    main()
