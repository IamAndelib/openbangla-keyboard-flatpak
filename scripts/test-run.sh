#!/usr/bin/env bash
# Restart the host's KWin-launched Fcitx5 Flatpak so it picks up the installed
# add-on, check that OpenBangla is registered, and run a headless typing test.
#
#   scripts/test-run.sh              # restart + checks
#   scripts/test-run.sh --no-restart # checks only
#
# KDE Plasma Wayland: KWin launches Fcitx5 as the virtual keyboard, and does NOT
# respawn it after `flatpak kill`. We restart it the way System Settings does:
# set kwinrc [Wayland] InputMethod to "" and back with change notification,
# then restore the original kwinrc byte-for-byte (kwriteconfig6 drops the
# `[$e]` key marker). Never use Fcitx5's own "Restart" on Wayland.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

# PID of the Fcitx5 daemon instance (other instances of the same app ID, e.g. a
# `flatpak run --command=...` shell or the GUI, are skipped).
fcitx_pid() {
    local pid child
    while read -r pid child; do
        if host cat "/proc/$child/cmdline" 2>/dev/null | tr '\0' ' ' | grep -q -- '-- /app/bin/fcitx5'; then
            echo "$pid"; return
        fi
    done < <(host flatpak ps --columns=pid,child-pid,application | awk -v a="$FCITX_APP" '$3==a{print $1, $2}')
}

host flatpak info "$APP_ID" >/dev/null 2>&1 || die "$APP_ID is not installed (run scripts/build.sh)"
log "installed: $APP_ID $(host flatpak info "$APP_ID" | awk '/Origin:/{o=$2} /Commit:/{c=substr($2,1,12)} END{print "(" o " " c ")"}')"

if [[ "${1:-}" != "--no-restart" ]]; then
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
    sleep 2
fi

log "checking registration over D-Bus"
addons="$(host busctl --user call org.fcitx.Fcitx5 /controller org.fcitx.Fcitx.Controller1 GetAddonsV2 2>&1 || true)"
ims="$(host busctl --user call org.fcitx.Fcitx5 /controller org.fcitx.Fcitx.Controller1 AvailableInputMethods 2>&1 || true)"
grep -q '"openbangla"' <<<"$addons" || die "addon 'openbangla' not loaded by Fcitx5"
grep -q '"openbangla"' <<<"$ims"    || die "input method 'openbangla' not available"
log "addon + input method 'openbangla' registered"

log "headless typing test"
python3 "$ROOT/scripts/probe-type.py" "ami banglay gan gai" --expect "আমি বাংলায় গান গাই"
log "manual check: type in a real app (Kate Flatpak, a native app) after adding OpenBangla in Fcitx5 settings"
