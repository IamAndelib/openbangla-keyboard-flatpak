#!/usr/bin/env bash
# Restart the host's running Fcitx5 Flatpak so it picks up the installed
# add-on, then check that OpenBangla is loaded.
#
# On KDE Plasma Wayland, KWin launches Fcitx5 as the virtual keyboard and
# respawns it when it exits, so we stop it and wait for KWin to bring it back.
# Never use Fcitx5's own "Restart" on Wayland (it loses the IM protocol).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
# Runs on the host or in the container (uses flatpak-spawn --host when needed).

if ! host flatpak info "$APP_ID" >/dev/null 2>&1; then
    die "$APP_ID is not installed (run scripts/build.sh)"
fi
log "installed: $(host flatpak info "$APP_ID" | awk '/Commit:/{print $2}' | cut -c1-12)"

old_pid="$(host flatpak ps --columns=pid,application | awk -v a="$FCITX_APP" '$2==a{print $1; exit}')"
if [[ -n "$old_pid" ]]; then
    log "stopping $FCITX_APP (pid $old_pid); waiting for KWin to respawn it"
    host flatpak kill "$FCITX_APP"
    for _ in $(seq 1 20); do
        sleep 0.5
        new_pid="$(host flatpak ps --columns=pid,application | awk -v a="$FCITX_APP" '$2==a{print $1; exit}')"
        [[ -n "$new_pid" && "$new_pid" != "$old_pid" ]] && break
    done
    [[ -n "${new_pid:-}" ]] || die "Fcitx5 did not come back; start it from System Settings → Virtual Keyboard"
    log "Fcitx5 running again (pid $new_pid)"
else
    warn "$FCITX_APP was not running; select it in System Settings → Virtual Keyboard"
    exit 1
fi

sleep 2
log "checking the add-on is loaded"
diag="$(host flatpak run --command=fcitx5-diagnose "$FCITX_APP" 2>/dev/null || true)"
mkdir -p "$OUT_DIR"; printf '%s\n' "$diag" > "$OUT_DIR/fcitx5-diagnose.txt"
if grep -qi openbangla <<<"$diag"; then
    grep -i openbangla <<<"$diag" | sed 's/^/    /'
    log "OpenBangla found (full report: out/fcitx5-diagnose.txt)"
    log "manual check: add OpenBangla in Fcitx5 settings, type 'ami banglay gan gai' → আমি বাংলায় গান গাই"
else
    die "OpenBangla not found in fcitx5-diagnose output (see out/fcitx5-diagnose.txt)"
fi
