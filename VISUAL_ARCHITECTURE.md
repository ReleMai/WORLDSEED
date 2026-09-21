# WORLDSEED RC8 Visual Architecture

## Decision

WORLDSEED's primary window renderer is **pygame-ce**.  The ANSI terminal backend remains supported as a fallback/debug presentation.

The renderer is an adapter.  Simulation state, command handling, deterministic RNG, saves, world generation, AI, ecology and economy do not import pygame or sprite assets.

## Presentation boundary

```text
Simulation / LivingWorldState / ContentRegistry
                |
                v
        presentation.visuals
          stable visual IDs
                |
      +---------+---------+
      |                   |
 ANSI Terminal      pygame-ce Window
 glyph fallback     hybrid sprite map
```

`worldseed/presentation/visuals.py` owns the mapping from stable content IDs to image files. Missing art can degrade to glyphs, while `tools/audit_visuals.py` makes full coverage a release gate.

## RC8 hybrid renderer

The main local world is now drawn as layered sprites inside a normal resizable game window. Menus and reports remain terminal-like text panels inside that same window. This preserves WORLDSEED's information density while removing dependence on Windows Terminal / ANSI rendering for normal play.

Layer order in RC8:

1. ground terrain
2. fluid overlay
3. natural resource feature
4. crop growth stage
5. structure/furniture
6. ground item pile
7. carcass
8. fire
9. living creature
10. NPC
11. player
12. targeting/look cursor
13. UI chrome / status / log

Visual dimensions never define simulation footprint. A tree may visually overhang neighboring cells while mechanically occupying one world position.

## Input

Pygame receives actual keyboard and mouse events. WASD/arrow semantics remain unchanged. Right-click maps to Back/Escape and mouse wheel maps to page scrolling in terminal-style menus. The old terminal parser remains available under `--terminal`.

## Assets

Generated runtime assets live under `worldseed/assets/`:

- `visuals.json` — per-content visual manifest
- `atlas_index.json` — future atlas/batching metadata
- `sprites/items/`
- `sprites/terrain/`
- `sprites/resources/`
- `sprites/structures/`
- `sprites/crops/`
- `sprites/species/`
- `sprites/npc/`
- `atlases/`

The current sprite generator is deterministic. It is safe to replace individual generated PNGs with hand-authored art while preserving the same manifest path/ID.

## Sprite evolution plan

### RC8
- dedicated pygame-ce window
- hybrid map renderer
- complete sprite coverage
- animal/NPC variation
- atlas metadata
- ANSI fallback

### Next visual pass
- proper hover hit-testing and tooltips
- click-to-select/context actions
- animation timelines driven by simulation events
- equipment overlays on NPC/player sprites
- directional animal/NPC frames
- terrain edge/autotile masks
- animated water/fire/weather
- lighting and darkness map
- zoom presets

### Later
- procedural modular sprites for generated species
- body/hair/clothing/equipment composition for named characters
- structure material overlays
- sprite LOD for local/spatial/world views
- optional GPU-batched backend if profiling justifies it

## Performance rule

Presentation must remain observational. Opening, resizing, hovering or rendering must never realize world regions, roll RNG, advance time, mutate ecology, or alter saves.
