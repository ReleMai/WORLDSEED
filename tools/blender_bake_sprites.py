"""Bake a reviewed static GLB into staged sprites; run with Blender --background.

This authoring tool never imports WORLDSEED or promotes output into runtime assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORTHO_SCALE = 2.2
FOOT_ANCHOR = (0.5, 0.25)  # Normalized image coordinates, origin at bottom left.


def normalization(points):
    """Uniformly fit world bounds to one unit and put ground-center at origin."""
    points = [tuple(point) for point in points]
    if not points or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("model bounds must contain finite XYZ points")
    lower = tuple(min(p[i] for p in points) for i in range(3))
    upper = tuple(max(p[i] for p in points) for i in range(3))
    extent = max(upper[i] - lower[i] for i in range(3))
    if extent <= 1e-8:
        raise ValueError("model has zero-size bounds")
    pivot = ((lower[0] + upper[0]) / 2, (lower[1] + upper[1]) / 2, lower[2])
    return 1 / extent, tuple(-v / extent for v in pivot)


def validate_paths(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.suffix.lower() != ".glb" or not source.is_file():
        raise ValueError("source must be an existing local .glb file")
    # Runtime assets and all other tracked project directories are out of bounds.
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / "scratch"):
        raise ValueError("output inside the repository must be under scratch/")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output must be a new or empty staging directory")
    return source, output


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--views", type=int, choices=(1, 4, 8, 16), default=8)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--license-note", required=True, help="Source rights/attribution record; not an approval")
    args = parser.parse_args(argv)
    if not 64 <= args.size <= 2048:
        parser.error("--size must be between 64 and 2048")
    if not 1 <= args.samples <= 256:
        parser.error("--samples must be between 1 and 256")
    if not args.license_note.strip():
        parser.error("--license-note cannot be empty")
    return args


def bake(args):
    source, output = validate_paths(args.source, args.output)
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    scene = bpy.context.scene
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("source contains no mesh objects")
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    scale, translation = normalization(points)
    controller = bpy.data.objects.new("WORLDSEED_normalization", None)
    scene.collection.objects.link(controller)
    for obj in list(scene.objects):
        if obj != controller and obj.parent is None:
            obj.parent = controller
    controller.scale = (scale,) * 3
    controller.location = translation
    # Source lighting/cameras must not affect a common bake recipe.
    for obj in list(scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.seed = 0
    scene.cycles.use_denoising = False  # Some headless builds omit OpenImageDenoise.
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.world = bpy.data.worlds.new("WORLDSEED_world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25
    for name, position, power, size in (
        ("key", (3, -4, 5), 400, 4), ("fill", (-3, -1, 3), 150, 5)
    ):
        light = bpy.data.lights.new(name, "AREA")
        light.energy, light.shape, light.size = power, "DISK", size
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = position
        obj.rotation_euler = (-obj.location).to_track_quat("-Z", "Y").to_euler()

    camera_data = bpy.data.cameras.new("WORLDSEED_camera")
    camera_data.type, camera_data.ortho_scale = "ORTHO", ORTHO_SCALE
    camera = bpy.data.objects.new("WORLDSEED_camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    output.mkdir(parents=True, exist_ok=True)
    records = []
    elevation = math.radians(35.26438968)
    for index in range(args.views):
        yaw_degrees = 45 + 360 * index / args.views
        yaw = math.radians(yaw_degrees)
        camera.location = Vector((5 * math.cos(elevation) * math.sin(yaw),
                                  -5 * math.cos(elevation) * math.cos(yaw),
                                  5 * math.sin(elevation)))
        camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
        # Translate along camera-up to give every asset the same ground anchor.
        camera.location += camera.rotation_euler.to_matrix() @ Vector((0, ORTHO_SCALE * 0.25, 0))
        bpy.context.view_layer.update()
        foot = world_to_camera_view(scene, camera, Vector((0, 0, 0)))
        filename = f"view_{index:02d}.png"
        scene.render.filepath = str(output / filename)
        bpy.ops.render.render(write_still=True)
        records.append({"file": filename, "yaw_degrees": yaw_degrees,
                        "camera_location": list(camera.location),
                        "camera_rotation_radians": list(camera.rotation_euler),
                        "foot_anchor_bottom_left": [foot.x, foot.y],
                        "sha256": hashlib.sha256((output / filename).read_bytes()).hexdigest()})
    manifest = {"schema_version": 1, "status": "unreviewed", "source_file": source.name,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "license_note": args.license_note, "blender_version": bpy.app.version_string,
                "normalization": {"scale": scale, "translation": translation},
                "recipe": {"engine": "CYCLES", "device": "CPU", "samples": args.samples, "seed": 0,
                           "denoising": False,
                           "size": args.size, "ortho_scale": ORTHO_SCALE,
                           "elevation_degrees": math.degrees(elevation),
                           "foot_anchor_bottom_left": list(FOOT_ANCHOR),
                           "lighting": "key:400W disk4 at(3,-4,5); fill:150W disk5 at(-3,-1,3); world:0.25",
                           "view_transform": "Standard", "look": "None"}, "views": records}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Staged {len(records)} views in {output}; visual review and runtime import are still required.")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        bake(parse_args(argv))
    except (ValueError, OSError, ImportError) as error:
        raise SystemExit(str(error)) from None
