#!/usr/bin/env bash
# Mirror of scripts/stress-isolated.sh for prototype scenarios.
#   iso.sh <name> <default|hardened> <seed-script-or-"-"> <python-script> [args...]
# Private dbus-run-session bus, private XDG dirs under $SP/iso/<name>, guard refuses otherwise.
set -euo pipefail
SP=${SCRATCH:-/tmp/obk-scratch}
name=$1 profile=$2 seed=$3; shift 3
w="$SP/iso/$name"
rm -rf "$w"; mkdir -p "$w/config/fcitx5" "$w/data" "$w/cache"
cat > "$w/config/fcitx5/profile" <<'EOF'
[Groups/0]
Name="Group 1"
Default Layout=us
DefaultIM=openbangla

[Groups/0/Items/0]
Name=keyboard-us

[Groups/0/Items/1]
Name=openbangla

[GroupOrder]
0="Group 1"
EOF
if [[ "$profile" == hardened ]]; then
    printf '[Hotkey/AltTriggerKeys]\n\n[Behavior]\nShareInputState=All\n' > "$w/config/fcitx5/config"
fi
[[ "$seed" != "-" ]] && W="$w" bash "$seed"
export REAL_BUS="${DBUS_SESSION_BUS_ADDRESS:-none}" W="$w"
inner='
set -euo pipefail
[[ "$DBUS_SESSION_BUS_ADDRESS" != "$REAL_BUS" ]] || { echo "REFUSING: not a private bus"; exit 98; }
flatpak run --die-with-parent --filesystem="$W" --env=WAYLAND_DISPLAY= --env=DISPLAY= \
  --command=sh org.fcitx.Fcitx5 -c '"'"'
    export XDG_CONFIG_HOME="$1" XDG_DATA_HOME="$2" XDG_CACHE_HOME="$3"
    case "$XDG_CONFIG_HOME" in */scratchpad/iso/*) ;; *) echo "REFUSING $XDG_CONFIG_HOME"; exit 99;; esac
    exec fcitx5 --disable=all --enable=dbus,dbusfrontend,keyboard,openbangla
  '"'"' _ "$W/config" "$W/data" "$W/cache" > "$W/fcitx5.log" 2>&1 &
fx=$!
has_owner() { dbus-send --session --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.NameHasOwner string:org.fcitx.Fcitx5 2>/dev/null | grep -q "boolean true"; }
for _ in $(seq 1 50); do has_owner && break; sleep 0.2; done
has_owner || { echo "private Fcitx5 did not come up"; tail -20 "$W/fcitx5.log"; exit 1; }
sleep 1
rc=0; python3 "$@" || rc=$?
kill $fx 2>/dev/null || true; wait $fx 2>/dev/null || true
exit $rc
'
exec distrobox enter dev -- env FLATPAK_SYSTEM_DIR=/run/host/var/lib/flatpak REAL_BUS="$REAL_BUS" W="$w" dbus-run-session -- bash -c "$inner" _ "$@"
