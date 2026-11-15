#!/usr/bin/env python3
"""Unit tests for tools/me_import.py pure helpers (no editor, no X11)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import me_import as m  # noqa: E402

fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


SETTINGS = '''function data()
return {
		constructionImportOptions = {
			blenderMode = false,
			scale = 100,
		},
		importOptions = { 
			blenderMode = false,
			overwriteAnimations = false,
			overwriteMaterials = false,
			overwriteMeshes = false,
			overwriteTextures = false,
		},
		pathOptions = {
			lastOpenedMod = { "", },
			userDataPath = "",
		},
	}
end'''

out = m.patch_settings(SETTINGS, "sandbox_1", "/u/local/")
ci = out[out.index("constructionImportOptions"):out.index("importOptions = {")]
io = out[out.index("importOptions = {"):out.index("pathOptions")]
check("blenderMode = false" in ci, "construction import blenderMode untouched")
check("blenderMode = true" in io, "model import blenderMode set")
check('lastOpenedMod = { "sandbox_1", }' in out, "lastOpenedMod set")
check('userDataPath = "/u/local/"' in out, "userDataPath set")
check(m.patch_settings(out, "sandbox_1", "/u/local/") == out, "patch is idempotent")
check(all(f"{k} = true" in io for k in ("overwriteMeshes", "overwriteMaterials", "overwriteTextures")),
      "overwrite toggles on (else re-import reuses stale .msh/.mtl/.dds)")
check("overwriteAnimations = false" in io and "scale = 100" in out, "other keys preserved")
try:
    m.patch_settings("function data() return { } end", "x", "/")
    check(False, "missing section raises")
except ValueError:
    check(True, "missing section raises")

# Real settings file layout: trailing space after "{", nested tables in other sections.
REAL = open(os.path.join(ROOT, "tests", "fixtures", "model_editor_settings_v13.lua")).read()
out = m.patch_settings(REAL, "sandbox_1", "/u/local/")
check(out.count("blenderMode = true") == 1, "real settings: exactly one blenderMode flipped")
check(len(out.splitlines()) == len(REAL.splitlines()), "real settings: line count unchanged")
check('externalModPath = ""' in out and "pixelsPerMeter = 320" in out, "real settings: unrelated keys intact")

for log, want in [
    ("x\nValidation: no errors!\n", (True, True)),
    ("Validation: 2 errors\n", (True, False)),
    ("Validation: no errors!\n...\nValidation: 1 error\n", (True, False)),
    ("nothing yet", (False, False)),
]:
    got = m.validation_result(log)[:2]
    check(got == want, f"validation_result {log!r} -> {got}")

MDL = '''function data()
return {
		boundingInfo = {
			bbMax = { 0.9, 0.295, 0.85, },
			bbMin = { -0.9, -0.225, 0, },
		},
	}
end'''
bb = m.parse_bbox(MDL)
check(bb == ([-0.9, -0.225, 0.0], [0.9, 0.295, 0.85]), f"parse_bbox {bb}")
check(m.bbox_matches(bb, [1.8, 0.52, 0.85]), "bbox matches build size")
check(not m.bbox_matches(bb, [180, 52, 85]), "cm/m mix-up detected")
check(not m.bbox_matches(([-0.9, 0, -0.225], [0.9, 0.85, 0.295]), [1.8, 0.52, 0.85]),
      "Y-up (axis mode off) detected")
try:
    m.parse_bbox("return {}")
    check(False, "missing bbox raises")
except ValueError:
    check(True, "missing bbox raises")

import tempfile
with tempfile.TemporaryDirectory() as steam:
    try:
        m.find_userdata(steam, env={})
        check(False, "no Steam account -> error")
    except SystemExit:
        check(True, "no Steam account -> error")
    os.makedirs(os.path.join(steam, "userdata", "111", "3493540", "local"))
    os.makedirs(os.path.join(steam, "userdata", "222", "999"))  # other game only
    got = m.find_userdata(steam, env={})
    check(got == os.path.join(steam, "userdata", "111", "3493540", "local", ""), f"single TF3 account picked {got}")
    os.makedirs(os.path.join(steam, "userdata", "333", "3493540", "local"))
    try:
        m.find_userdata(steam, env={})
        check(False, "two TF3 accounts -> ask for TF3_USERDATA")
    except SystemExit:
        check(True, "two TF3 accounts -> ask for TF3_USERDATA")
    check(m.find_userdata(steam, env={"TF3_USERDATA": "/x/local"}) == "/x/local/", "TF3_USERDATA override, trailing /")

print(f"\n{'FAILED ' + str(len(fails)) if fails else 'all passed'}")
sys.exit(1 if fails else 0)
