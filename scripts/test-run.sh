#!/usr/bin/env bash
# Restart the host's KWin-launched Fcitx5 Flatpak so it picks up the installed
# add-on, check that OpenBangla is registered, and run a headless typing test.
#
#   scripts/test-run.sh              # restart + checks
#   scripts/test-run.sh --no-restart # checks only
#
# The restart is scripts/fcitx-restart.sh (KWin InputMethod toggle).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

host flatpak info "$APP_ID" >/dev/null 2>&1 || die "$APP_ID is not installed (run scripts/build.sh)"
log "installed: $APP_ID $(host flatpak info "$APP_ID" | awk '/Origin:/{o=$2} /Commit:/{c=substr($2,1,12)} END{print "(" o " " c ")"}')"

if [[ "${1:-}" != "--no-restart" ]]; then
    "$ROOT/scripts/fcitx-restart.sh"
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
