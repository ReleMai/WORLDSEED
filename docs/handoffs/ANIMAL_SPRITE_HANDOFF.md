# Illustrated animal sprites

- Replaced the visual registry paths for all 21 authored animals with four transparent PNG variants per species. Cave crawlers and cave stalkers retain their monster art.
- Three generated sprite sheets cover woodland, upland, wetland, coastal and cave animals. The art was cropped into 160 × 136 transparent frames and isolated by connected silhouette to prevent neighboring sheet fragments. Facing and subtle coat variants add visual variety; deer, wolves and boars also use distinct generated illustrations.
- Gameplay and save data are unchanged. Species IDs and deterministic variant selection remain intact; existing sprite files are retained for compatibility.
- Validation: `python -m unittest tests.test_animal_sprites` and a visual contact sheet inspection. The full visual coverage suite needs the repository's other preexisting binary assets, which are absent from this session's local source snapshot.
