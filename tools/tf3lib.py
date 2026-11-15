"""Small helpers shared by asset scripts (runs inside Blender)."""
import bpy


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def box(name, size, location, material=None):
    """Axis-aligned box; size/location in metres, location = box centre."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    # Cube projection keeps texel density uniform across boxes of different sizes.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cube_project(cube_size=1.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    if material:
        o.data.materials.append(material)
    return o


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    return o


def material(name, image=None, color=(0.8, 0.8, 0.8, 1)):
    """Material whose name drives the Model Editor's texture lookup (<name>_alb)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    if image is not None:
        tex = m.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = image
        m.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def image(name, size, fill, alpha=False):
    """Procedural image; fill(x, y) -> (r, g, b, a) in 0..1.
    Opaque by default: a 32-bit TGA makes the Model Editor compress albedo to
    BC3/DXT5 and warn that opaque textures should be BC1/DXT1."""
    w, h = size
    img = bpy.data.images.new(name, w, h, alpha=alpha)
    px = [0.0] * (w * h * 4)
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            px[i:i + 4] = fill(x, y)
    img.pixels[:] = px
    return img
