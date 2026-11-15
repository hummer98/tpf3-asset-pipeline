"""Build a TF3 asset inside Blender: run assets/<name>/model.py, export FBX per LOD,
save textures as TGA (Model Editor converts them to DDS), and render preview PNGs.

usage: tools/blender.sh tools/build_asset.py -- <asset_name> [--no-preview]

model.py must define build(lib) -> dict:
  {"lods": {0: [obj, ...], 1: [...]}, "textures": [(bpy_image, "<mat>_alb.tga"), ...]}
"""
import contextlib
import importlib.util
import json
import math
import re
import os
import shutil
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


def validate(name, result):
    lods = result.get("lods") or {}
    if 0 not in lods:
        raise SystemExit(f"{name}: LOD0 missing (Model Editor requires _lod0.fbx)")
    for lod, objs in lods.items():
        if not objs:
            raise SystemExit(f"{name}: LOD{lod} has no objects")
        for o in objs:
            # Model Editor derives the element name from the object name and adds
            # _lodN itself, so a suffix here would double it and differ per LOD.
            if re.search(r"_lod\d+$", o.name):
                raise SystemExit(f"{name}: object '{o.name}' must not end with _lodN")


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


@contextlib.contextmanager
def lod_names(objs, all_objs):
    """Every LOD shares element names (e.g. 'bench'), but Blender renames
    duplicates to 'bench.001'. Park the other LODs under temp names while
    exporting so this LOD's objects get the clean name in the FBX."""
    saved = {o: (o.name, o.data.name) for o in all_objs}
    for i, o in enumerate(all_objs):
        o.name = f"__lodtmp{i}"
        o.data.name = f"__lodtmp{i}"
    for o in objs:
        o.name = re.sub(r"\.\d{3}$", "", saved[o][0])
        # The Model Editor names .msh files after the mesh datablock, not the object
        # (otherwise they come out as Cube_lod0.msh / Cube.013_lod1.msh).
        o.data.name = o.name
    try:
        yield
    finally:
        for i, o in enumerate(all_objs):
            o.name = o.data.name = f"__lodtmp_restore{i}"
        for o, (n, dn) in saved.items():
            o.name, o.data.name = n, dn


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
    # The whole out/<name>/ folder gets dropped into the Model Editor, so stale
    # LODs/textures from earlier builds must not survive, and previews/report live
    # outside it in out/_preview/<name>/.
    base = os.path.dirname(out_dir)
    preview_dir = os.path.join(base, "_preview", name)
    tf3lib.reset_scene()
    result = load_model(name).build(tf3lib)
    # Validate before wiping, so a broken model.py keeps the last good build.
    validate(name, result)
    for d in (out_dir, preview_dir):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    report = {"asset": name, "lods": {}, "textures": [], "previews": []}

    for img, fname in result.get("textures", []):
        path = os.path.join(out_dir, fname)
        img.filepath_raw = path
        img.file_format = "TARGA_RAW"  # RLE support in the DDS converter is unverified
        img.save()
        report["textures"].append(fname)

    all_lod_objs = [o for objs in result["lods"].values() for o in objs]
    for lod, objs in sorted(result["lods"].items()):
        path = os.path.join(out_dir, f"{name}_lod{lod}.fbx")
        with lod_names(objs, all_lod_objs):
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
        report["previews"] = [os.path.basename(p) for p in render_previews(lod0, preview_dir, name)]

    with open(os.path.join(preview_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("[build_asset] " + json.dumps(report, ensure_ascii=False))


main()
