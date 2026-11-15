"""Runs inside Blender: re-import each exported FBX and dump what the Model Editor will see."""
import json
import struct
import sys

import bpy


def unit_scale_factor(path):
    """Read UnitScaleFactor straight from the binary FBX (100 = metres), since a
    Blender->Blender round trip would hide a unit mix-up."""
    data = open(path, "rb").read()
    i = data.find(b"UnitScaleFactor")
    if i < 0:
        return None
    j = data.find(b"D", i + len("UnitScaleFactor"))  # property value is typed 'D' (double)
    # Skip the "double"/"Number"/"" type strings: find the first 'D' followed by a plausible double.
    while j >= 0:
        v = struct.unpack("<d", data[j + 1:j + 9])[0]
        if 1e-6 < v < 1e6:
            return v
        j = data.find(b"D", j + 1)
    return None


def relative_filenames(raw):
    """Blender always writes the absolute path into FileName; path_mode=STRIP only
    affects RelativeFilename, which is what moved files are resolved by."""
    names, i, tag = [], 0, b"RelativeFilenameS"
    while (i := raw.find(tag, i)) >= 0:
        n = struct.unpack("<I", raw[i + len(tag):i + len(tag) + 4])[0]
        names.append(raw[i + len(tag) + 4:i + len(tag) + 4 + n].decode("utf-8", "replace"))
        i += 1
    return names


out = {}
for path in sys.argv[sys.argv.index("--") + 1:]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    objs = list(bpy.context.scene.objects)
    meshes = [o for o in objs if o.type == "MESH"]
    raw = open(path, "rb").read()
    verts = [v.co for o in meshes for v in o.data.vertices]
    out[path] = {
        "names": sorted(o.name for o in objs),
        "types": sorted({o.type for o in objs}),
        "mesh_names": sorted({o.data.name for o in meshes}),
        "scale": [round(v, 3) for v in meshes[0].scale] if meshes else None,
        "raw_extent": [round(max(c[k] for c in verts) - min(c[k] for c in verts), 3) for k in range(3)] if verts else None,
        "unit_scale_factor": unit_scale_factor(path),
        "materials": sorted({s.material.name for o in meshes for s in o.material_slots if s.material}),
        "has_uv": bool(meshes) and all(len(o.data.uv_layers) > 0 for o in meshes),
        "relative_filenames": relative_filenames(raw),
    }
print("[check_fbx] " + json.dumps(out))
