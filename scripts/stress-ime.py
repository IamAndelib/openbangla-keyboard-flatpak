#!/usr/bin/env python3
"""Reliability, pressure and regression tests for the OpenBangla Fcitx5 engine.

Drives Fcitx5 through its D-Bus input-context frontend (the API the GTK/Qt
im-modules and the portal use). Every scenario runs in a fresh input context and
checks that the Fcitx5 daemon is still alive afterwards. Pass criteria describe
the CORRECT behaviour, so scenarios for known bugs FAIL until the bug is fixed.

Runs only inside scripts/stress-isolated.sh (private bus + private XDG dirs,
STRESS_ISOLATED=1 and STRESS_RUN_DIR set). Pass --live to override; never use
--live on a desktop someone is using.

Behaviour scenarios
  shift-tap     a Left-Shift tap alone must not switch IM                 (config)
  new-ic        a new context (window/app) must start in openbangla       (config)
  refocus       FocusOut/FocusIn ×N keeps the IM
  soak          N random keys (letters, Shift+caps, space, BS, arrows, punctuation,
                digits, Return, Ctrl+BS); IM never lost, no errors, daemon alive
  burst         words typed back-to-back; every word committed, same output each round
Regression scenarios (docs/research.md §6.1)
  persist-empty     F1  `:)` + literal pick saves {":":""}; `:e` must not crash
  two-ic            F2  keys in context B while A is mid-word must not crash
  corrupt-selection F3  truncated phonetic-candidate-selection.json        [seeded]
  unwritable-selection F3 selection file path is a directory               [seeded]
  invalid-layout    F3  Keyboard.conf points at a torn user-imported layout [seeded]
  torn-autocorrect  F3  truncated user autocorrect.json                    [seeded]
  page-commit       F4  Space after paging the candidate list must commit
  suffix-dup        F5  learned selections must not store doubled values
  deactivate-midword F6 switching IM mid-word must commit the pending word
  reload-count      F7  Keyboard.conf must not be re-read at every word start [seeded]
  rss-slope         F8  RSS growth per 25k keys must stay under a threshold
  selection-growth  F9  (info) size of the learned-selection file after N keys
[seeded] scenarios prepare files BEFORE the daemon starts (riti reads them when
the add-on loads, which happens at startup when openbangla is in the profile):
stress-isolated.sh runs `stress-ime.py --prepare` first. They must be the only
scenario in their run (scripts/regress.sh starts one daemon per scenario).
(A layout path that doesn't exist is safe: riti keeps the previous layout.)
"""
import argparse
import json
import os
import random
import sys
import time
import unicodedata

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = "org.fcitx.Fcitx5"
IM_IFACE = "org.fcitx.Fcitx.InputMethod1"
IC_IFACE = "org.fcitx.Fcitx.InputContext1"
CTRL = "/controller"
CTRL_IFACE = "org.fcitx.Fcitx.Controller1"
IM = "openbangla"
# Preedit | FormattedPreedit | ClientUnfocusCommit | SurroundingText: what the
# Wayland frontend advertises. 0 would hide the preedit/focus-out code paths.
WAYLAND_CAPS = 0x72

XK = {"space": 0x20, "Return": 0xFF0D, "BackSpace": 0xFF08, "Tab": 0xFF09,
      "Left": 0xFF51, "Up": 0xFF52, "Right": 0xFF53, "Down": 0xFF54,
      "Shift_L": 0xFFE1, "Control_L": 0xFFE3}
SHIFT_MASK, CTRL_MASK = 1 << 0, 1 << 2

RUN_DIR = os.environ.get("STRESS_RUN_DIR", "")
DATA_DIR = os.path.join(RUN_DIR, "data", "openbangla-keyboard")
OBK_CONF = os.path.join(RUN_DIR, "config", "OpenBangla", "Keyboard.conf")
SELECTION = os.path.join(DATA_DIR, "phonetic-candidate-selection.json")
LOG = os.path.join(RUN_DIR, "fcitx5.log")


def nfc(t):
    return unicodedata.normalize("NFC", t)


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

    def alive(self):
        """PID of the daemon owning org.fcitx.Fcitx5, or None if it is gone."""
        try:
            r = self.conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                    "org.freedesktop.DBus", "GetConnectionUnixProcessID",
                                    GLib.Variant("(s)", (BUS,)), GLib.VariantType("(u)"),
                                    Gio.DBusCallFlags.NONE, 2000, None)
            return r.unpack()[0]
        except GLib.Error:
            return None


def pump(ms=10):
    ctx = GLib.MainContext.default()
    end = GLib.get_monotonic_time() + ms * 1000
    while GLib.get_monotonic_time() < end:
        ctx.iteration(False)


class IC:
    def __init__(self, fx, name, caps):
        self.fx = fx
        self.path, _ = fx.call("/org/freedesktop/portal/inputmethod", IM_IFACE,
                               "CreateInputContext", "(a(ss))",
                               ([("program", name), ("display", "")],), "(oay)")
        self.commits = []
        self.preedit = ""
        self.im = None  # this context's own IM, from its CurrentIM signal
        sub = fx.conn.signal_subscribe
        sub(BUS, IC_IFACE, "CommitString", self.path, None, Gio.DBusSignalFlags.NONE,
            lambda *a: self.commits.append(a[5].unpack()[0]))
        sub(BUS, IC_IFACE, "CurrentIM", self.path, None, Gio.DBusSignalFlags.NONE,
            self._on_im)
        sub(BUS, IC_IFACE, "UpdateFormattedPreedit", self.path, None,
            Gio.DBusSignalFlags.NONE, self._on_preedit)
        fx.call(self.path, IC_IFACE, "SetCapability", "(t)", (caps,))

    def _on_im(self, *a):
        self.im = a[5].unpack()[1]  # (name, uniqueName, langCode)

    def _on_preedit(self, *a):
        self.preedit = "".join(seg for seg, _fmt in a[5].unpack()[0])

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
        pump(2)
        return a

    def type(self, text):
        """Type ASCII text the way a user would (Shift held for capitals and shifted symbols)."""
        for ch in text:
            if ch.isupper() or ch in ':)(!@#$%^&*_+{}|"<>?~':
                self.key(XK["Shift_L"])
                self.tap(ord(ch), SHIFT_MASK)
                self.key(XK["Shift_L"], SHIFT_MASK, True)
            elif ch == " ":
                self.tap(XK["space"])
            else:
                self.tap(ord(ch))
        pump(10)

    def page_next(self):
        self.fx.call(self.path, IC_IFACE, "NextPage")
        pump(10)

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
    except (OSError, TypeError):
        pass
    return -1


def activate(fx, ic):
    ic.focus_in()
    fx.ctrl("SetCurrentIM", "(s)", (IM,))
    pump(30)
    return fx.current_im() == IM


def words(ic):
    return [nfc(c.strip()) for c in ic.commits if c.strip()]


def selection_values():
    try:
        with open(SELECTION, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def log_count(needle):
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            return sum(needle in line for line in f)
    except OSError:
        return 0


# ------------------------------------------------------- behaviour scenarios

def sc_shift_tap(fx, ic, _a):
    assert activate(fx, ic), "could not activate openbangla"
    results = []
    for hold in (0.03, 0.10, 0.20, 0.40):
        activate(fx, ic)
        ic.tap(XK["Shift_L"], hold=hold)
        pump(30)
        results.append((hold, fx.current_im()))
    ok = all(im == IM for _h, im in results)
    return ok, ", ".join(f"{int(h*1000)}ms:{im}" for h, im in results)


def sc_new_ic(fx, ic, a):
    assert activate(fx, ic), "could not activate openbangla"
    other = IC(fx, "obk-stress-second-window", a.caps)
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
    for _ in range(a.refocus):
        ic.focus_out()
        ic.focus_in()
        if fx.current_im() != IM:
            lost += 1
            activate(fx, ic)
    return lost == 0, f"{a.refocus} focus cycles, IM lost {lost} times"


ALPHA = "abcdefghijklmnopqrstuvwxyz"
SHIFTABLE = "TDNSRGOIUJKY"  # Avro uses these capitals


def random_key(rng, ic, hist):
    r = rng.random()
    if r < 0.70:
        c = rng.choice(ALPHA); ic.tap(ord(c)); hist.append(c)
    elif r < 0.78:
        c = rng.choice(SHIFTABLE)
        ic.key(XK["Shift_L"]); ic.tap(ord(c), SHIFT_MASK); ic.key(XK["Shift_L"], SHIFT_MASK, True)
        hist.append(f"S-{c}")
    elif r < 0.88:
        ic.tap(XK["space"]); hist.append("SPC")
    elif r < 0.93:
        ic.tap(XK["BackSpace"]); hist.append("BS")
    elif r < 0.95:
        k = rng.choice(["Left", "Right", "Up", "Down", "Tab"]); ic.tap(XK[k]); hist.append(k)
    elif r < 0.97:
        c = rng.choice(".,?!;'-"); ic.tap(ord(c)); hist.append(c)
    elif r < 0.985:
        c = rng.choice("0123456789"); ic.tap(ord(c)); hist.append(c)
    elif r < 0.995:
        ic.tap(XK["Return"]); hist.append("RET")
    else:
        ic.key(XK["Control_L"]); ic.tap(XK["BackSpace"], CTRL_MASK)
        ic.key(XK["Control_L"], CTRL_MASK, True)
        hist.append("C-BS")
    del hist[:-12]


def sc_soak(fx, ic, a):
    rng = random.Random(a.seed)
    assert activate(fx, ic), "could not activate openbangla"
    pid0 = fx.alive()
    rss0 = rss_kib(pid0)
    lost, errors, slow, stolen = 0, 0, 0, 0
    worst = 0.0
    hist, lost_ctx = [], []
    t_start = time.monotonic()
    for i in range(a.keys):
        try:
            t0 = time.monotonic()
            random_key(rng, ic, hist)
            dt = time.monotonic() - t0
            worst = max(worst, dt)
            slow += dt > 0.05
        except GLib.Error as e:
            errors += 1
            if errors > 5 or fx.alive() is None:
                return False, f"aborted after {i} keys: {e.message[:120]}"
        if i % a.check_every == 0:
            pump(1)
            if ic.im is not None and ic.im != IM:
                lost += 1
                lost_ctx.append(f"key#{i} → {ic.im} after: {' '.join(hist)}")
                activate(fx, ic)
            elif fx.current_im() != IM:
                stolen += 1  # another context has focus: impossible when isolated
                ic.focus_in()
    elapsed = time.monotonic() - t_start
    pid1 = fx.alive()
    rss1 = rss_kib(pid1)
    isolated = os.environ.get("STRESS_ISOLATED") == "1"
    ok = (lost == 0 and errors == 0 and pid1 == pid0 and not (isolated and stolen))
    return ok, (f"{a.keys} keys in {elapsed:.1f}s ({a.keys/elapsed:.0f}/s), commits={len(ic.commits)}, "
                f"own IM lost {lost}×, focus stolen {stolen}×, D-Bus errors {errors}, "
                f"slow(>50ms) {slow}, worst {worst*1000:.1f}ms, pid {pid0}→{pid1}, RSS {rss0}→{rss1} KiB"
                + "".join(f"\n        lost: {c}" for c in lost_ctx[:10]))


BURST_WORDS = ["ami", "tumi", "bangla", "valobasi", "kOthay", "jabe", "SHokal", "rat"]
BURST_KNOWN = {"ami": "আমি", "tumi": "তুমি", "bangla": "বাংলা"}


def sc_burst(fx, ic, a):
    assert activate(fx, ic), "could not activate openbangla"
    ic.commits.clear()
    t0 = time.monotonic()
    n = 0
    first, problems = {}, []
    for rnd in range(a.burst):
        for w in BURST_WORDS:
            before = len(ic.commits)
            ic.type(w + " ")
            n += len(w) + 1
            got = "".join(c for c in ic.commits[before:]).strip()
            if not got:
                problems.append(f"round {rnd} '{w}': nothing committed")
                continue
            first.setdefault(w, got)
            if nfc(got) != nfc(first[w]):
                problems.append(f"round {rnd} '{w}': '{got}' ≠ first round '{first[w]}'")
            if w in BURST_KNOWN and nfc(got) != nfc(BURST_KNOWN[w]):
                problems.append(f"round {rnd} '{w}': '{got}' ≠ expected '{BURST_KNOWN[w]}'")
    dt = time.monotonic() - t0
    ok = not problems and fx.current_im() == IM
    return ok, (f"{n} keys in {dt:.2f}s ({dt/n*1000:.2f} ms/key), {a.burst*len(BURST_WORDS)} words, "
                f"{len(problems)} problems, IM '{fx.current_im()}'"
                + "".join(f"\n        {p}" for p in problems[:10]))


# ------------------------------------------------------ regression scenarios

def sc_persist_empty(fx, ic, _a):
    """F1: `:)` + literal candidate stores {":": ""}; a later `:e` must not abort fcitx5."""
    assert activate(fx, ic)
    ic.type(":)")
    ic.tap(XK["Right"])          # pick the literal candidate instead of the emoji
    ic.tap(XK["space"])
    pump(30)
    stored = selection_values()
    try:
        ic.type(":e ")
    except GLib.Error:
        pass
    pump(300)
    empty = {k: v for k, v in stored.items() if not k or not v}
    ok = fx.alive() is not None and not empty
    return ok, f"stored after `:)`: {stored}; daemon alive after `:e`: {fx.alive() is not None}"


def sc_two_ic(fx, ic, a):
    """F2: B gets keys while A is mid-word (two contexts focused, as across focus groups)."""
    b = IC(fx, "obk-stress-b", a.caps)
    try:
        b.focus_in()
        fx.ctrl("SetCurrentIM", "(s)", (IM,))
        pump(30)
        ic.focus_in()
        fx.ctrl("SetCurrentIM", "(s)", (IM,))
        pump(30)
        ic.type("am")
        try:
            b.tap(ord("i"))
            b.tap(XK["space"])
        except GLib.Error:
            pass
        pump(300)
        alive = fx.alive() is not None
        return alive, f"daemon alive: {alive}; A commits {words(ic)}, B commits {words(b) if alive else '-'}"
    finally:
        b.destroy()


def _type_word_survives(fx, ic, word, expect=None):
    assert activate(fx, ic)
    try:
        ic.type(word + " ")
    except GLib.Error:
        pass
    pump(300)
    alive = fx.alive() is not None
    got = words(ic) if alive else []
    ok = alive and (expect is None or nfc(expect) in got)
    return ok, f"daemon alive: {alive}; commits {got}"


def seed_corrupt_selection():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SELECTION, "w", encoding="utf-8") as f:
        f.write('{"ami": "আ')  # torn write


def sc_corrupt_selection(fx, ic, _a):
    """F3: a truncated selection file must not abort fcitx5 when the add-on loads."""
    return _type_word_survives(fx, ic, "ami", "আমি")


def seed_unwritable_selection():
    os.makedirs(SELECTION, exist_ok=True)  # path exists but is a directory → write fails


def sc_unwritable_selection(fx, ic, _a):
    """F3: failing to save a learned selection must not abort fcitx5."""
    assert activate(fx, ic)
    try:
        ic.type("kotha")
        ic.tap(XK["Right"])  # non-default pick → riti saves the selection file
        ic.tap(XK["space"])
        ic.type("ami ")
    except GLib.Error:
        pass
    pump(300)
    alive = fx.alive() is not None
    return alive, f"daemon alive: {alive}; commits {words(ic) if alive else '-'}"


def seed_invalid_layout():
    layouts = os.path.join(DATA_DIR, "layouts")
    os.makedirs(layouts, exist_ok=True)
    broken = os.path.join(layouts, "Broken.json")
    with open(broken, "w", encoding="utf-8") as f:
        f.write('{"info": {"layout": {"name": "Brok')  # torn import
    os.makedirs(os.path.dirname(OBK_CONF), exist_ok=True)
    with open(OBK_CONF, "w") as f:
        f.write(f"[layout]\npath={broken}\n")


def sc_invalid_layout(fx, ic, _a):
    """F3: an unparsable layout file must fall back (to Avro phonetic), not abort."""
    return _type_word_survives(fx, ic, "ami", "আমি")


def seed_torn_autocorrect():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "autocorrect.json"), "w", encoding="utf-8") as f:
        f.write('{"amar": "আমা')


def sc_torn_autocorrect(fx, ic, _a):
    """F3: a truncated user autocorrect file must not abort fcitx5."""
    ok1, d1 = _type_word_survives(fx, ic, "ami", "আমি")
    ok2, d2 = _type_word_survives(fx, ic, "tumi", "তুমি") if ok1 else (False, "")
    return ok1 and ok2, d2 or d1


def sc_page_commit(fx, ic, _a):
    """F4: Space after NextPage must commit the word and end the session."""
    assert activate(fx, ic)
    ic.type("kotha")
    ic.page_next()
    ic.tap(XK["space"])
    pump(30)
    after_page = words(ic)
    ic.type("r ")
    pump(30)
    final = words(ic)
    ok = len(after_page) == 1 and len(final) == 2 and final[1] == nfc("র")
    return ok, f"after NextPage+Space: {after_page}; after 'r'+Space: {final}"


def sc_suffix_dup(fx, ic, _a):
    """F5: deriving selections for suffixed words must not store doubled values."""
    assert activate(fx, ic)
    ic.type("ami")
    ic.tap(XK["Right"]); ic.tap(XK["Right"])   # learn a non-default candidate for "ami"
    ic.tap(XK["space"])
    for w in ("amie", "amier", "amiera"):
        ic.type(w + " ")   # default commit; differs from the derived preselection → saved
    pump(50)
    sel = selection_values()
    doubled = {k: v for k, v in sel.items()
               if v and len(v) % 2 == 0 and v[: len(v) // 2] == v[len(v) // 2:]}
    return not doubled, f"selections {sel}; doubled {doubled}"


def sc_deactivate_midword(fx, ic, _a):
    """F6: Ctrl+Space with a pending word must commit it, not drop it."""
    assert activate(fx, ic)
    ic.type("ami")
    pending = ic.preedit
    ic.key(XK["Control_L"])
    ic.tap(XK["space"], CTRL_MASK)
    ic.key(XK["Control_L"], CTRL_MASK, True)
    pump(50)
    got = words(ic)
    ok = nfc("আমি") in got
    return ok, f"preedit before switch '{pending}', IM now '{fx.current_im()}', commits {got}"


def seed_keyboard_conf():
    os.makedirs(os.path.dirname(OBK_CONF), exist_ok=True)
    with open(OBK_CONF, "w") as f:
        f.write("[layout]\nname=Avro Phonetic\npath=avro_phonetic\n")  # as the GUI writes it


def sc_reload_count(fx, ic, _a):
    """F7: Keyboard.conf should be read once, not at every word start."""
    assert activate(fx, ic)
    ic.type("x ")  # make sure the add-on is loaded and has done its initial read
    before = log_count("Reload openbangla configuration")
    for w in ("ami", "tumi", "se", "ora", "amra", "tara", "kal", "aj", "ekhon", "pore"):
        ic.type(w + " ")
    for _ in range(5):
        ic.tap(XK["Left"])
    pump(100)
    n = log_count("Reload openbangla configuration") - before
    return n <= 1, f"{n} config reloads while typing 10 words + 5 arrows (log: fcitx5.log)"


def sc_rss_slope(fx, ic, a):
    """F8: RSS growth per 25k random keys after warm-up must stay under --rss-slope KiB."""
    assert activate(fx, ic)
    rng = random.Random(a.seed)
    pid = fx.alive()
    samples, hist = [], []
    for chunk in range(a.chunks):
        for _ in range(25000):
            random_key(rng, ic, hist)
        pump(5)
        samples.append(rss_kib(pid))
        if fx.alive() != pid:
            return False, f"daemon changed/died after chunk {chunk}"
    ys = samples[1:]  # drop warm-up chunk
    n = len(ys)
    xbar, ybar = (n - 1) / 2, sum(ys) / n
    slope = (sum((i - xbar) * (y - ybar) for i, y in enumerate(ys))
             / max(1e-9, sum((i - xbar) ** 2 for i in range(n))))
    return slope < a.rss_slope, f"RSS KiB per chunk {samples}; slope {slope:.0f} KiB/25k keys (limit {a.rss_slope})"


def sc_selection_growth(fx, ic, a):
    """F9 (info): learned-selection file size after N random keys."""
    assert activate(fx, ic)
    rng = random.Random(a.seed)
    hist = []
    for _ in range(a.keys):
        random_key(rng, ic, hist)
    pump(50)
    sel = selection_values()
    size = os.path.getsize(SELECTION) if os.path.isfile(SELECTION) else 0
    return True, f"INFO {len(sel)} entries, {size} bytes after {a.keys} keys"


SCENARIOS = {
    "shift-tap": sc_shift_tap, "new-ic": sc_new_ic, "refocus": sc_refocus,
    "soak": sc_soak, "burst": sc_burst,
    "persist-empty": sc_persist_empty, "two-ic": sc_two_ic,
    "corrupt-selection": sc_corrupt_selection, "unwritable-selection": sc_unwritable_selection,
    "invalid-layout": sc_invalid_layout, "torn-autocorrect": sc_torn_autocorrect,
    "page-commit": sc_page_commit, "suffix-dup": sc_suffix_dup,
    "deactivate-midword": sc_deactivate_midword, "reload-count": sc_reload_count,
    "rss-slope": sc_rss_slope, "selection-growth": sc_selection_growth,
}
SEEDS = {"corrupt-selection": seed_corrupt_selection,
         "unwritable-selection": seed_unwritable_selection,
         "invalid-layout": seed_invalid_layout,
         "torn-autocorrect": seed_torn_autocorrect,
         "reload-count": seed_keyboard_conf}
BEHAVIOUR = ["shift-tap", "new-ic", "refocus", "soak", "burst"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(BEHAVIOUR))
    ap.add_argument("--keys", type=int, default=20000)
    ap.add_argument("--refocus", type=int, default=500)
    ap.add_argument("--burst", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--chunks", type=int, default=6, help="rss-slope: number of 25k-key chunks")
    ap.add_argument("--rss-slope", type=float, default=256.0, help="rss-slope: KiB per 25k keys")
    ap.add_argument("--caps", type=lambda s: int(s, 0), default=WAYLAND_CAPS)
    ap.add_argument("--check-every", type=int, default=50,
                    help="soak: check the context's IM every N keys (1 = after every key)")
    ap.add_argument("--prepare", action="store_true",
                    help="only create the files a seeded scenario needs, then exit "
                         "(stress-isolated.sh calls this before starting Fcitx5)")
    ap.add_argument("--live", action="store_true",
                    help="allow running against a non-isolated Fcitx5 (dangerous)")
    a = ap.parse_args()

    if os.environ.get("STRESS_ISOLATED") != "1" and not a.live:
        sys.exit("refusing: run through scripts/stress-isolated.sh (or pass --live knowingly)")
    names = a.only.split(",")
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        sys.exit(f"unknown scenarios: {unknown}")
    seeded = [n for n in names if n in SEEDS]
    if seeded and len(names) > 1:
        sys.exit(f"seeded scenario(s) {seeded} must run alone (use scripts/regress.sh)")
    if a.prepare:
        if seeded:
            if not RUN_DIR:
                sys.exit("seeded scenarios need STRESS_RUN_DIR")
            SEEDS[seeded[0]]()
        return 0

    fx = Fcitx()
    pump(500)
    if fx.alive() is None:  # e.g. the add-on aborted while loading seeded files
        for name in names:
            print(f"FAIL  {name:20s} daemon not running: it died during startup/add-on load "
                  f"(see {os.path.join(RUN_DIR, 'fcitx5.log')})", flush=True)
        return 1
    group = fx.ctrl("CurrentInputMethodGroup", reply="(s)")[0]
    layout, items = fx.ctrl("InputMethodGroupInfo", "(s)", (group,), "(sa(ss))")
    if IM not in [n for n, _ in items]:
        fx.ctrl("SetInputMethodGroupInfo", "(ssa(ss))", (group, layout, items + [(IM, "")]))
        pump(300)

    failed = 0
    for name in names:
        pid0 = fx.alive()
        ic = IC(fx, f"obk-stress-{name}", a.caps)
        try:
            ok, detail = SCENARIOS[name](fx, ic, a)
        except AssertionError as e:
            ok, detail = False, f"setup failed: {e}"
        except GLib.Error as e:
            ok, detail = False, f"D-Bus error: {e.message[:160]}"
        pid1 = fx.alive()
        if pid1 != pid0:
            ok, detail = False, f"daemon died or restarted (pid {pid0}→{pid1}); {detail}"
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:20s} {detail}", flush=True)
        if pid1 is None:
            break
        try:
            ic.focus_out()
        except GLib.Error:
            pass
        ic.destroy()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
