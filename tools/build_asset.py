"""Build a TF3 asset inside Blender: run assets/<name>/model.py, export FBX per LOD,
save textures as TGA (Model Editor converts them to DDS), and render preview PNGs.

usage: tools/blender.sh tools/build_asset.py -- <asset_name> [--no-preview]

model.py must define build(lib) -> dict:
  {"lods": {0: [obj, ...], 1: [...]}, "textures": [(bpy_image, "<mat>_alb.tga"), ...]}
"""
import importlib.util
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import tf3lib  # noqa: E402


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        raise SystemExit("asset name required")
    return argv[0], "--no-preview" not in argv


def load_model(name):
    path = os.path.join(ROOT, "assets", name, "model.py")
    spec = importlib.util.spec_from_file_location(f"asset_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tri_count(objs):
    deps = bpy.context.evaluated_depsgraph_get()
    n = 0
    for o in objs:
        if o.type != "MESH":
            continue
        m = o.evaluated_get(deps).to_mesh()
        m.calc_loop_triangles()
        n += len(m.loop_triangles)
        o.evaluated_get(deps).to_mesh_clear()
    return n


def export_lod(objs, path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    # Defaults (-Z forward, Y up) pair with the Model Editor's
    # "Use Blender Coordinate System" import option, which the TF3 wiki requires.
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH"},
        apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE",
        use_mesh_modifiers=True, path_mode="STRIP", embed_textures=False)


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def render_previews(objs, out_dir, name):
    scene = bpy.context.scene
    lo, hi = bounds(objs)
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 0.1)

    bpy.ops.mesh.primitive_plane_add(size=radius * 8, location=(center.x, center.y, lo.z))
    ground = bpy.context.active_object
    gm = bpy.data.materials.new("preview_ground")
    gm.diffuse_color = (0.35, 0.38, 0.33, 1)
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.35, 0.38, 0.33, 1)
    ground.data.materials.append(gm)

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.7, 0.85, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 50

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 800
    scene.render.resolution_y = 600
    scene.render.image_settings.file_format = "PNG"

    views = {"persp": (35, 30), "front": (0, 5), "side": (90, 5), "top": (0, 89)}
    written = []
    for view, (az, el) in views.items():
        d = radius * 3.2
        a, e = math.radians(az), math.radians(el)
        # Camera looks from -Y towards +Y at azimuth 0 ("front").
        cam.location = center + Vector((d * math.sin(a) * math.cos(e),
                                        -d * math.cos(a) * math.cos(e),
                                        d * math.sin(e)))
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        path = os.path.join(out_dir, f"{name}_preview_{view}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        written.append(path)
    return written


def main():
    name, preview = parse_args()
    # TF3_ASSETS_OUT lets tests build into a scratch dir without touching out/.
    out_dir = os.path.join(os.environ.get("TF3_ASSETS_OUT") or os.path.join(ROOT, "out"), name)
    os.makedirs(out_dir, exist_ok=True)
    tf3lib.reset_scene()

    result = load_model(name).build(tf3lib)
    report = {"asset": name, "lods": {}, "textures": [], "previews": []}

    for img, fname in result.get("textures", []):
        path = os.path.join(out_dir, fname)
        img.filepath_raw = path
        img.file_format = "TARGA"
        img.save()
        report["textures"].append(fname)

    for lod, objs in sorted(result["lods"].items()):
        path = os.path.join(out_dir, f"{name}_lod{lod}.fbx")
        export_lod(objs, path)
        lo, hi = bounds(objs)
        report["lods"][lod] = {"fbx": os.path.basename(path), "tris": tri_count(objs),
                               "size_m": [round(v, 3) for v in (hi - lo)]}

    if preview:
        lod0 = result["lods"][0]
        for lod, objs in result["lods"].items():
            if lod != 0:
                for o in objs:
                    o.hide_render = True
        report["previews"] = [os.path.basename(p) for p in render_previews(lod0, out_dir, name)]

    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("[build_asset] " + json.dumps(report, ensure_ascii=False))


main()
