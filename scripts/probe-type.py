#!/usr/bin/env python3
"""Headless typing test for the OpenBangla Fcitx5 engine.

Talks to the running Fcitx5 through its D-Bus input-context frontend (the same
API the GTK/Qt im-modules and the portal use): creates an input context,
focuses it, switches it to the `openbangla` input method, feeds key events, and
collects CommitString signals. Keys the engine does not accept are treated as
if the application inserted them (space, punctuation).

If `openbangla` is not in the user's current input-method group, it is added
temporarily for the test and the group is restored afterwards.

Usage (session bus; runs on the host or in the dev container):
    scripts/probe-type.py ["ami banglay gan gai"] [--expect "আমি বাংলায় গান গাই"]
Exit 0 when the result matches --expect (or always, without --expect).
"""
import argparse
import sys
import unicodedata

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = "org.fcitx.Fcitx5"
IM_IFACE = "org.fcitx.Fcitx.InputMethod1"
IC_IFACE = "org.fcitx.Fcitx.InputContext1"
CTRL_IFACE = "org.fcitx.Fcitx.Controller1"
IM_NAME = "openbangla"
# Capabilities: Preedit | FormattedPreedit | ClientSideInputPanel would make the
# client draw; keep 0 so the engine behaves as with a plain app.
CAPS = 0


def call(conn, path, iface, method, args=None, reply=None):
    return conn.call_sync(BUS, path, iface, method, args, reply and GLib.VariantType(reply),
                          Gio.DBusCallFlags.NONE, 5000, None)


def pump(ms=60):
    ctx = GLib.MainContext.default()
    end = GLib.get_monotonic_time() + ms * 1000
    while GLib.get_monotonic_time() < end:
        ctx.iteration(False)


def keysym(ch):
    if ch == " ":
        return 0x20
    if ch == "\n":
        return 0xFF0D
    return ord(ch)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="ami banglay gan gai")
    ap.add_argument("--expect")
    args = ap.parse_args()

    conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    out = []
    events = []

    def on_signal(_c, _s, _p, _i, name, params):
        if name == "CommitString":
            out.append(params.unpack()[0])
        elif name == "ForwardKey":
            sym, _state, release = params.unpack()
            if not release and 0x20 <= sym < 0x7F:
                out.append(chr(sym))
        events.append(name)

    path, _uuid = call(conn, "/org/freedesktop/portal/inputmethod", IM_IFACE,
                       "CreateInputContext",
                       GLib.Variant("(a(ss))", ([("program", "obk-probe"), ("display", "")],)),
                       "(oay)").unpack()
    conn.signal_subscribe(BUS, IC_IFACE, None, path, None, Gio.DBusSignalFlags.NONE, on_signal)

    ctrl = "/controller"
    saved_group = None
    try:
        call(conn, path, IC_IFACE, "SetCapability", GLib.Variant("(t)", (CAPS,)))
        call(conn, path, IC_IFACE, "FocusIn")
        pump()
        call(conn, ctrl, CTRL_IFACE, "SetCurrentIM", GLib.Variant("(s)", (IM_NAME,)))
        pump()
        cur = call(conn, ctrl, CTRL_IFACE, "CurrentInputMethod", None, "(s)").unpack()[0]
        if cur != IM_NAME:
            group = call(conn, ctrl, CTRL_IFACE, "CurrentInputMethodGroup", None, "(s)").unpack()[0]
            saved_group = (group, call(conn, ctrl, CTRL_IFACE, "InputMethodGroupInfo",
                                       GLib.Variant("(s)", (group,)), "(sa(ss))").unpack())
            layout, items = saved_group[1]
            print(f"note: adding {IM_NAME} to group '{group}' temporarily", file=sys.stderr)
            call(conn, ctrl, CTRL_IFACE, "SetInputMethodGroupInfo",
                 GLib.Variant("(ssa(ss))", (group, layout, items + [(IM_NAME, "")])))
            pump(300)
            call(conn, path, IC_IFACE, "FocusIn")
            call(conn, ctrl, CTRL_IFACE, "SetCurrentIM", GLib.Variant("(s)", (IM_NAME,)))
            pump()
            cur = call(conn, ctrl, CTRL_IFACE, "CurrentInputMethod", None, "(s)").unpack()[0]
        if cur != IM_NAME:
            print(f"FAIL: could not switch to {IM_NAME} (current: {cur})", file=sys.stderr)
            return 2

        for ch in args.text:
            sym = keysym(ch)
            for release in (False, True):
                accepted = call(conn, path, IC_IFACE, "ProcessKeyEvent",
                                GLib.Variant("(uuubu)", (sym, 0, 0, release, 0)), "(b)").unpack()[0]
                if not accepted and not release:
                    pump(30)
                    out.append(ch)  # the application would insert it
            pump(20)
        # flush any pending preedit with a final space
        accepted = call(conn, path, IC_IFACE, "ProcessKeyEvent",
                        GLib.Variant("(uuubu)", (0x20, 0, 0, False, 0)), "(b)").unpack()[0]
        pump(100)
        result = "".join(out).strip()
        print(f"input : {args.text}")
        print(f"output: {result}")
        if args.expect is not None:
            # Compare canonically: the engine emits precomposed letters (e.g. U+09DF য়)
            # where typed text may use base + nukta (U+09AF U+09BC).
            nfc = lambda t: unicodedata.normalize("NFC", t)
            ok = nfc(result) == nfc(args.expect)
            print("PASS" if ok else f"FAIL (expected: {args.expect})")
            return 0 if ok else 1
        return 0
    finally:
        try:
            call(conn, path, IC_IFACE, "FocusOut")
            call(conn, path, IC_IFACE, "DestroyIC")
        except GLib.Error:
            pass
        if saved_group:
            group, (layout, items) = saved_group
            call(conn, ctrl, CTRL_IFACE, "SetInputMethodGroupInfo",
                 GLib.Variant("(ssa(ss))", (group, layout, items)))
            print(f"note: restored group '{group}'", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
