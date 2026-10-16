# WORLDSEED — Interior visual pass 2 (2026-10-16)

## Scope and art direction

This pass builds on the **current main repository** (Dev57+ furnishing, Dev52 interiors, and Dev50 settlement storage), not the historical RC13 prototype. Keep the top-down, physically grounded look of the existing authored art. The visual review sheets are generated directly from the *actual game sprites*, organized as four separate sheets:

1. Floors, rugs and circulation
2. Interior walls, surfaces and stairs
3. Furniture, workstations and lighting
4. Real containers and storage fittings

Run `python tools/generate_interior_style_sheets.py --output docs/art/interior_pass2_sheets` to regenerate these sheets. Windows GPU builds also publish a separate `WORLDSEED-Interior-Art-Sheets-<SHA>` review artifact.

## Runtime changes

- **Lighting:** Portable, deterministic 64×64 warm radial glow art is emitted only for physically installed lamps and hearths **inside live player LOS**. Color/intensity are presentation only. Existing authoritative indoor light remains the gameplay source for detection and illumination; wall occlusion and remembered sight continue to control visibility.
- **Soft shadows:** Contact shadows for solid furnishings become feathered and project gently away from the nearest *visible* installed light, instead of using a fixed ellipse direction. Dynamic shadow textures are small and reused. No hidden lamp coordinates leak through the detached scene.
- **Performance:** Indoor and container PNGs remain intact on disk, but GPU upload copies are limited to 320 px on the longest axis, retaining each canvas aspect ratio. Reduces the resident RGBA size of a 2048×1024 texture from 8 MiB to about 200 KiB, before GPU mip overhead (no mipmaps created here). Outdoor trees/terrain are unaffected. All current sprites, floor paint and memory masks retain the existing UV alignment.
- **Scale, placement and hitboxes:** The existing `InteriorFurniture(x,y,w,h)` and authored `interior_furnishing.json` dimension catalog remain authoritative. Sprite fitting and shadow centering use the true physical footprint, NOT transparent texture padding; hit tests, aisle margins, furniture `source_uid` and room slot checks remain untouched.
- **Containers:** No new storage class, loot or permissions have been fabricated. `container_profiles.json` still selects eleven real sources and their stock tables; `property_storage` and `interior_storage.bind_storage` retain ownership, locks, inventories and conservation behavior. The review gallery shows the distinct **already-integrated** chest, pantry, wardrobe, coffer, cabinet and hamper artwork.

## QA and caveats

Run `tests.test_gpu_interior_art_pass2` with the existing `tests.test_gpu_interiors`, `tests.test_gpu_interior_smoothing`, `tests.test_dev50_interior_storage`, `tests.test_dev53_furnishing_slots`, and `tests.test_interior_materials`. The dedicated pass-2 tests verify private lights cannot produce glow, shadows depend only on admitted light, and GPU thumbnails are bounded. No saved-game migration or inventory changes occur.

This is a **render and asset-art direction pass**, not a new generation of binary furniture artwork or a replacement for live playtest validation. The generated review sheets contain the already-authored sprites as displayed by the current game and can be compared with the separate exploratory concept sheets provided in chat. Windows 3D/driver FPS must still be measured while walking inside a furnished building.
