#!/usr/bin/env python3
"""Extra scenarios on top of scripts/stress-ime.py (imported, not modified)."""
import importlib.util, sys, time
WS = "${OBK_WS:-.}"
spec = importlib.util.spec_from_file_location("stress", WS + "/scripts/stress-ime.py")
st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
XK, CTRL, SHIFT = st.XK, st.CTRL_MASK, st.SHIFT_MASK
IM = st.IM

def ctrl_space(ic):
    ic.key(XK["Control_L"]); ic.key(XK["space"], CTRL); ic.key(XK["space"], CTRL, True)
    ic.key(XK["Control_L"], CTRL, True); st.pump(30)

def main():
    fx = st.Fcitx()
    # 1. first context ever, no SetCurrentIM: what does a fresh session start in?
    a = st.IC(fx, "app-a"); a.focus_in(); st.pump(50)
    print(f"INFO  fresh      first IC at startup starts in '{fx.current_im()}'")
    # 2. Ctrl+Space toggle round-trip
    st.activate(fx, a); ctrl_space(a); im1 = fx.current_im(); ctrl_space(a); im2 = fx.current_im()
    ok = im1 == "keyboard-us" and im2 == IM
    print(f"{'PASS' if ok else 'FAIL'}  ctrl-space after 1st: {im1}, after 2nd: {im2}")
    # 3. Shift_L tap after Shift+T combo (Avro capital) must not toggle; and text typed
    st.activate(fx, a); a.commits.clear()
    a.key(XK["Shift_L"]); a.key(ord("T"), SHIFT); a.key(ord("T"), SHIFT, True); a.key(XK["Shift_L"], SHIFT, True)
    a.tap(ord("a")); a.tap(XK["space"]); st.pump(50)
    print(f"INFO  shift-combo IM after Shift+T,a,space: {fx.current_im()} commits={a.commits!r}")
    # 4. toggle to English in app A, then open app B: does B follow?
    st.activate(fx, a); ctrl_space(a); imA = fx.current_im(); a.focus_out()
    b = st.IC(fx, "app-b"); b.focus_in(); st.pump(30); imB = fx.current_im()
    b.focus_out(); a.focus_in(); st.pump(30); imA2 = fx.current_im()
    print(f"INFO  en-follow  A toggled to {imA}; new app B starts in {imB}; A after refocus {imA2}")
    # 5. same-program second context (e.g. 2nd tab/window of same app)
    st.activate(fx, a); a.focus_out()
    c = st.IC(fx, "app-a"); c.focus_in(); st.pump(30); imC = fx.current_im()
    print(f"INFO  same-prog  A in {IM}; 2nd context of same program starts in {imC}")
    for x in (a, b, c): x.focus_out(); x.destroy()

main()
