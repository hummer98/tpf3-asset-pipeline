#!/usr/bin/env python3
"""Import a built asset into the TF3 Model Editor and save it, unattended.

The Model Editor has no CLI and ignores argv, so this:
  1. pins the editor settings (Blender axis mode, target mod, userdata path),
  2. launches a fresh editor (aborts if one is already running),
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
    # Without these the editor reuses the mod's existing .msh/.mtl/.dds on
    # re-import ("Found mesh to reuse ..."), so a rebuilt shape would be ignored.
    for key in ("overwriteMeshes", "overwriteMaterials", "overwriteTextures"):
        text = _set_in_section(text, "importOptions", key, "true")
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


def validation_result(log_text):
    """Last 'Validation: ...' line after an import -> (found, ok, line)."""
    lines = re.findall(r"Validation: [^\n]*", log_text)
    if not lines:
        return False, False, None
    last = lines[-1].strip()
    return True, last.startswith("Validation: no errors"), last


def bbox_matches(bb, size_m, tol=0.01):
    lo, hi = bb
    return all(abs((h - l) - s) <= tol for l, h, s in zip(lo, hi, size_m))


# ---- editor control ----

def editor_pids():
    """PIDs of running Model Editors. comm is renamed to 'Main Thread', so match exe."""
    pids = []
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                if os.path.basename(os.readlink(f"/proc/{p}/exe")) == "ModelEditor":
                    pids.append(int(p))
            except OSError:
                pass
    return pids


def read_log(offset=0):
    if not os.path.exists(LOG):
        return ""
    with open(LOG, "rb") as f:
        f.seek(offset)
        return f.read().decode("utf-8", "replace")


def log_size():
    return os.path.getsize(LOG) if os.path.exists(LOG) else 0


def wait_until(pred, timeout, step=0.3):
    end = time.time() + timeout
    while time.time() < end:
        r = pred()
        if r:
            return r
        time.sleep(step)
    return pred()


def launch():
    env = dict(os.environ, LD_LIBRARY_PATH="model_editor/plugins:." +
               (":" + os.environ["LD_LIBRARY_PATH"] if os.environ.get("LD_LIBRARY_PATH") else ""))
    with open(LOG, "wb") as log:
        # Own session so the caller's shell/process-group cleanup can't take it down.
        return subprocess.Popen(["model_editor/ModelEditor"], cwd=GAME, env=env, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)


def write_settings(new):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, SETTINGS)


def stop(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("asset")
    ap.add_argument("--mod", default=DEFAULT_MOD, help="mod folder under local/staging_area")
    ap.add_argument("--keep-open", action="store_true", help="leave the editor running afterwards")
    a = ap.parse_args()

    fbx = os.path.join(ROOT, "out", a.asset, f"{a.asset}_lod0.fbx")
    report_path = os.path.join(ROOT, "out", "_preview", a.asset, "report.json")
    if not os.path.exists(fbx):
        sys.exit(f"build first: {fbx} missing")
    # Without the build report the bbox check can't run; a stale one would check the wrong shape.
    if not os.path.exists(report_path) or os.path.getmtime(report_path) < os.path.getmtime(fbx):
        sys.exit(f"build report missing or older than FBX: {report_path} (rebuild)")
    mod_dir = os.path.join(USERDATA, "staging_area", a.mod)
    if not os.path.isdir(mod_dir):
        sys.exit(f"target mod missing: {mod_dir} (the editor only lists staging_area mods)")

    # Always a fresh editor: settings are read only at startup, a manually started one
    # doesn't log to LOG, and re-importing in a long session once segfaulted.
    running = editor_pids()
    if running:
        sys.exit(f"Model Editor already running (pid {running}); close it first")

    import xwin  # needs python-xlib (.venv)

    with open(SETTINGS, encoding="utf-8") as f:
        text = f.read()
    new = patch_settings(text, a.mod, USERDATA)
    if new != text:
        write_settings(new)

    d = xwin.open_display()
    proc = launch()
    try:
        if not wait_until(lambda: re.search(r"Set current mod: " + re.escape(a.mod) + r"\b", read_log()), 90):
            sys.exit(f"editor did not select mod {a.mod} (see {LOG})")
        # Only accept the window owned by the editor we started (never a browser tab etc.).
        wins = wait_until(lambda: [w for w in xwin.find_windows(d, TITLE_RX) if w[3] == proc.pid], 30)
        if not wins:
            sys.exit("editor window not found")
        time.sleep(2)  # let the first frames render before input arrives
        run(a, d, xwin, wins[0], fbx, mod_dir, report_path)
    finally:
        if not a.keep_open:
            stop(proc)


def saved_files(mod_dir, asset):
    base = os.path.join(mod_dir, "content", asset)
    out = {}
    for dp, _, fs in os.walk(base):
        for f in fs:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, base)] = os.stat(p).st_mtime
    return out


def run(a, d, xwin, win_info, fbx, mod_dir, report_path):
    win, _, ver, _pid = win_info
    mdl = os.path.join(mod_dir, "content", a.asset, f"{a.asset}.mdl")

    offset = log_size()
    served = xwin.drop_files(d, win, ver, [fbx])
    if served != 1:
        sys.exit(f"drop not taken (selection requests served={served})")
    found = wait_until(lambda: validation_result(read_log(offset))[0], 60)
    _, ok, line = validation_result(read_log(offset))
    if not found:
        sys.exit(f"import did not complete (see {LOG})")
    if not ok:
        sys.exit(f"import validation failed: {line} (see {LOG})")
    want = f"{a.mod}::/{a.asset}/{a.asset}.mdl"
    if not wait_until(lambda: want in (xwin.title(d, win) or ""), 15):  # title lags a frame or two
        sys.exit(f"editor shows '{xwin.title(d, win)}', expected {want}")

    # Baseline right before Save: the import itself may touch files in the mod.
    before = saved_files(mod_dir, a.asset)
    t_click = time.time()

    def saved():
        now = saved_files(mod_dir, a.asset)
        msh = [k for k in now if k.endswith(".msh")]
        return (now.get(f"{a.asset}.mdl", 0) > before.get(f"{a.asset}.mdl", 0)
                and msh and all(now[k] > before.get(k, 0) for k in msh)) and now

    after = None
    for attempt in range(2):  # a click can miss if hover hasn't registered yet
        xwin.click(d, win, *SAVE_BUTTON)
        after = wait_until(saved, 20)
        if after:
            break
    if not after:
        sys.exit(f"save did not rewrite .mdl and all .msh in {os.path.dirname(mdl)}")
    # Wait until the files stop changing so we never parse a half-written .mdl.
    prev, end = None, time.time() + 30
    while (cur := saved_files(mod_dir, a.asset)) != prev:
        if time.time() > end:
            sys.exit(f"saved files kept changing for 30 s in {os.path.dirname(mdl)}")
        prev = cur
        time.sleep(1)

    with open(mdl, encoding="utf-8") as f:
        bb = parse_bbox(f.read())
    with open(report_path) as f:
        size = json.load(f)["lods"]["0"]["size_m"]
    result = {"asset": a.asset, "mod": a.mod, "mdl": mdl, "bbox": bb, "size_m": size,
              "bbox_matches_build": bbox_matches(bb, size),
              "rewritten": sorted(k for k, t in prev.items() if t >= t_click - 1)}
    print("[me_import] " + json.dumps(result, ensure_ascii=False))
    if not result["bbox_matches_build"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
