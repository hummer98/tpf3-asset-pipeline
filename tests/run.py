#!/usr/bin/env python3
"""Pipeline test: build each asset headless into a temp dir, then verify outputs.
usage: python3 tests/run.py [asset ...]   (default: all assets)"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = os.path.join(ROOT, "tools", "blender.sh")
fails = []


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
        check(t.endswith((".tga",)) and "_" in t, f"texture {t} is TGA with map suffix")
        with open(os.path.join(d, t), "rb") as f:
            check(len(f.read(18)) == 18, f"texture {t} has TGA header")
    for p in rep["previews"]:
        with open(os.path.join(d, p), "rb") as f:
            check(f.read(8) == b"\x89PNG\r\n\x1a\n", f"preview {p} is PNG")

    fbx = [os.path.join(d, i["fbx"]) for i in rep["lods"].values()]
    code, log = blender(os.path.join(ROOT, "tests", "check_fbx.py"), *fbx)
    re = tagged(log, "[check_fbx]")
    check(code == 0 and re is not None, "FBX re-import succeeds")
    if re is None:
        return
    for lod, info in rep["lods"].items():
        r = re[os.path.join(d, info["fbx"])]
        check(r["objects"] >= 1, f"lod{lod} has mesh")
        check(r["has_uv"], f"lod{lod} has UVs")
        # Metre scale must survive the round trip (a cm/m mix-up shows as x100).
        built = sorted(info["size_m"])
        back = sorted(a * s for a, s in zip(r["dims"], r["scale"]))
        check(all(abs(a - b) < 0.01 for a, b in zip(built, back)),
              f"lod{lod} size kept {built} vs {[round(v, 3) for v in back]}")
        tex_mats = {t.rsplit("_", 1)[0] for t in rep["textures"]}
        check(tex_mats <= set(r["materials"]),
              f"lod{lod} materials {r['materials']} cover textures {sorted(tex_mats)}")


def main():
    names = sys.argv[1:] or sorted(os.listdir(os.path.join(ROOT, "assets")))
    # Flatpak Blender has a private /tmp, so the scratch dir must live under the repo.
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test_out_") as tmp:
        for n in names:
            test_asset(n, tmp)
    print(f"\n{'FAILED ' + str(len(fails)) if fails else 'all passed'}")
    sys.exit(1 if fails else 0)


main()
