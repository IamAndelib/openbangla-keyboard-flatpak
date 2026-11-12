#!/usr/bin/env bash
# Restart the host's KWin-launched Fcitx5 (KDE Plasma Wayland).
#
# KWin does NOT respawn Fcitx5 after `flatpak kill`, and Fcitx5's own
# "Restart" loses the Wayland input-method protocol. So we do what System
# Settings does: set kwinrc [Wayland] InputMethod to "" and back with change
# notification, then restore kwinrc byte-for-byte (kwriteconfig6 drops the
# `[$e]` key marker).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

# PID of the Fcitx5 daemon instance (skips `flatpak run --command=...` instances).
fcitx_pid() {
    local pid child
    while read -r pid child; do
        if host cat "/proc/$child/cmdline" 2>/dev/null | tr '\0' ' ' | grep -q -- '-- /app/bin/fcitx5'; then
            echo "$pid"; return
        fi
    done < <(host flatpak ps --columns=pid,child-pid,application | awk -v a="$FCITX_APP" '$3==a{print $1, $2}')
}

kwinrc="$HOME/.config/kwinrc"
im="$(host kreadconfig6 --file kwinrc --group Wayland --key InputMethod)"
[[ -n "$im" ]] || die "KWin has no InputMethod set; select Fcitx 5 in System Settings → Virtual Keyboard"
backup="$(mktemp)"; cp -p "$kwinrc" "$backup"
restore() { cp -p "$backup" "$kwinrc"; rm -f "$backup"; }
trap restore EXIT

old_pid="$(fcitx_pid)"
log "restarting Fcitx5 via KWin (was pid ${old_pid:-none})"
host kwriteconfig6 --notify --file kwinrc --group Wayland --key InputMethod ""
sleep 1
host kwriteconfig6 --notify --file kwinrc --group Wayland --key InputMethod "$im"
new_pid=""
for _ in $(seq 1 30); do
    sleep 0.5
    new_pid="$(fcitx_pid)"
    [[ -n "$new_pid" && "$new_pid" != "${old_pid:-}" ]] && break
done
restore; trap - EXIT
[[ -n "$new_pid" ]] || die "Fcitx5 did not come back; re-select it in System Settings → Virtual Keyboard"
log "Fcitx5 running (pid $new_pid); kwinrc restored"
