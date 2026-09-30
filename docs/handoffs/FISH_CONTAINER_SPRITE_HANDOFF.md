# Fish and natural container sprite refresh

- Replaced the existing 12 fish item PNGs with generated, species-specific transparent illustrations. Item visual paths remain derived from `items.json`; no simulation or save format changes.
- Replaced three natural container PNGs used by both resource and structure entries. Rebuilt `natural_container_variants.png` as five 128 × 128 frames for each of three existing atlas rows. The world renderer still selects stable variants using the current `resource_rendering` metadata.
- Inspected the fish and container contact sheet and atlas. Validation: `python -m unittest tests.test_fish_and_container_sprites` and PNG alpha/dimensions checks. Local source snapshot lacks various unrelated preexisting binary assets, so the complete visual coverage suite cannot be run here.
