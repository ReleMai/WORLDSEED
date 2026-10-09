"""Reusable, masked pixel-art detail layers for version-two NPC portraits.

The composer supplies resolved catalog parts, palettes and facial geometry.
These helpers only paint their supplied surfaces: no world reads, random draws,
pygame initialization, mutable identity or external image dependencies.
"""
from __future__ import annotations


def _mix(first, second, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(first, second))


def _layer(pg, surface):
    return pg.Surface(surface.get_size(), pg.SRCALPHA)


def _masked_blit(pg, target, layer, mask):
    """Clip a translucent layer without altering the supplied reusable mask."""
    if hasattr(mask, "to_surface"):
        mask = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    layer.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    target.blit(layer, (0, 0))


def shade_planes(pg, face, *, spec, part, skin, geometry):
    """Paint complete v2 facial planes before clipping and facial features.

    The silhouette remains the composer's authority. Contrast changes the
    strength of the lighting, while each style changes the actual plane colors
    and geometry rather than applying an opaque filter over finished eyes.
    """
    d = pg.draw
    x, left, right = geometry["x"], geometry["left"], geometry["right"]
    top, chin, jaw = geometry["top"], geometry["chin"], geometry["jaw"]
    style = part["style"]
    strength = .40 + part.get("contrast", 15) / 60
    base = skin[1]
    lit = _mix(base, skin[0], strength)
    shade = _mix(base, skin[2], strength)
    deep = _mix(shade, skin[3], .45)
    if style == "warm":
        lit = _mix(lit, (247, 203, 138), .20)
        shade = _mix(shade, (104, 58, 53), .15)
    elif style == "cool":
        lit = _mix(lit, (192, 216, 225), .21)
        shade = _mix(shade, (47, 73, 90), .20)
    elif style == "dramatic":
        lit = _mix(base, skin[0], min(1, strength + .2))
        shade = _mix(skin[2], skin[3], min(.8, strength))
        deep = _mix(shade, (23, 29, 39), .16)
    face.fill(base)
    # Lit forehead, shaded temple and separate cheek/jaw volumes are shared
    # across heads of different widths. The composer masks their outer edges.
    d.polygon(face, shade, [(x + 3, top), (right + 3, top),
                           (right + 3, chin), (x + 3, chin),
                           (x + 6, 38), (x + 8, 31), (x + 6, 23)])
    d.polygon(face, lit, [(left + 3, top + 5), (x - 2, top + 2),
                         (x + 1, 21), (x - 4, 24), (left + 3, 25)])
    d.polygon(face, lit, [(left + 3, 30), (x - 6, 29),
                         (x - 4, 34), (x - 7, 37), (left + 4, 35)])
    d.polygon(face, shade, [(left - 1, 33), (left + 5, 36),
                           (x - 6, 40), (x - 5, chin), (left - 2, chin)])
    d.polygon(face, _mix(base, lit, .40), [(x - 3, 36), (x + 4, 36),
                                        (x + 5, 42), (x, chin - 2), (x - 5, 42)])
    d.polygon(face, deep, [(right - 1, 26), (right + 2, 24),
                          (right + 3, chin), (x + 6, chin), (right - 2, 35)])
    if style == "soft":
        d.polygon(face, _mix(base, lit, .30), [(left + 2, 26),
                                            (x - 3, 27), (x - 4, 32), (left + 3, 33)])
    elif style == "dramatic":
        d.polygon(face, shade, [(x + 1, top + 1), (right + 2, top + 1),
                               (right + 2, chin), (x + 2, chin),
                               (x + 3, 37), (x + 2, 30)])
        d.line(face, lit, (left + 2, 26), (left + 3, 33), 1)
    elif style == "sculpted":
        d.polygon(face, deep, [(left + 1, 34), (x - 6, 36),
                              (x - 5, 40), (x - jaw + 1, chin - 4)])
        d.polygon(face, _mix(lit, skin[0], .25), [(left + 4, 29),
                                               (x - 6, 29), (x - 4, 32), (left + 5, 33)])
        d.polygon(face, shade, [(x + 4, 29), (right - 2, 28),
                               (right - 3, 35), (x + 6, 37)])
        d.line(face, lit, (x - 3, chin - 3), (x + 2, chin - 3), 1)
    elif style == "weathered":
        # Small fixed-grid color breaks give worn skin without random noise.
        # Youth retain the lighting family without adult skin texture.
        if spec.age_stage != "youth":
            for side in (-1, 1):
                for dx, dy in ((0, 0), (2, 1), (-1, 3), (3, 4), (0, 5)):
                    px, py = x + side * 9 + dx, 31 + dy
                    color = _mix(base, shade if (dx + dy) % 2 else lit, .6)
                    d.rect(face, color, (px, py, 1, 1))
            for px in range(x - 6, x + 5, 2):
                d.rect(face, shade, (px, max(top + 7, 17), 1, 1))


def skin_overlays(pg, surface, mask, *, face_mask, neck_mask, spec, parts, palettes, geometry):
    """Paint clipped skin markings and age-appropriate tattoo components.

    Facial markings and facial tattoos use the face mask; neck tattoos use
    the neck mask. The final union mask also keeps every ink pixel on skin.
    Existing eyes, nose and lip centers are deliberately left visible.
    """
    d = pg.draw
    x, left, right = geometry["x"], geometry["left"], geometry["right"]
    ey, my, chin = geometry["ey"], geometry["my"], geometry["chin"]
    top, spacing = geometry["top"], geometry["spacing"]
    skin, ink = palettes["skin"], palettes["ink"]
    face_layer = _layer(pg, surface)
    neck_layer = _layer(pg, surface)
    composite = _layer(pg, surface)
    marking = parts["markings"]["style"]
    freckle = _mix(skin[1], skin[3], .60)
    scar = _mix(skin[1], (172, 103, 91), .28)
    scar_light = _mix(skin[1], skin[0], .78)
    cheek_y = ey + 6
    if marking in ("freckles", "dense_freckles"):
        spots = ((-2, 0), (0, 1), (2, 0), (1, 3), (-3, 2))
        if marking == "dense_freckles":
            spots += ((-4, 0), (3, 2), (0, 4), (-2, 4), (4, 4), (-4, 4))
        for side in (-1, 1):
            for dx, dy in spots:
                d.rect(face_layer, freckle, (x + side * 8 + dx, cheek_y + dy, 1, 1))
        if marking == "dense_freckles":
            for dx, dy in ((-2, 0), (1, 1), (0, -1)):
                d.rect(face_layer, freckle, (x + dx, ey + 4 + dy, 1, 1))
    elif marking == "mole":
        d.rect(face_layer, skin[3], (x - 8, my - 2, 2, 1))
        d.rect(face_layer, freckle, (x - 8, my - 1, 1, 1))
    elif marking == "beauty_marks":
        d.rect(face_layer, skin[3], (x + 7, my - 2, 1, 1))
        d.rect(face_layer, skin[3], (x - 9, ey + 6, 1, 1))
    elif marking == "scar_cheek":
        points = [(right - 5, ey + 4), (right - 6, ey + 7), (right - 8, ey + 10)]
        d.lines(face_layer, scar, False, points, 1)
        d.lines(face_layer, scar_light, False, [(px - 1, py) for px, py in points], 1)
        d.line(face_layer, scar, (right - 8, ey + 7), (right - 5, ey + 8), 1)
    elif marking == "scar_brow":
        bx = x - spacing - 1
        d.line(face_layer, scar, (bx, ey - 7), (bx + 2, ey - 3), 1)
        d.line(face_layer, scar_light, (bx - 1, ey - 7), (bx + 1, ey - 3), 1)
    elif marking == "scar_nose":
        d.line(face_layer, scar, (x - 3, ey + 3), (x + 3, ey + 5), 1)
        d.line(face_layer, scar_light, (x - 3, ey + 2), (x + 2, ey + 4), 1)
    elif marking == "dimples":
        half_mouth = parts["mouth"]["width"] // 2
        for side in (-1, 1):
            cx = x + side * (half_mouth + 2)
            d.line(face_layer, _mix(skin[1], skin[2], .72), (cx, my), (cx - side, my + 2), 1)
            d.rect(face_layer, scar_light, (cx + side, my + 1, 1, 1))
    elif marking == "birthmark":
        color = _mix(skin[1], (117, 62, 62), .34)
        d.polygon(face_layer, color, [(left + 3, ey + 3), (left + 7, ey + 4),
                                     (left + 8, ey + 7), (left + 6, ey + 10),
                                     (left + 3, ey + 8), (left + 2, ey + 5)])
    elif marking == "vitiligo":
        color = _mix(skin[1], (233, 215, 188), .65)
        d.polygon(face_layer, color, [(left + 3, ey + 4), (left + 6, ey + 5),
                                     (left + 7, ey + 8), (left + 5, ey + 11),
                                     (left + 2, ey + 10), (left + 2, ey + 7)])
        d.polygon(face_layer, color, [(x + 5, my + 3), (x + 8, my + 2),
                                     (x + 9, my + 4), (x + 6, chin - 2),
                                     (x + 4, chin - 3)])
    tattoo = parts["tattoo"]["style"] if spec.age_stage != "youth" else "none"
    ink_color = _mix(ink[1], skin[1], .18)
    ink_light = _mix(ink[0], skin[1], .20)
    if tattoo == "cheek_runes":
        for side in (-1, 1):
            cx = x + side * 9
            d.lines(face_layer, ink_color, False, [(cx, cheek_y), (cx, cheek_y + 5),
                                                  (cx + side * 3, cheek_y + 3)], 1)
            d.line(face_layer, ink_light, (cx - side * 2, cheek_y + 1),
                   (cx + side * 2, cheek_y + 3), 1)
    elif tattoo == "temple_spiral":
        cx, cy = right - 4, ey - 2
        d.lines(face_layer, ink_color, False, [(cx - 1, cy - 5), (cx + 2, cy - 5),
                                              (cx + 3, cy - 2), (cx + 2, cy + 1),
                                              (cx, cy + 1), (cx - 1, cy - 1),
                                              (cx + 1, cy - 2)], 1)
    elif tattoo == "brow_dots":
        for side in (-1, 1):
            for dx, dy in ((-2, 1), (0, 0), (2, 1)):
                d.rect(face_layer, ink_color, (x + side * spacing + dx, ey - 7 + dy, 1, 1))
        d.rect(face_layer, ink_light, (x, max(top + 5, ey - 9), 1, 2))
    elif tattoo == "chin_lines":
        for dx in (-3, 0, 3):
            d.line(face_layer, ink_color, (x + dx, my + 4), (x + dx, chin - 1), 1)
        d.line(face_layer, ink_light, (x - 4, chin - 3), (x + 4, chin - 3), 1)
    elif tattoo == "neck_bands":
        for yy in (49, 52):
            d.line(neck_layer, ink_color, (x - geometry["neck"] - 1, yy),
                   (x + geometry["neck"] + 1, yy), 1)
        d.rect(neck_layer, ink_light, (x - 1, 50, 3, 1))
    elif tattoo == "eye_arc":
        for side in (-1, 1):
            cx = x + side * spacing
            d.lines(face_layer, ink_color, False, [(cx - 3, ey + 4),
                                                  (cx, ey + 5), (cx + 3, ey + 4)], 1)
            d.line(face_layer, ink_light, (cx + side * 4, ey + 3),
                   (cx + side * 5, ey + 5), 1)
    elif tattoo == "cheek_stars":
        for side in (-1, 1):
            cx, cy = x + side * 9, cheek_y + 2
            d.line(face_layer, ink_color, (cx - 2, cy), (cx + 2, cy), 1)
            d.line(face_layer, ink_color, (cx, cy - 2), (cx, cy + 2), 1)
            d.rect(face_layer, ink_light, (cx - 1, cy - 1, 1, 1))
    elif tattoo == "face_lattice":
        for side in (-1, 1):
            cx, cy = x + side * 9, cheek_y
            d.lines(face_layer, ink_color, False, [(cx - 3, cy + 2), (cx, cy),
                                                  (cx + 3, cy + 2), (cx, cy + 4),
                                                  (cx - 3, cy + 2)], 1)
            d.lines(face_layer, ink_light, False, [(cx - 2, cy + 5), (cx, cy + 4),
                                                  (cx + 2, cy + 5), (cx, cy + 7),
                                                  (cx - 2, cy + 5)], 1)
    _masked_blit(pg, composite, face_layer, face_mask)
    _masked_blit(pg, composite, neck_layer, neck_mask)
    _masked_blit(pg, surface, composite, mask)


def cloth_overlay(pg, surface, cloth_mask, *, spec, parts, palettes, geometry):
    """Decorate the existing garment mask; neckline skin always stays clear."""
    d = pg.draw
    layer = _layer(pg, surface)
    x, shoulders = geometry["x"], geometry["shoulders"]
    cloth, metal = palettes["cloth"], palettes["metal"]
    light, dark = _mix(cloth[0], cloth[1], .15), _mix(cloth[2], cloth[1], .2)
    stitch = _mix(cloth[0], (216, 197, 149), .35)
    style = parts["cloth_detail"]["style"]
    if style == "plain":
        return
    if style == "stripes":
        for xx in range(x - shoulders + 2, x + shoulders, 5):
            d.line(layer, light, (xx, 48), (xx + 3, 63), 1)
            d.line(layer, dark, (xx + 1, 48), (xx + 4, 63), 1)
    elif style == "checks":
        for xx in range(x - shoulders + 2, x + shoulders, 5):
            d.line(layer, dark, (xx, 48), (xx, 63), 1)
        for yy in range(50, 64, 4):
            d.line(layer, light, (x - shoulders, yy), (x + shoulders, yy), 1)
    elif style == "embroidery":
        for side in (-1, 1):
            for yy in (54, 59):
                cx = x + side * (11 if yy == 54 else 14)
                d.lines(layer, stitch, False, [(cx - 2, yy), (cx, yy - 2),
                                               (cx + 2, yy), (cx, yy + 2), (cx - 2, yy)], 1)
                d.rect(layer, light, (cx, yy, 1, 1))
        d.lines(layer, stitch, False, [(x - 9, 51), (x - 5, 56),
                                       (x, 58), (x + 5, 56), (x + 9, 51)], 1)
    elif style == "diamond_trim":
        for cx in range(x - shoulders + 4, x + shoulders - 1, 5):
            d.lines(layer, stitch, True, [(cx - 2, 60), (cx, 58),
                                          (cx + 2, 60), (cx, 62)], 1)
        d.line(layer, dark, (x - shoulders, 57), (x + shoulders, 57), 1)
    elif style == "buttons":
        d.line(layer, dark, (x, 55), (x, 63), 1)
        for yy in (56, 60, 63):
            d.rect(layer, metal[2], (x - 1, yy - 1, 3, 2))
            d.rect(layer, metal[0], (x - 1, yy - 1, 1, 1))
    elif style == "lacing":
        d.line(layer, dark, (x - 3, 55), (x - 3, 63), 1)
        d.line(layer, dark, (x + 3, 55), (x + 3, 63), 1)
        for yy in (55, 58, 61):
            d.line(layer, stitch, (x - 3, yy), (x + 3, yy + 2), 1)
            d.line(layer, stitch, (x + 3, yy), (x - 3, yy + 2), 1)
    elif style == "patches":
        patch = _mix(cloth[1], cloth[2], .5)
        d.polygon(layer, patch, [(x - 18, 57), (x - 10, 56),
                                (x - 9, 62), (x - 17, 63)])
        d.lines(layer, stitch, True, [(x - 17, 58), (x - 11, 57),
                                      (x - 10, 61), (x - 16, 62)], 1)
        for yy in (58, 60, 62):
            d.rect(layer, light, (x - 17, yy, 2, 1))
    elif style == "brocade":
        for row, yy in enumerate(range(51, 64, 5)):
            for xx in range(x - shoulders + 4 + (row % 2) * 3, x + shoulders, 6):
                d.lines(layer, stitch, False, [(xx - 1, yy + 2), (xx - 2, yy),
                                               (xx, yy - 1), (xx + 2, yy),
                                               (xx + 1, yy + 2)], 1)
                d.rect(layer, dark, (xx, yy + 2, 1, 1))
    _masked_blit(pg, surface, layer, cloth_mask)


def accessory_overlay(pg, surface, *, spec, parts, palettes, geometry):
    """Add cosmetic jewelry and transparent-lens eyewear after front hair."""
    d = pg.draw
    x, hw = geometry["x"], geometry["hw"]
    ey, spacing, top = geometry["ey"], geometry["spacing"], geometry["top"]
    style = parts["accessory"]["style"]
    metal = palettes["metal"]
    light, mid, dark = metal
    ear = parts["ears"]
    ear_y = 26 - ear["lift"] + ear["height"] - 2
    if style == "ear_stud":
        for side in (-1, 1):
            ex = x + side * (hw + 1)
            d.rect(surface, dark, (ex - 1, ear_y - 1, 3, 3))
            d.rect(surface, light, (ex - 1, ear_y - 1, 2, 1))
            d.rect(surface, mid, (ex, ear_y, 1, 1))
    elif style in ("ear_hoop", "double_hoops"):
        for side in (-1, 1):
            ex = x + side * (hw + 1)
            d.ellipse(surface, dark, (ex - 2, ear_y - 1, 5, 7), 1)
            d.lines(surface, light, False, [(ex - 1, ear_y),
                                           (ex - 2, ear_y + 2), (ex - 1, ear_y + 4)], 1)
            d.line(surface, mid, (ex, ear_y + 5), (ex + 1, ear_y + 5), 1)
            if style == "double_hoops":
                d.ellipse(surface, mid, (ex + side * 3 - 1, ear_y - 2, 3, 5), 1)
                d.rect(surface, light, (ex + side * 3 - 1, ear_y - 1, 1, 1))
    elif style == "ear_cuff":
        ex, cy = x + hw + 1, 28 - ear["lift"]
        d.lines(surface, dark, False, [(ex - 1, cy), (ex + 2, cy),
                                      (ex + 2, cy + 3), (ex, cy + 3)], 2)
        d.line(surface, light, (ex, cy), (ex + 2, cy), 1)
        d.rect(surface, mid, (ex + 1, cy + 3, 1, 2))
    elif style in ("nose_stud", "septum"):
        nose = parts["nose"]
        bottom = ey + 1 + nose["length"]
        if style == "nose_stud":
            nx = x + nose["width"]
            d.rect(surface, dark, (nx, bottom - 1, 2, 2))
            d.rect(surface, light, (nx, bottom - 1, 1, 1))
        else:
            d.lines(surface, dark, False, [(x - 2, bottom + 1), (x - 2, bottom + 3),
                                          (x, bottom + 4), (x + 2, bottom + 3),
                                          (x + 2, bottom + 1)], 1)
            d.line(surface, light, (x - 1, bottom + 3), (x + 1, bottom + 3), 1)
    elif style in ("neck_beads", "pendant"):
        points = [(x - geometry["neck"], 50), (x - 4, 54),
                  (x, 56), (x + 4, 54), (x + geometry["neck"], 50)]
        d.lines(surface, dark, False, points, 1)
        if style == "neck_beads":
            for cx, cy in points:
                d.rect(surface, mid, (cx - 1, cy - 1, 3, 3))
                d.rect(surface, light, (cx - 1, cy - 1, 1, 1))
        else:
            d.lines(surface, mid, False, [(x - 4, 54), (x, 56), (x + 4, 54)], 1)
            d.polygon(surface, dark, [(x, 56), (x + 2, 59), (x, 62), (x - 2, 59)])
            d.polygon(surface, mid, [(x, 57), (x + 1, 59), (x, 61), (x - 1, 59)])
            d.rect(surface, light, (x - 1, 58, 1, 2))
    elif style == "hair_pin":
        hair_style = parts["hair"]["style"]
        if hair_style == "bald":
            return
        # Side placement stays on receding hair as well as complete caps.
        px, py = x + hw - 3, max(top + 6, 15)
        d.line(surface, dark, (px - 3, py), (px + 2, py - 3), 2)
        d.line(surface, light, (px - 3, py - 1), (px + 1, py - 3), 1)
        d.rect(surface, mid, (px - 3, py - 1, 2, 2))
    elif style in ("round_glasses", "square_glasses"):
        frame = _mix(dark, palettes["ink"][2], .45)
        lens_width = max(7, parts["eyes"]["width"] + 3)
        for side in (-1, 1):
            cx = x + side * spacing
            cy = ey + (spec.asymmetry if side > 0 else 0)
            rect = (cx - lens_width // 2, cy - 3, lens_width, 7)
            if style == "round_glasses":
                d.ellipse(surface, frame, rect, 1)
                d.line(surface, mid, (rect[0] + 2, cy - 3), (rect[0] + 4, cy - 3), 1)
            else:
                d.rect(surface, frame, rect, 1)
                d.line(surface, mid, (rect[0] + 1, cy - 3), (rect[0] + lens_width - 2, cy - 3), 1)
            d.line(surface, frame, (cx + side * (lens_width // 2), cy - 1),
                   (x + side * (hw + 1), cy - 2), 1)
        d.lines(surface, frame, False, [(x - spacing + lens_width // 2, ey),
                                       (x - 1, ey - 1), (x + 1, ey - 1),
                                       (x + spacing - lens_width // 2, ey)], 1)
