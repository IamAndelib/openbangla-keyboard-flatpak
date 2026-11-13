#!/usr/bin/env python3
"""Show / apply / restore the recommended Fcitx5 settings for OpenBangla users.

Talks to the RUNNING Fcitx5 on the session bus through its own config API
(Controller1.GetConfig / SetConfig), so values are validated, saved and
reloaded by Fcitx5 itself. No hand-editing of config files.

Recommended (docs/research.md §6.1, verified in an isolated Fcitx5):
  global   Hotkey.AltTriggerKeys = []        Left-Shift tap no longer switches IM
           Behavior.ShareInputState = All    one Bangla/English state for all windows
           Behavior.ActiveByDefault = False  each session starts in English (the first IM);
                                             Fcitx5 can't remember the last state across restarts
  classicui PreferTextIcon = True            tray shows the IM label (বা) instead of a
                                             missing icon (Flatpak add-ons can't export icons)
Ctrl+Space (TriggerKeys) stays the toggle.

Usage:
  scripts/fcitx-config.py --show
  scripts/fcitx-config.py --apply            # backs up first to out/backup/<timestamp>/
  scripts/fcitx-config.py --restore <dir>    # restore files from a backup, then ReloadConfig
"""
import argparse
import datetime
import os
import shutil
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_DIR = os.path.expanduser("~/.var/app/org.fcitx.Fcitx5/config/fcitx5")
FILES = ["config", "conf/classicui.conf"]
V = GLib.Variant

GLOBAL = V("a{sv}", {
    "Hotkey": V("a{sv}", {"AltTriggerKeys": V("a{sv}", {})}),
    "Behavior": V("a{sv}", {"ShareInputState": V("s", "All"),
                            "ActiveByDefault": V("s", "False")}),
})
CLASSICUI = V("a{sv}", {"PreferTextIcon": V("s", "True")})


class Fcitx:
    def __init__(self):
        self.c = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def _call(self, method, args, reply=None):
        r = self.c.call_sync("org.fcitx.Fcitx5", "/controller", "org.fcitx.Fcitx.Controller1",
                             method, args, GLib.VariantType(reply) if reply else None,
                             Gio.DBusCallFlags.NONE, 5000, None)
        return r.unpack() if reply else None

    def get(self, uri):
        return self._call("GetConfig", V("(s)", (uri,)), "(va(sa(sssva{sv})))")[0]

    def set(self, uri, value):
        self._call("SetConfig", V("(sv)", (uri, value)))

    def reload(self):
        self._call("ReloadConfig", None)


def show(fx):
    g = fx.get("fcitx://config/global")
    ui = fx.get("fcitx://config/addon/classicui")
    alt = g["Hotkey"].get("AltTriggerKeys")
    print(f"TriggerKeys       : {dict(g['Hotkey'].get('TriggerKeys') or {})}")
    print(f"AltTriggerKeys    : {dict(alt) if isinstance(alt, dict) else (alt or '(empty)')}")
    print(f"ShareInputState   : {g['Behavior'].get('ShareInputState')}")
    print(f"ActiveByDefault   : {g['Behavior'].get('ActiveByDefault')}")
    print(f"PreferTextIcon    : {ui.get('PreferTextIcon')}")
    return g, ui


def is_recommended(g, ui):
    alt = g["Hotkey"].get("AltTriggerKeys")
    return (not alt and g["Behavior"].get("ShareInputState") == "All"
            and g["Behavior"].get("ActiveByDefault") == "False"
            and ui.get("PreferTextIcon") == "True")


def backup():
    d = os.path.join(ROOT, "out", "backup", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    for f in FILES:
        src = os.path.join(CFG_DIR, f)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
            shutil.copy2(src, os.path.join(d, f))
    open(os.path.join(d, "MANIFEST"), "w").write(
        "".join(f"{f}\n" for f in FILES if os.path.exists(os.path.join(CFG_DIR, f))))
    return d


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--restore", metavar="BACKUP_DIR")
    a = ap.parse_args()
    fx = Fcitx()

    if a.show:
        gl, ui = show(fx)
        print("state: " + ("recommended" if is_recommended(gl, ui) else "NOT recommended"))
        return 0

    if a.apply:
        d = backup()
        print(f"backup: {os.path.relpath(d, ROOT)}")
        fx.set("fcitx://config/global", GLOBAL)
        fx.set("fcitx://config/addon/classicui", CLASSICUI)
        gl, ui = show(fx)
        ok = is_recommended(gl, ui)
        print("state: " + ("recommended (applied)" if ok else "FAILED to apply"))
        return 0 if ok else 1

    d = os.path.abspath(a.restore)
    listed = open(os.path.join(d, "MANIFEST")).read().split()
    for f in FILES:
        dst = os.path.join(CFG_DIR, f)
        if f in listed:
            shutil.copy2(os.path.join(d, f), dst)
        elif os.path.exists(dst):
            os.remove(dst)  # did not exist before apply
    fx.reload()
    show(fx)
    print(f"restored from {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
