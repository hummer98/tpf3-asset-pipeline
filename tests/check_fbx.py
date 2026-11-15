"""Runs inside Blender: re-import each exported FBX and dump what the Model Editor will see."""
import json
import sys

import bpy

out = {}
for path in sys.argv[sys.argv.index("--") + 1:]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    out[path] = {
        "objects": len(meshes),
        "dims": [round(v, 3) for v in meshes[0].dimensions] if meshes else None,
        "scale": [round(v, 3) for v in meshes[0].scale] if meshes else None,
        "materials": sorted({s.material.name for o in meshes for s in o.material_slots if s.material}),
        "has_uv": all(len(o.data.uv_layers) > 0 for o in meshes),
    }
print("[check_fbx] " + json.dumps(out))
