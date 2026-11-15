#!/usr/bin/env python3
"""Pipeline test: build each asset headless into a temp dir, then verify outputs.
usage: python3 tests/run.py [asset ...]   (default: all assets)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = os.path.join(ROOT, "tools", "blender.sh")
fails = []
# Suffixes the Model Editor matches textures by (TF3 wiki, modding:tools:modeleditor).
MAP_SUFFIXES = ("_alb", "_albedo", "_albo", "_albedo_opacity", "_nrm", "_normal", "_mga",
                "_metal_gloss_ao", "_cdr", "_cblend_dirt_rust", "_cblend", "_uv1_ao", "_id",
                "_emissive_ID_lod1", "_e", "_op1", "_op2")
PREVIEW_VIEWS = ("persp", "front", "side", "top")


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def blender(script, *args, env=None):
    r = subprocess.run([BLENDER, script, "--", *args], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def tagged(log, tag):
    for line in log.splitlines():
        if line.startswith(tag + " "):
            return json.loads(line[len(tag) + 1:])
    return None


def test_asset(name, tmp):
    print(f"[{name}]")
    env = dict(os.environ, TF3_ASSETS_OUT=tmp)
    code, log = blender(os.path.join(ROOT, "tools", "build_asset.py"), name, env=env)
    check(code == 0, f"build exits 0 (got {code})")
    rep = tagged(log, "[build_asset]")
    check(rep is not None, "build report printed")
    if rep is None:
        print(log[-2000:])
        return
    d = os.path.join(tmp, name)
    check("0" in rep["lods"], "LOD0 present (Model Editor requires _lod0)")
    for lod, info in rep["lods"].items():
        check(info["fbx"] == f"{name}_lod{lod}.fbx", f"lod{lod} FBX naming {info['fbx']}")
        check(os.path.getsize(os.path.join(d, info["fbx"])) > 0, f"lod{lod} FBX non-empty")
    if "1" in rep["lods"]:
        check(rep["lods"]["1"]["tris"] < rep["lods"]["0"]["tris"], "LOD1 has fewer tris than LOD0")
    for t in rep["textures"]:
        stem = t[:-4] if t.endswith(".tga") else t
        check(t.endswith(".tga") and stem.endswith(MAP_SUFFIXES), f"texture {t} is TGA with a known map suffix")
        with open(os.path.join(d, t), "rb") as f:
            check(len(f.read(18)) == 18, f"texture {t} has TGA header")
    check(sorted(rep["previews"]) == sorted(f"{name}_preview_{v}.png" for v in PREVIEW_VIEWS),
          "all preview views rendered")
    pd = os.path.join(tmp, "_preview", name)
    check(sorted(os.listdir(d)) == sorted([i["fbx"] for i in rep["lods"].values()] + rep["textures"]),
          "drop folder holds only FBX + textures (no previews/report)")
    for p in rep["previews"]:
        with open(os.path.join(pd, p), "rb") as f:
            check(f.read(8) == b"\x89PNG\r\n\x1a\n", f"preview {p} is PNG")

    fbx = [os.path.join(d, i["fbx"]) for i in rep["lods"].values()]
    code, log = blender(os.path.join(ROOT, "tests", "check_fbx.py"), *fbx)
    re = tagged(log, "[check_fbx]")
    check(code == 0 and re is not None, "FBX re-import succeeds")
    if re is None:
        return
    used_mats = set()
    for lod, info in rep["lods"].items():
        r = re[os.path.join(d, info["fbx"])]
        used_mats |= set(r["materials"])
        check(r["types"] == ["MESH"], f"lod{lod} contains only meshes {r['types']}")
        check(r["names"] == [name], f"lod{lod} element name is '{name}' without _lodN {r['names']}")
        check(r["mesh_names"] == [name], f"lod{lod} mesh datablock named '{name}' (drives .msh file name) {r['mesh_names']}")
        check("preview_ground" not in r["materials"], f"lod{lod} has no preview objects")
        check(r["has_uv"], f"lod{lod} has UVs")
        check(r["unit_scale_factor"] == 100.0, f"lod{lod} FBX UnitScaleFactor=100 (metres), got {r['unit_scale_factor']}")
        check(r["scale"] == [1.0, 1.0, 1.0], f"lod{lod} object scale 1 {r['scale']}")
        built, back = sorted(info["size_m"]), sorted(r["raw_extent"])
        check(all(abs(a - b) < 0.01 for a, b in zip(built, back)),
              f"lod{lod} vertex extent in metres {built} vs {back}")
        rel = r["relative_filenames"]
        check(bool(rel) == bool(rep["textures"]) and all("/" not in n and "\\" not in n for n in rel),
              f"lod{lod} RelativeFilename is bare file name {rel}")
    # LODs may drop materials, but every textured material must appear in some LOD.
    tex_mats = {t[:-4].rsplit("_", 1)[0] for t in rep["textures"]}
    check(tex_mats <= used_mats, f"materials {sorted(used_mats)} cover textures {sorted(tex_mats)}")
    with open(os.path.join(d, rep["textures"][0]), "rb") as f:
        check(f.read(3)[2] == 2, "TGA saved uncompressed (type 2, not RLE)") if rep["textures"] else None


def test_validation(tmp):
    """build() mistakes must fail loudly before anything is exported."""
    print("[validation]")
    cases = {
        "no_lod0": 'def build(lib):\n    o = lib.box("x", (1, 1, 1), (0, 0, 0))\n    return {"lods": {1: [o]}}\n',
        "empty_lod": 'def build(lib):\n    o = lib.box("x", (1, 1, 1), (0, 0, 0))\n    return {"lods": {0: [o], 1: []}}\n',
        "lod_suffix": 'def build(lib):\n    o = lib.box("x_lod0", (1, 1, 1), (0, 0, 0))\n    return {"lods": {0: [o]}}\n',
    }
    adir = os.path.join(ROOT, "assets")
    for case, src in cases.items():
        name = f"_test_{case}"
        os.makedirs(os.path.join(adir, name))
        try:
            with open(os.path.join(adir, name, "model.py"), "w") as f:
                f.write(src)
            env = dict(os.environ, TF3_ASSETS_OUT=tmp)
            code, _ = blender(os.path.join(ROOT, "tools", "build_asset.py"), name, "--no-preview", env=env)
            check(code != 0, f"{case}: build fails")
            check(not os.listdir(os.path.join(tmp, name)), f"{case}: nothing exported")
        finally:
            shutil.rmtree(os.path.join(adir, name))


def test_stale_cleanup(tmp):
    print("[stale cleanup]")
    stale = os.path.join(tmp, "bench", "bench_lod2.fbx")
    os.makedirs(os.path.dirname(stale), exist_ok=True)
    open(stale, "w").close()
    env = dict(os.environ, TF3_ASSETS_OUT=tmp)
    code, _ = blender(os.path.join(ROOT, "tools", "build_asset.py"), "bench", "--no-preview", env=env)
    check(code == 0 and not os.path.exists(stale), "rebuild removes stale LOD from earlier build")


def main():
    names = sys.argv[1:] or sorted(n for n in os.listdir(os.path.join(ROOT, "assets")) if not n.startswith("_"))
    # Flatpak Blender has a private /tmp, so the scratch dir must live under the repo.
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test_out_") as tmp:
        for n in names:
            test_asset(n, tmp)
        if not sys.argv[1:]:
            test_validation(tmp)
            test_stale_cleanup(tmp)
    print(f"\n{'FAILED ' + str(len(fails)) if fails else 'all passed'}")
    sys.exit(1 if fails else 0)


main()
