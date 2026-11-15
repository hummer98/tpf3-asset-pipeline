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
			overwriteMeshes = false,
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
check("overwriteMeshes = false" in out and "scale = 100" in out, "other keys preserved")
try:
    m.patch_settings("function data() return { } end", "x", "/")
    check(False, "missing section raises")
except ValueError:
    check(True, "missing section raises")

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

print(f"\n{'FAILED ' + str(len(fails)) if fails else 'all passed'}")
sys.exit(1 if fails else 0)
