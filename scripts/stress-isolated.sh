#!/usr/bin/env bash
# Run scripts/stress-ime.py against a PRIVATE Fcitx5 instance: its own D-Bus
# session bus, its own config/data dirs under out/stress/, and only the
# dbus/dbusfrontend/keyboard/openbangla addons (no Wayland/X11/tray frontends).
# Nothing the user does on the desktop can interfere, and the user's real
# Fcitx5, config and input method are never touched.
#
#   scripts/stress-isolated.sh [--config default|hardened|recommended] [stress-ime.py args...]
#
# --config default   Fcitx5 out-of-the-box behaviour (what new users get)
# --config hardened  AltTriggerKeys (Left Shift tap) disabled + ShareInputState=All
# --config recommended  hardened + ActiveByDefault=False + PreferTextIcon (what
#                       scripts/fcitx-config.py --apply sets for users)
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

profile="default"
if [[ "${1:-}" == "--config" ]]; then profile="$2"; shift 2; fi
[[ "$profile" =~ ^(default|hardened|recommended)$ ]] || die "--config default|hardened|recommended"

# Unique run dir per invocation (concurrent runs must not clobber each other);
# out/stress/<profile>-latest points at the newest one.
w="$OUT_DIR/stress/$profile-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$w/config/fcitx5" "$w/data" "$w/cache"
ln -sfn "$(basename "$w")" "$OUT_DIR/stress/$profile-latest"
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
if [[ "$profile" == recommended ]]; then
    mkdir -p "$w/config/fcitx5/conf"
    cat > "$w/config/fcitx5/config" <<'EOF2'
[Hotkey]
AltTriggerKeys=

[Behavior]
ShareInputState=All
ActiveByDefault=False
EOF2
    printf 'PreferTextIcon=True\n' > "$w/config/fcitx5/conf/classicui.conf"
fi
if [[ "$profile" == hardened ]]; then
    cat > "$w/config/fcitx5/config" <<'EOF'
[Hotkey/AltTriggerKeys]

[Behavior]
ShareInputState=All
EOF
fi

# Seeded scenarios need their files in place before Fcitx5 (and the add-on) start.
STRESS_RUN_DIR="$w" STRESS_ISOLATED=1 python3 "$ROOT/scripts/stress-ime.py" --prepare "$@"

inner=$(cat <<EOF
set -euo pipefail
# Flatpak forces XDG_CONFIG_HOME/XDG_DATA_HOME to ~/.var/app/<id>/..., so
# --env cannot override them. Set them INSIDE the sandbox, and refuse to start
# unless they point into out/stress/ (never the user's real Fcitx5 config).
flatpak run --die-with-parent --filesystem="$ROOT" \
    --env=WAYLAND_DISPLAY= --env=DISPLAY= \
    --command=sh "$FCITX_APP" -c '
        export XDG_CONFIG_HOME="\$1" XDG_DATA_HOME="\$2" XDG_CACHE_HOME="\$3"
        case "\$XDG_CONFIG_HOME" in */out/stress/*) ;; *) echo "REFUSING: config dir \$XDG_CONFIG_HOME"; exit 99 ;; esac
        echo "isolated XDG_CONFIG_HOME=\$XDG_CONFIG_HOME XDG_DATA_HOME=\$XDG_DATA_HOME"
        exec fcitx5 --disable=all --enable=dbus,dbusfrontend,keyboard,openbangla --verbose=openbangla=5
    ' _ "$w/config" "$w/data" "$w/cache" \
    > "$w/fcitx5.log" 2>&1 &
fx=\$!
# busctl --user would talk to systemd's user bus; use the private session bus.
has_owner() {
    dbus-send --session --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus \\
        org.freedesktop.DBus.NameHasOwner string:org.fcitx.Fcitx5 2>/dev/null | grep -q 'boolean true'
}
for _ in \$(seq 1 50); do has_owner && break; sleep 0.2; done
has_owner || { echo "private Fcitx5 did not come up"; tail -20 "$w/fcitx5.log"; exit 1; }
echo "private bus: \$DBUS_SESSION_BUS_ADDRESS"
head -1 "$w/fcitx5.log"

sleep 1
rc=0
STRESS_RUN_DIR="$w" STRESS_ISOLATED=1 python3 "$ROOT/scripts/stress-ime.py" "\$@" || rc=\$?
kill \$fx 2>/dev/null || true
wait \$fx 2>/dev/null || true
exit \$rc
EOF
)

log "isolated Fcitx5 ($profile config), private session bus; run dir: ${w#"$ROOT"/}"
dbus-run-session -- bash -c "$inner" _ "$@"
