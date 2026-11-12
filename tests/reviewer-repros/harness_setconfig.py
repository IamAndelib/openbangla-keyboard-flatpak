#!/usr/bin/env python3
"""Apply the hardening via Controller1.SetConfig on the PRIVATE bus, then rerun scenarios."""
import importlib.util, sys
from gi.repository import GLib
WS = "${OBK_WS:-.}"
spec = importlib.util.spec_from_file_location("stress", WS + "/scripts/stress-ime.py")
st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
fx = st.Fcitx()
V = GLib.Variant
v = V("a{sv}", {
    "Hotkey": V("a{sv}", {"AltTriggerKeys": V("a{sv}", {})}),
    "Behavior": V("a{sv}", {"ShareInputState": V("s", "All"), "ActiveByDefault": V("s", "True")}),
})
fx.ctrl("SetConfig", "(sv)", ("fcitx://config/global", v))
st.pump(200)
cfg = fx.ctrl("GetConfig", "(s)", ("fcitx://config/global",), "(va(sa(sssva{sv})))")[0]
print("INFO  after SetConfig: Hotkey.AltTriggerKeys =", cfg["Hotkey"].get("AltTriggerKeys"),
      "| TriggerKeys =", cfg["Hotkey"].get("TriggerKeys"),
      "| Behavior.ShareInputState =", cfg["Behavior"].get("ShareInputState"),
      "| ActiveByDefault =", cfg["Behavior"].get("ActiveByDefault"))
ic = st.IC(fx, "obk-stress")
class A: pass
for name in ("shift-tap", "new-ic"):
    ok, d = st.SCENARIOS[name](fx, ic, A())
    print(f"{'PASS' if ok else 'FAIL'}  {name:10s} {d}")
ic.focus_out(); ic.destroy()
