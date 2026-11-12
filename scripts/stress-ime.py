#!/usr/bin/env python3
"""Reliability / pressure test for the OpenBangla engine in the running Fcitx5.

Drives Fcitx5 through its D-Bus input-context frontend (the same API the
GTK/Qt im-modules use) and checks, per scenario, that the input method stays
`openbangla`, that Fcitx5 neither crashes nor restarts, and that its memory
stays bounded.

Scenarios (run all by default, or pick with --only):
  shift-tap   tap Left Shift alone while OpenBangla is active        (H1)
  new-ic      open a second input context ("another window")          (H2)
  refocus     FocusOut/FocusIn the same context many times
  soak        N random Avro-phonetic keystrokes incl. Shift combos,
              BackSpace, arrows, Return, punctuation, digits
  burst       many short words typed with no pause (latency check)

Usage:  scripts/stress-ime.py [--only shift-tap,soak] [--keys 20000] [--seed 1]
Prints one PASS/FAIL line per scenario and exits non-zero on any FAIL.
Read-only for the user's config: if `openbangla` is missing from the current
group it is added temporarily and the group is restored afterwards.
"""
import argparse
import os
import random
import subprocess
import sys
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = "org.fcitx.Fcitx5"
IM_IFACE = "org.fcitx.Fcitx.InputMethod1"
IC_IFACE = "org.fcitx.Fcitx.InputContext1"
CTRL = "/controller"
CTRL_IFACE = "org.fcitx.Fcitx.Controller1"
IM = "openbangla"

XK = {"space": 0x20, "Return": 0xFF0D, "BackSpace": 0xFF08, "Tab": 0xFF09,
      "Left": 0xFF51, "Up": 0xFF52, "Right": 0xFF53, "Down": 0xFF54,
      "Shift_L": 0xFFE1, "Control_L": 0xFFE3}
SHIFT_MASK, CTRL_MASK = 1 << 0, 1 << 2


class Fcitx:
    def __init__(self):
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(self, path, iface, method, sig=None, args=(), reply=None, timeout=5000):
        params = GLib.Variant(sig, args) if sig else None
        r = self.conn.call_sync(BUS, path, iface, method, params,
                                GLib.VariantType(reply) if reply else None,
                                Gio.DBusCallFlags.NONE, timeout, None)
        return r.unpack() if reply else None

    def ctrl(self, method, sig=None, args=(), reply=None):
        return self.call(CTRL, CTRL_IFACE, method, sig, args, reply)

    def current_im(self):
        return self.ctrl("CurrentInputMethod", reply="(s)")[0]

    def owner_pid(self):
        r = self.conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                "org.freedesktop.DBus", "GetConnectionUnixProcessID",
                                GLib.Variant("(s)", (BUS,)), GLib.VariantType("(u)"),
                                Gio.DBusCallFlags.NONE, 2000, None)
        return r.unpack()[0]


def pump(ms=10):
    ctx = GLib.MainContext.default()
    end = GLib.get_monotonic_time() + ms * 1000
    while GLib.get_monotonic_time() < end:
        ctx.iteration(False)


class IC:
    def __init__(self, fx, name):
        self.fx = fx
        self.path, _ = fx.call("/org/freedesktop/portal/inputmethod", IM_IFACE,
                               "CreateInputContext", "(a(ss))",
                               ([("program", name), ("display", "")],), "(oay)")
        self.commits = []
        self.im = None  # this context's own IM, from its CurrentIM signal
        fx.conn.signal_subscribe(BUS, IC_IFACE, "CommitString", self.path, None,
                                 Gio.DBusSignalFlags.NONE,
                                 lambda *a: self.commits.append(a[5].unpack()[0]))
        fx.conn.signal_subscribe(BUS, IC_IFACE, "CurrentIM", self.path, None,
                                 Gio.DBusSignalFlags.NONE, self._on_im)
        fx.call(self.path, IC_IFACE, "SetCapability", "(t)", (0,))

    def _on_im(self, *a):
        self.im = a[5].unpack()[1]  # (name, uniqueName, langCode)

    def focus_in(self):
        self.fx.call(self.path, IC_IFACE, "FocusIn")
        pump(5)

    def focus_out(self):
        self.fx.call(self.path, IC_IFACE, "FocusOut")
        pump(5)

    def key(self, sym, state=0, release=False):
        return self.fx.call(self.path, IC_IFACE, "ProcessKeyEvent", "(uuubu)",
                            (sym, 0, state, release, int(time.monotonic() * 1000) & 0xFFFFFFFF),
                            "(b)")[0]

    def tap(self, sym, state=0, hold=0.0):
        a = self.key(sym, state)
        if hold:
            time.sleep(hold)
        self.key(sym, state, True)
        return a

    def destroy(self):
        try:
            self.fx.call(self.path, IC_IFACE, "DestroyIC")
        except GLib.Error:
            pass


def rss_kib(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    # daemon runs inside a sandbox: find the child fcitx5-bin
    try:
        out = subprocess.run(["pgrep", "-f", "fcitx5-bin"], capture_output=True, text=True).stdout
        for p in out.split():
            with open(f"/proc/{p}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1])
    except OSError:
        pass
    return -1


def activate(fx, ic):
    ic.focus_in()
    fx.ctrl("SetCurrentIM", "(s)", (IM,))
    pump(30)
    return fx.current_im() == IM


# ---------------------------------------------------------------- scenarios

def sc_shift_tap(fx, ic, _a):
    """H1: Fcitx5's default AltTriggerKeys=Shift_L toggles to the first IM."""
    assert activate(fx, ic), "could not activate openbangla"
    results = []
    for hold in (0.03, 0.10, 0.20, 0.40):
        activate(fx, ic)
        ic.tap(XK["Shift_L"], hold=hold)
        pump(30)
        results.append((hold, fx.current_im()))
    switched = [f"{int(h*1000)}ms→{im}" for h, im in results if im != IM]
    ok = not switched
    detail = ", ".join(f"{int(h*1000)}ms:{im}" for h, im in results)
    return ok, detail


def sc_new_ic(fx, ic, _a):
    """H2: a second input context (new window/app) starts in which IM?"""
    assert activate(fx, ic), "could not activate openbangla"
    other = IC(fx, "obk-stress-second-window")
    try:
        other.focus_in()
        pump(30)
        im_new = fx.current_im()
        other.focus_out()
        ic.focus_in()
        pump(30)
        im_back = fx.current_im()
    finally:
        other.destroy()
    ok = im_new == IM and im_back == IM
    return ok, f"new context starts in '{im_new}'; original context after refocus: '{im_back}'"


def sc_refocus(fx, ic, a):
    assert activate(fx, ic), "could not activate openbangla"
    lost = 0
    for i in range(a.refocus):
        ic.focus_out()
        ic.focus_in()
        if fx.current_im() != IM:
            lost += 1
            activate(fx, ic)
    return lost == 0, f"{a.refocus} focus cycles, IM lost {lost} times"


ALPHA = "abcdefghijklmnopqrstuvwxyz"
SHIFTABLE = "TDNSRGOIUJKY"  # Avro uses these capitals


def sc_soak(fx, ic, a):
    rng = random.Random(a.seed)
    assert activate(fx, ic), "could not activate openbangla"
    pid0 = fx.owner_pid()
    rss0 = rss_kib(pid0)
    lost, errors, slow, stolen = 0, 0, 0, 0
    worst = 0.0
    hist = []
    lost_ctx = []
    t_start = time.monotonic()
    for i in range(a.keys):
        r = rng.random()
        try:
            t0 = time.monotonic()
            if r < 0.70:
                c = rng.choice(ALPHA); ic.tap(ord(c)); hist.append(c)
            elif r < 0.78:  # Shift+capital, realistic order: Shift down, key, key up, Shift up
                c = rng.choice(SHIFTABLE)
                ic.key(XK["Shift_L"])
                ic.tap(ord(c), SHIFT_MASK)
                ic.key(XK["Shift_L"], SHIFT_MASK, True)
                hist.append(f"S-{c}")
            elif r < 0.88:
                ic.tap(XK["space"]); hist.append("SPC")
            elif r < 0.93:
                ic.tap(XK["BackSpace"]); hist.append("BS")
            elif r < 0.95:
                k = rng.choice(["Left", "Right", "Up", "Down", "Tab"]); ic.tap(XK[k]); hist.append(k)
            elif r < 0.97:
                c = rng.choice(".,?!;:'\"-"); ic.tap(ord(c)); hist.append(c)
            elif r < 0.985:
                c = rng.choice("0123456789"); ic.tap(ord(c)); hist.append(c)
            elif r < 0.995:
                ic.tap(XK["Return"]); hist.append("RET")
            else:  # Ctrl+BackSpace (word delete) — handled by riti
                ic.key(XK["Control_L"])
                ic.tap(XK["BackSpace"], CTRL_MASK)
                ic.key(XK["Control_L"], CTRL_MASK, True)
                hist.append("C-BS")
            hist = hist[-12:]
            dt = time.monotonic() - t0
            worst = max(worst, dt)
            if dt > 0.05:
                slow += 1
        except GLib.Error as e:
            errors += 1
            if errors > 5:
                return False, f"aborted after {i} keys: {e.message}"
        if i % a.check_every == 0:
            pump(1)
            if ic.im is not None and ic.im != IM:
                # our own context switched IM: a real loss
                lost += 1
                lost_ctx.append(f"key#{i} → {ic.im} after: {' '.join(hist)}")
                activate(fx, ic)
            elif fx.current_im() != IM:
                # another context (a real app window) has focus: not our loss
                stolen += 1
                ic.focus_in()
    elapsed = time.monotonic() - t_start
    pid1 = fx.owner_pid()
    rss1 = rss_kib(pid1)
    ok = lost == 0 and errors == 0 and pid1 == pid0 and (rss0 < 0 or rss1 - rss0 < 50_000)
    return ok, (f"{a.keys} keys in {elapsed:.1f}s ({a.keys/elapsed:.0f}/s), "
                f"commits={len(ic.commits)}, own IM lost {lost}×, focus taken by other windows {stolen}×, D-Bus errors {errors}, "
                f"slow(>50ms) {slow}, worst {worst*1000:.1f}ms, "
                f"fcitx pid {pid0}→{pid1}, RSS {rss0}→{rss1} KiB"
                + "".join(f"\n        lost: {c}" for c in lost_ctx[:10]))


def sc_burst(fx, ic, a):
    assert activate(fx, ic), "could not activate openbangla"
    ic.commits.clear()
    words = ["ami", "tumi", "bangla", "valobasi", "kOthay", "jabe", "SHokal", "rat"]
    t0 = time.monotonic()
    n = 0
    missing = []
    for rnd in range(a.burst):
        for w in words:
            before = len([c for c in ic.commits if c.strip()])
            for ch in w:
                if ch.isupper():
                    ic.key(XK["Shift_L"])
                    ic.tap(ord(ch), SHIFT_MASK)
                    ic.key(XK["Shift_L"], SHIFT_MASK, True)
                else:
                    ic.tap(ord(ch))
                n += 1
            ic.tap(XK["space"])
            n += 1
            pump(2)
            if len([c for c in ic.commits if c.strip()]) == before:
                missing.append(f"round {rnd} '{w}' (own IM {ic.im}, focused IM {fx.current_im()}, "
                               f"last commits {ic.commits[-2:]})")
    pump(50)
    dt = time.monotonic() - t0
    expected_words = a.burst * len(words)
    got = len([c for c in ic.commits if c.strip()])
    ok = got == expected_words and fx.current_im() == IM
    return ok, (f"{n} keys in {dt:.2f}s ({dt/n*1000:.2f} ms/key), "
                f"committed {got}/{expected_words} words, IM now '{fx.current_im()}'"
                + "".join(f"\n        missing: {m}" for m in missing[:10]))


SCENARIOS = {"shift-tap": sc_shift_tap, "new-ic": sc_new_ic, "refocus": sc_refocus,
             "soak": sc_soak, "burst": sc_burst}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SCENARIOS))
    ap.add_argument("--keys", type=int, default=20000)
    ap.add_argument("--refocus", type=int, default=500)
    ap.add_argument("--burst", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--check-every", type=int, default=200,
                    help="soak: check the current IM every N keys (1 = after every key)")
    a = ap.parse_args()

    fx = Fcitx()
    group = fx.ctrl("CurrentInputMethodGroup", reply="(s)")[0]
    layout, items = fx.ctrl("InputMethodGroupInfo", "(s)", (group,), "(sa(ss))")
    saved = None
    if IM not in [n for n, _ in items]:
        saved = (group, layout, items)
        fx.ctrl("SetInputMethodGroupInfo", "(ssa(ss))", (group, layout, items + [(IM, "")]))
        pump(300)
        print(f"note: added {IM} to group '{group}' temporarily", file=sys.stderr)

    ic = IC(fx, "obk-stress")
    failed = 0
    try:
        for name in a.only.split(","):
            try:
                ok, detail = SCENARIOS[name](fx, ic, a)
            except AssertionError as e:
                ok, detail = False, str(e)
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {name:10s} {detail}", flush=True)
    finally:
        ic.focus_out()
        ic.destroy()
        if saved:
            fx.ctrl("SetInputMethodGroupInfo", "(ssa(ss))", saved)
            print(f"note: restored group '{group}'", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
