#!/usr/bin/env python3
"""Import a built asset into the TF3 Model Editor and save it, unattended.

The Model Editor has no CLI and ignores argv, so this:
  1. pins the editor settings (Blender axis mode, target mod, userdata path),
  2. launches the editor (or reuses a running one),
  3. drops out/<asset>/<asset>_lod0.fbx onto it via XDND,
  4. clicks Save with a synthetic event,
  5. checks the saved .mdl bounding box against the Blender build report.

usage: .venv/bin/python tools/me_import.py <asset> [--keep-open] [--mod staging_mod_dir]
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.expanduser("~/.local/share/Steam/steamapps/common/Transport Fever 3")
USERDATA = os.path.expanduser("~/.local/share/Steam/userdata/<steam_user_id>/3493540/local/")
SETTINGS = os.path.expanduser("~/.local/share/Transport Fever 3/model_editor_settings_v13.lua")
LOG = os.path.join(ROOT, "model_editor.log")
DEFAULT_MOD = "tf3_asset_sandbox_1"
TITLE_RX = r"Model Editor \(version"
SAVE_BUTTON = (74, 14)  # toolbar is left-anchored, so this holds for any window size


# ---- pure helpers (unit-tested in tests/test_me_import.py) ----

def _section(text, name):
    m = re.search(r"\b" + name + r"\s*=\s*\{", text)
    if not m:
        raise ValueError(f"settings section {name} not found")
    depth, i = 1, m.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return m.end(), i


def _set_in_section(text, section, key, value_lua):
    s, e = _section(text, section)
    body = text[s:e]
    new, n = re.subn(r"(\b" + key + r"\s*=\s*)(\{[^{}]*\}|\"[^\"]*\"|\w+)", lambda m: m.group(1) + value_lua, body, count=1)
    if n != 1:
        raise ValueError(f"{section}.{key} not found")
    return text[:s] + new + text[e:]


def patch_settings(text, mod, userdata):
    """importOptions.blenderMode is the editor's 'Use Blender Coordinate System';
    constructionImportOptions has its own blenderMode which we leave alone."""
    text = _set_in_section(text, "importOptions", "blenderMode", "true")
    text = _set_in_section(text, "pathOptions", "lastOpenedMod", '{ "%s", }' % mod)
    text = _set_in_section(text, "pathOptions", "userDataPath", '"%s"' % userdata)
    return text


def parse_bbox(mdl_text):
    def vec(key):
        m = re.search(key + r"\s*=\s*\{([^}]*)\}", mdl_text)
        if not m:
            raise ValueError(f"{key} not in .mdl")
        return [float(v) for v in m.group(1).split(",") if v.strip()]
    return vec("bbMin"), vec("bbMax")


def bbox_matches(bb, size_m, tol=0.01):
    lo, hi = bb
    return all(abs((h - l) - s) <= tol for l, h, s in zip(lo, hi, size_m))


# ---- editor control ----

def log_size():
    return os.path.getsize(LOG) if os.path.exists(LOG) else 0


def wait_log(offset, pattern, timeout):
    rx = re.compile(pattern)
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(LOG):
            with open(LOG, "rb") as f:
                f.seek(offset)
                if rx.search(f.read().decode("utf-8", "replace")):
                    return True
        time.sleep(0.3)
    return False


def launch():
    env = dict(os.environ, LD_LIBRARY_PATH="model_editor/plugins:." +
               (":" + os.environ["LD_LIBRARY_PATH"] if os.environ.get("LD_LIBRARY_PATH") else ""))
    log = open(LOG, "wb")
    # Own session so the caller's shell/process-group cleanup can't take it down.
    return subprocess.Popen(["model_editor/ModelEditor"], cwd=GAME, env=env, stdout=log,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("asset")
    ap.add_argument("--mod", default=DEFAULT_MOD, help="mod folder under local/staging_area")
    ap.add_argument("--keep-open", action="store_true")
    a = ap.parse_args()

    import xwin  # needs python-xlib (.venv)

    fbx = os.path.join(ROOT, "out", a.asset, f"{a.asset}_lod0.fbx")
    report_path = os.path.join(ROOT, "out", "_preview", a.asset, "report.json")
    if not os.path.exists(fbx):
        sys.exit(f"build first: {fbx} missing")
    mod_dir = os.path.join(USERDATA, "staging_area", a.mod)
    if not os.path.isdir(mod_dir):
        sys.exit(f"target mod missing: {mod_dir} (the editor only lists staging_area mods)")
    mdl = os.path.join(mod_dir, "content", a.asset, f"{a.asset}.mdl")

    d = xwin.open_display()
    wins = xwin.find_windows(d, TITLE_RX)
    if len(wins) > 1:
        sys.exit(f"{len(wins)} Model Editor windows open; close extras first")
    started = None
    if wins:
        # Settings are only read at startup, so a running editor keeps its target mod.
        print("[me_import] reusing running Model Editor")
        offset = log_size()
        if not wait_log(0, r"Set current mod: " + re.escape(a.mod) + r"\b", 0.1):
            print(f"[me_import] warning: could not confirm running editor targets {a.mod}")
    else:
        with open(SETTINGS, encoding="utf-8") as f:
            text = f.read()
        new = patch_settings(text, a.mod, USERDATA)
        if new != text:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                f.write(new)
        started = launch()
        if not wait_log(0, r"Set current mod: " + re.escape(a.mod) + r"\b", 90):
            sys.exit(f"editor did not select mod {a.mod} (see {LOG})")
        end = time.time() + 30
        while not (wins := xwin.find_windows(d, TITLE_RX)) and time.time() < end:
            time.sleep(0.5)
        if not wins:
            sys.exit("editor window not found")
        time.sleep(2)  # let the first frames render before input arrives
        offset = log_size()
    try:
        run(a, d, xwin, wins[0], fbx, mdl, report_path, offset)
    finally:
        if started is not None and not a.keep_open:
            os.killpg(started.pid, signal.SIGTERM)
            try:
                started.wait(15)
            except subprocess.TimeoutExpired:
                os.killpg(started.pid, signal.SIGKILL)


def run(a, d, xwin, win_info, fbx, mdl, report_path, offset):
    win, _, ver, _pid = win_info

    before = os.path.getmtime(mdl) if os.path.exists(mdl) else 0
    served = xwin.drop_files(d, win, ver, [fbx])
    if served != 1 or not wait_log(offset, r"Validation: ", 60):
        sys.exit(f"import did not complete (selection served={served}, see {LOG})")
    want = f"{a.mod}::/{a.asset}/{a.asset}.mdl"
    end = time.time() + 15  # title follows a frame or two after the import
    while want not in (xwin.title(d, win) or "") and time.time() < end:
        time.sleep(0.3)
    if want not in (xwin.title(d, win) or ""):
        sys.exit(f"editor shows '{xwin.title(d, win)}', expected {want}")

    offset = log_size()
    xwin.click(d, win, *SAVE_BUTTON)
    end = time.time() + 60
    while time.time() < end and not (os.path.exists(mdl) and os.path.getmtime(mdl) > before):
        time.sleep(0.3)
    if not (os.path.exists(mdl) and os.path.getmtime(mdl) > before):
        sys.exit(f"save did not write {mdl}")
    wait_log(offset, r"Prepare material ubo", 10)

    result = {"asset": a.asset, "mod": a.mod, "mdl": mdl}
    with open(mdl, encoding="utf-8") as f:
        bb = parse_bbox(f.read())
    result["bbox"] = bb
    if os.path.exists(report_path):
        with open(report_path) as f:
            size = json.load(f)["lods"]["0"]["size_m"]
        result["size_m"] = size
        result["bbox_matches_build"] = bbox_matches(bb, size)

    print("[me_import] " + json.dumps(result, ensure_ascii=False))
    if not result.get("bbox_matches_build", True):
        sys.exit(2)


if __name__ == "__main__":
    main()
