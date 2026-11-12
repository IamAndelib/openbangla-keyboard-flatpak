import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stress_copy as s
fx = s.Fcitx(); ic = s.IC(fx, "slope")
pid = fx.owner_pid()
s.activate(fx, ic)
print("start rss", s.rss_kib(pid), flush=True)
for chunk in range(int(sys.argv[1])):
    a = types.SimpleNamespace(keys=25000, seed=chunk + 10, check_every=200)
    ok, detail = s.sc_soak(fx, ic, a)
    print(f"chunk {chunk} ok={ok} rss={s.rss_kib(pid)} KiB commits={len(ic.commits)}", flush=True)
    ic.commits.clear()
sel = os.path.join(os.environ["W"], "data/openbangla-keyboard/phonetic-candidate-selection.json")
print("selection file bytes", os.path.getsize(sel))
