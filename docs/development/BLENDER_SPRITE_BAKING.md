# Meshy models to staged WORLDSEED sprites

Meshy creates source geometry; Blender provides cleanup and a repeatable camera and
lighting recipe. This fits WORLDSEED's current sprite rendering without adding a
runtime mesh importer. Start with static props such as rocks, furniture and ruins.

1. Generate and download a model from Meshy as a self-contained GLB. Keep the
   original prompt, reference-image rights, service/model version, and license
   record with it. Meshy free-plan attribution requirements differ from paid plans.
2. Inspect geometry, textures, silhouette and orientation in Blender. Remove
   unintended objects, repair defects, and export a reviewed static GLB. Animated
   rigs and complex source scenes need a separate animation workflow.
3. Bake into a new staging directory with Blender 4.3+ installed:

```sh
blender --background --python-exit-code 1 --python tools/blender_bake_sprites.py -- --source scratch/props/ruin.glb --output scratch/bakes/ruin --views 8 --size 256 --license-note "Record actual source rights, plan and required attribution here"
```

The tool imports the source into an empty scene, normalizes its largest dimension
to one unit, and grounds its bounding-box center. Eight evenly spaced orthographic
views start at 45-degree azimuth and use fixed 35.26-degree elevation, CPU Cycles,
64 samples (adjustable with `--samples`), lighting and transparent RGBA
output. Every view records the ground anchor (50% across, 25% up from the bottom),
camera transform and PNG hash. The manifest also retains the source hash,
normalization, Blender version, render settings and supplied license note.

Output must be outside the checkout or under its `scratch/` folder, and the
directory must be empty. Run each revision into a new directory. Review quality
at WORLDSEED's actual display size, including alpha edges and ground contact.
Results remain `unreviewed`; a license note alone does not approve an asset.
After review, use the existing asset/catalog workflow to publish the selected
sprites with stable IDs. This command does not change gameplay, simulation,
existing sprites, or the item-icon importer.

The recipe normalizes each prop independently. Record a separate gameplay scale
when publishing differently sized objects. It does not guarantee identical pixels
across Blender versions or material changes, generate collision footprints, bake
animation, or automatically produce WORLDSEED's hand-painted style.

Sources: [Meshy image-to-3D API](https://docs.meshy.ai/en/api/image-to-3d),
[Meshy asset licensing](https://help.meshy.ai/en/articles/9992001-can-i-use-meshy-assets-commercially-license-copyright-explained),
[Blender rendering and authoring](https://www.blender.org/features/).
