import sys, time
sys.path.insert(0, "${OBK_WS:-.}/scripts")
import importlib.util
spec = importlib.util.spec_from_file_location("st", "${OBK_WS:-.}/scripts/stress-ime.py")
st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
from gi.repository import Gio, GLib
fx = st.Fcitx(); ic = st.IC(fx, "obk-review"); assert st.activate(fx, ic)
S = st.SHIFT_MASK
def t(sym, state=0): ic.tap(sym, state); st.pump(5)
def typ(s):
    for c in s:
        if c == ':': t(0x3a, S)
        elif c == ')': t(0x29, S)
        else: t(ord(c))
def alive():
    try: return fx.owner_pid()
    except GLib.Error as e: return None
mode = sys.argv[1]
if mode == "dup":
    for w, rights in (("ami", 2), ("amie", 0), ("amier", 0)):
        typ(w); [t(st.XK["Right"]) for _ in range(rights)]; t(0x20); st.pump(30)
        print(f"{w!r:8} +{rights} Right + Space -> committed {ic.commits[-1]!r}")
elif mode == "crash":
    pid = alive(); print("fcitx5 pid", pid)
    typ(":)"); t(st.XK["Right"]); t(0x20); st.pump(30)
    print("committed", ic.commits[-1:], "alive:", alive())
    try:
        typ(":e")
    except GLib.Error as e:
        print("D-Bus error:", e.message[:100])
    time.sleep(0.5)
    print("after typing ':e' -> fcitx5 alive:", alive())
if mode == "twoic":
    b = st.IC(fx, "obk-review-b"); b.focus_in(); fx.ctrl("SetCurrentIM", "(s)", ("openbangla",)); st.pump(30)
    ic.focus_in()                     # A focused (no focus group in this harness, so B stays focused too)
    typ("am")                          # composing in A
    b.key(ord("i")); b.key(ord("i"), 0, True); st.pump(5)
    b.key(0x20); b.key(0x20, 0, True); st.pump(30)
    print("A commits:", ic.commits, " B commits:", b.commits)
if mode == "page":
    typ("kotha")
    fx.call(ic.path, st.IC_IFACE, "NextPage"); st.pump(10)     # what a mouse-wheel/page-arrow in the panel does
    acc = ic.key(0x20); ic.key(0x20, 0, True); st.pump(30)
    print("Space after NextPage: filtered =", acc, " commits so far:", ic.commits)
    typ("r"); acc = ic.key(0x20); ic.key(0x20, 0, True); st.pump(30)
    print("then 'r'+Space: filtered =", acc, " commits:", ic.commits)
if mode == "words":
    for w in ["ami", "tumi", "se", "ora", "amra"]:
        typ(w); t(0x20); st.pump(10)
    for _ in range(5): t(st.XK["Left"])   # arrows while not composing
    print("commits:", ic.commits)
