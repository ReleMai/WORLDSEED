# Dev46 interior art

Generated with the built-in ImageGen tool; final runtime files are stored here.
Floor and wall are surface textures; the bed retains generated RGBA transparency.
Other furniture uses its existing authored settlement-piece art.

## Final prompts

- `cottage_floor.png`: square seamless overhead texture of worn medieval cottage
  oak floorboards, warm muted brown, hand-painted survival RPG detail; flat
  orthographic full frame; varied board lengths/scuffs; no furniture, walls,
  object shadows, grid, border, text or watermark.
- `cottage_wall.png`: square seamless medieval limewashed plaster with restrained
  timber grain/seams, muted warm pale gray, weathered hand-painted survival RPG
  surface; flat overhead, tileable edges; no furniture, cast shadows, perspective,
  grid, border, text or watermark.
- `cottage_bed.png`: single rustic medieval wooden bed strictly overhead, head
  at top, cream linen pillow, muted green wool blanket; whole frame centered,
  hand-painted wood; no floor/room/props/perspective/text/watermark. Final edit:
  remove all dark backdrop/glow/shadow outside the frame; exact bed cutout with
  transparent alpha, preserving materials, pillow, blanket and proportions.

Source outputs remain in the generation service's generated_images directory;
the game references only these checked-in files through stable visual IDs.
