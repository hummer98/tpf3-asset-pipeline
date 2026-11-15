"""Drive an X11 (XWayland) window without touching the real pointer.

Under Wayland xdotool can't warp the pointer, so its clicks land wherever the
cursor is (e.g. on the running game). Instead we talk X11 protocol directly to
the target window: XDND for file drops, synthetic button events for clicks.
"""
import os
import re
import time
import urllib.parse

from Xlib import X, display, protocol

XDND_VERSION = 5


def open_display():
    return display.Display()


def _name(d, w):
    name = w.get_wm_name()
    if not name:
        prop = w.get_full_property(d.intern_atom("_NET_WM_NAME"), 0)
        name = prop.value if prop else None
    if isinstance(name, bytes):
        name = name.decode("utf-8", "replace")
    return name


def find_windows(d, pattern):
    """Viewable XDND-aware windows whose title matches -> [(win, title, xdnd_ver, pid)]."""
    rx = re.compile(pattern)
    hits, stack = [], [d.screen().root]
    while stack:
        w = stack.pop()
        try:
            name = _name(d, w)
            if name and rx.search(name) and w.get_attributes().map_state == X.IsViewable:
                aware = w.get_full_property(d.intern_atom("XdndAware"), X.AnyPropertyType)
                pid = w.get_full_property(d.intern_atom("_NET_WM_PID"), X.AnyPropertyType)
                if aware:
                    hits.append((w, name, aware.value[0], pid.value[0] if pid else None))
            stack.extend(w.query_tree().children)
        except Exception:
            pass
    return hits


def title(d, w):
    try:
        return _name(d, w)
    except Exception:
        return None


def _client_message(d, target, type_name, data):
    target.send_event(protocol.event.ClientMessage(
        window=target, client_type=d.intern_atom(type_name),
        data=(32, (data + [0] * 5)[:5])), event_mask=0)
    d.flush()


def drop_files(d, target, xdnd_version, paths, timeout=30):
    """XDND source: offer text/uri-list and drop at the window centre.
    Returns number of selection requests served (1 per accepted drop)."""
    version = min(xdnd_version, XDND_VERSION)
    uri_list = "".join("file://" + urllib.parse.quote(os.path.abspath(p)) + "\r\n"
                       for p in paths).encode()
    root = d.screen().root
    src = root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    a = {n: d.intern_atom(n) for n in (
        "XdndSelection", "XdndActionCopy", "text/uri-list", "XdndStatus", "XdndFinished")}
    src.set_selection_owner(a["XdndSelection"], X.CurrentTime)
    geo = target.get_geometry()
    # w.translate_coords(src, x, y) maps src-local coords into w: target centre -> root.
    c = root.translate_coords(target, geo.width // 2, geo.height // 2)
    served = [0]

    def pump(want):
        end = time.time() + timeout
        while time.time() < end:
            while d.pending_events():
                ev = d.next_event()
                if ev.type == X.SelectionRequest and ev.selection == a["XdndSelection"]:
                    prop = ev.property or ev.target
                    if ev.target == a["text/uri-list"]:
                        ev.requestor.change_property(prop, ev.target, 8, uri_list)
                    else:
                        prop = X.NONE
                    ev.requestor.send_event(protocol.event.SelectionNotify(
                        time=ev.time, requestor=ev.requestor, selection=ev.selection,
                        target=ev.target, property=prop), event_mask=0)
                    d.flush()
                    served[0] += 1
                elif ev.type == X.ClientMessage and ev.client_type == a[want]:
                    return ev.data[1][1] & 1
            time.sleep(0.01)
        return None

    try:
        _client_message(d, target, "XdndEnter", [src.id, version << 24, a["text/uri-list"]])
        _client_message(d, target, "XdndPosition",
                        [src.id, 0, (c.x << 16) | (c.y & 0xFFFF), X.CurrentTime, a["XdndActionCopy"]])
        if not pump("XdndStatus"):
            _client_message(d, target, "XdndLeave", [src.id])
            raise RuntimeError("target did not accept the drop")
        _client_message(d, target, "XdndDrop", [src.id, 0, X.CurrentTime])
        fin = pump("XdndFinished")
        if fin is None:
            _client_message(d, target, "XdndLeave", [src.id])
            raise RuntimeError("no XdndFinished from target")
        if version >= 5 and not fin:
            raise RuntimeError("target finished but rejected the drop")
    finally:
        src.destroy()
        d.flush()
    return served[0]


def _send(d, w, cls, x, y, mask, **kw):
    root = d.screen().root
    rp = root.translate_coords(w, x, y)
    w.send_event(cls(time=X.CurrentTime, root=root, window=w, same_screen=1, child=X.NONE,
                     root_x=rp.x, root_y=rp.y, event_x=x, event_y=y, **kw),
                 event_mask=mask, propagate=False)
    d.flush()


def click(d, w, x, y):
    """Left click at window-local (x, y) via synthetic events (SDL accepts them)."""
    _send(d, w, protocol.event.MotionNotify, x, y, X.PointerMotionMask, state=0, detail=0)
    time.sleep(0.05)
    _send(d, w, protocol.event.ButtonPress, x, y, X.ButtonPressMask, state=0, detail=1)
    time.sleep(0.05)
    _send(d, w, protocol.event.ButtonRelease, x, y, X.ButtonReleaseMask,
          state=X.Button1Mask, detail=1)
