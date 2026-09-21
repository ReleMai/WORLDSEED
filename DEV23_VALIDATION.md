# RC14 Dev23 — WORLDGEN v8 Phase-1 validation

Scope: non-authoritative geological landform prototype only.

- Added a standalone deterministic landform sampler with fixed namespaces and integer generation math.
- Prototype fields: continentalness, tectonic uplift, mountain-chain strength, basin strength, plateau strength, roughness, elevation and province.
- WORLDGEN_VERSION remains 7. No save schema, hydrology version, terrain IDs, spawn rules, resource rules or live v7 terrain path changed.
- The WorldGenerator integration is read-only through prototype_landform_at(); sample_fields()/terrain_at() remain authoritative for v1-v7.
- Draft module, audit utility and test module passed Python syntax compilation in the development environment.
- Standalone deterministic smoke used the repository's exact hash protocol over four seeds. Repeated coordinate samples matched exactly; all sampled field values stayed within 0..65535.
- A 49x49 sample window (2,401 samples/seed) across four smoke seeds produced all six prototype province classes on each seed. Observed elevation extrema across those windows ranged from 8,424 to 64,106.
- Negative-coordinate samples were included in deterministic checks.
- Full repository unittest discovery was not available from the GitHub connector environment in this work session. A repository test module was added so the next executable checkout can run the integration gate directly.

Next executable validation command:

```bash
python -m unittest tests.test_worldgen_v8_landforms
python tools/audit_worldgen_v8_landforms.py --seed worldgen-v8-audit
```

Do not promote WORLDGEN_VERSION to 8 until the visual/debug exports for multiple golden seeds are reviewed and Phase-2 gates in WORLDGEN_V8_ROADMAP.md pass.
