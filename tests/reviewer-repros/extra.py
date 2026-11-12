#!/usr/bin/env python3
"""Extra probe scenarios (prototype, isolated bus only)."""
import os, sys, time, json, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stress_copy import Fcitx, IC, pump, XK, SHIFT_MASK, CTRL_MASK, IM, activate, rss_kib  # noqa
from gi.repository import Gio, GLib

PREEDIT, FMT, UNFOCUS, SURR = 1 << 1, 1 << 4, 1 << 5, 1 << 6
WAYLAND_CAPS = PREEDIT | FMT | SURR | UNFOCUS   # waylandimserver.cpp baseFlags
REPEAT = 1 << 31
ALT_MASK = 1 << 3


class IC2(IC):
    def __init__(self, fx, name, caps=0):
        super().__init__(fx, name)
        self.preedit = ""
        fx.conn.signal_subscribe("org.fcitx.Fcitx5", "org.fcitx.Fcitx.InputContext1",
                                 "UpdateFormattedPreedit", self.path, None,
                                 Gio.DBusSignalFlags.NONE, self._pe)
        fx.call(self.path, "org.fcitx.Fcitx.InputContext1", "SetCapability", "(t)", (caps,))

    def _pe(self, *a):
        segs, _cur = a[5].unpack()
        self.preedit = "".join(s for s, _ in segs)

    def type(self, s):
        for ch in s:
            if ch.isupper():
                self.key(XK["Shift_L"]); self.tap(ord(ch), SHIFT_MASK); self.key(XK["Shift_L"], SHIFT_MASK, True)
            else:
                self.tap(XK["space"] if ch == " " else ord(ch))
        pump(20)


def setim(fx, ic):
    ic.focus_in(); fx.ctrl("SetCurrentIM", "(s)", (IM,)); pump(30)


def out(name, msg):
    print(f"{name:22s} {msg}", flush=True)


def sc_midword_shift(fx):
    for caps, label in ((0, "caps=0"), (WAYLAND_CAPS, "caps=wayland")):
        ic = IC2(fx, f"mw-{caps}", caps); setim(fx, ic)
        ic.commits.clear(); ic.type("ami"); pe = ic.preedit
        ic.tap(XK["Shift_L"], hold=0.05); pump(50)
        out("midword-shift", f"{label}: preedit-before={pe!r} commits-after-tap={ic.commits} "
            f"preedit-after={ic.preedit!r} im={fx.current_im()}")
        ic.focus_out(); ic.destroy()


def sc_focusout_preedit(fx):
    for caps, label in ((0, "caps=0"), (PREEDIT, "caps=Preedit"), (WAYLAND_CAPS, "caps=wayland(+UnfocusCommit)")):
        ic = IC2(fx, f"fo-{caps}", caps); setim(fx, ic)
        ic.commits.clear(); ic.type("bangla"); pe = ic.preedit
        ic.focus_out(); pump(50)
        out("focusout-preedit", f"{label}: preedit={pe!r} commits-on-focusout={ic.commits}")
        # does the riti session survive? refocus and type space
        ic.focus_in(); pump(20); ic.commits.clear(); ic.tap(XK["space"]); pump(30)
        out("", f"  after refocus+space commits={ic.commits}")
        ic.focus_out(); ic.destroy()


def sc_ctrl_space(fx):
    ic = IC2(fx, "cs", WAYLAND_CAPS); setim(fx, ic)
    ic.key(XK["Control_L"]); ic.tap(XK["space"], CTRL_MASK); ic.key(XK["Control_L"], CTRL_MASK, True); pump(30)
    out("ctrl-space", f"im after Ctrl+Space = {fx.current_im()} (own {ic.im})")
    ic.focus_out(); ic.destroy()


def sc_two_ic(fx):
    # Variant 1: both focused (isolated D-Bus ICs have no focus group), interleave.
    a = IC2(fx, "A", WAYLAND_CAPS); b = IC2(fx, "B", WAYLAND_CAPS)
    setim(fx, a); setim(fx, b)
    a.commits.clear(); b.commits.clear()
    a.type("am"); pa = a.preedit
    b.type("i"); pb = b.preedit
    b.tap(XK["space"]); pump(30); a.tap(XK["space"]); pump(30)
    out("two-ic-both-focused", f"A preedit {pa!r}; B preedit after 'i' {pb!r}; "
        f"A commits {a.commits} A preedit now {a.preedit!r}; B commits {b.commits}")
    for x in (a, b):
        x.focus_out(); x.destroy()


def sc_two_ic_switch(fx):
    a = IC2(fx, "A", WAYLAND_CAPS); b = IC2(fx, "B", WAYLAND_CAPS)
    setim(fx, a); a.focus_out(); setim(fx, b); b.focus_out()
    a.commits.clear(); b.commits.clear()
    a.focus_in(); a.type("am"); a.focus_out(); b.focus_in(); b.type("i "); a.focus_in(); a.tap(XK["space"]); pump(30)
    out("two-ic-focus-switch", f"A commits {a.commits}; B commits {b.commits}")
    for x in (a, b):
        x.focus_out(); x.destroy()


def sc_repeat(fx):
    ic = IC2(fx, "rep", WAYLAND_CAPS); setim(fx, ic); ic.commits.clear()
    ic.key(ord("k"))
    t0 = time.monotonic()
    for _ in range(200):
        ic.key(ord("k"), REPEAT)
    ic.key(ord("k"), 0, True); t1 = time.monotonic()
    pe = ic.preedit
    for _ in range(100):  # held BackSpace
        ic.key(XK["BackSpace"], REPEAT)
    ic.key(XK["BackSpace"], 0, True)
    pump(20)
    out("autorepeat", f"201 'k' (200 with Repeat flag) in {(t1-t0)*1000:.0f}ms; preedit len {len(pe)} "
        f"head {pe[:8]!r}; after 100 repeated BS preedit len {len(ic.preedit)}; im {fx.current_im()}")
    ic.tap(XK["space"]); ic.focus_out(); ic.destroy()


def sc_long_word(fx):
    ic = IC2(fx, "long", WAYLAND_CAPS); setim(fx, ic)
    pat = "amarsonarbangla"
    for n in (20, 50, 100, 200, 400):
        ic.commits.clear()
        worst, t0 = 0.0, time.monotonic()
        for i in range(n):
            k0 = time.monotonic(); ic.tap(ord(pat[i % len(pat)])); worst = max(worst, time.monotonic() - k0)
        dt = time.monotonic() - t0
        ic.tap(XK["space"]); pump(20)
        L = len(ic.commits[0]) if ic.commits else 0
        out("long-word", f"{n} chars: total {dt*1000:.0f}ms, worst key {worst*1000:.1f}ms, committed len {L}")
    ic.focus_out(); ic.destroy()


def sc_altgr(fx):
    ic = IC2(fx, "altgr", WAYLAND_CAPS); setim(fx, ic); ic.commits.clear()
    ic.type("ami "); base = list(ic.commits); ic.commits.clear()
    ic.key(0xFFEA)  # Alt_R pressed, release lost (e.g. AltGr+Tab / focus moved)
    ic.type("ami ")
    out("altgr-stuck", f"normal {base}; after Alt_R press w/o release: {ic.commits}")
    ic.focus_out(); ic.focus_in(); ic.commits.clear(); ic.type("ami ")
    out("", f"  after focus cycle: {ic.commits}")
    ic.focus_out(); ic.destroy()


def sc_config_reload(fx):
    w = os.environ["W"]
    conf = os.path.join(w, "config", "OpenBangla"); os.makedirs(conf, exist_ok=True)
    ic = IC2(fx, "cfg", WAYLAND_CAPS); setim(fx, ic); ic.commits.clear()
    ic.type("ami "); a = list(ic.commits); ic.commits.clear()
    ic.type("am")  # mid-word
    with open(os.path.join(conf, "Keyboard.conf"), "w") as f:
        f.write("[layout]\npath=/app/addons/OpenBangla/share/openbangla-keyboard/layouts/Probhat.json\n")
    ic.type("i "); mid = list(ic.commits); ic.commits.clear()
    ic.type("ami "); after = list(ic.commits); ic.commits.clear()
    with open(os.path.join(conf, "Keyboard.conf"), "w") as f:
        f.write("[layout]\npath=/nonexistent.json\n")
    time.sleep(0.01); ic.type("ami "); bad = list(ic.commits); ic.commits.clear()
    os.remove(os.path.join(conf, "Keyboard.conf"))
    ic.type("ami "); gone = list(ic.commits)
    out("config-reload", f"avro {a}; layout->Probhat mid-word {mid}; next word {after}; "
        f"bad path {bad}; conf deleted {gone}; pid alive {fx.owner_pid()}")
    ic.focus_out(); ic.destroy()


def sc_select_write(fx):
    """Choose a non-default candidate -> riti rewrites phonetic-candidate-selection.json."""
    ic = IC2(fx, "sel", WAYLAND_CAPS); setim(fx, ic); ic.commits.clear()
    pid = fx.owner_pid()
    try:
        ic.type("kotha"); ic.tap(XK["Right"]); ic.tap(XK["space"]); pump(50)
        out("select-write", f"commits {ic.commits}; pid {pid} -> {fx.owner_pid()}")
    except GLib.Error as e:
        out("select-write", f"D-Bus error after candidate change: {e.message}")


def sc_pidcheck(fx):
    pid = fx.owner_pid()
    comm = open(f"/proc/{pid}/comm").read().strip()
    out("pidcheck", f"owner_pid={pid} comm={comm} rss_kib(owner)={rss_kib(pid)}")


def sc_config_reload2(fx):
    w = os.environ["W"]
    conf = os.path.join(w, "config", "OpenBangla"); os.makedirs(conf, exist_ok=True)
    ic = IC2(fx, "cfg2", WAYLAND_CAPS); setim(fx, ic); ic.commits.clear()
    ic.type("kotha "); a = list(ic.commits); ic.commits.clear()
    ic.type("kot")
    with open(os.path.join(conf, "Keyboard.conf"), "w") as f:
        f.write("[layout]\npath=/app/addons/OpenBangla/share/openbangla-keyboard/layouts/Probhat.json\n")
    ic.type("ha "); mid = list(ic.commits); ic.commits.clear()
    ic.type("kotha "); after = list(ic.commits); ic.commits.clear()
    out("config-reload2", f"avro {a}; switched mid-word {mid}; next word {after}")
    ic.focus_out(); ic.destroy()


def sc_typecheck(fx):
    ic = IC2(fx, "tc", WAYLAND_CAPS); setim(fx, ic); ic.commits.clear()
    try:
        ic.type("ami "); out("typecheck", f"commits {ic.commits} im {fx.current_im()} pid {fx.owner_pid()}")
    except GLib.Error as e:
        out("typecheck", f"D-Bus error: {e.message}")


def sc_corrupt_autocorrect(fx):
    d = os.path.join(os.environ["W"], "data", "openbangla-keyboard")
    ic = IC2(fx, "ac", WAYLAND_CAPS); setim(fx, ic); ic.commits.clear()
    ic.type("ami "); ok = list(ic.commits); ic.commits.clear()
    time.sleep(0.05)
    with open(os.path.join(d, "autocorrect.json"), "w") as f:
        f.write('{"ami": "আম')   # torn write
    try:
        ic.type("tumi "); out("corrupt-autocorrect", f"before {ok}; after torn autocorrect.json: {ic.commits} pid {fx.owner_pid()}")
    except GLib.Error as e:
        out("corrupt-autocorrect", f"before {ok}; after torn autocorrect.json: D-Bus error {e.message}")


SC = {k[3:].replace("_", "-"): v for k, v in globals().items() if k.startswith("sc_")}

if __name__ == "__main__":
    fx = Fcitx()
    for n in (sys.argv[1].split(",") if len(sys.argv) > 1 else SC):
        try:
            SC[n](fx)
        except Exception as e:  # noqa
            out(n, f"EXCEPTION {type(e).__name__}: {e}")
