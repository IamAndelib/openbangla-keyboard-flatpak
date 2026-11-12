#!/usr/bin/env bash
# Feasibility probe: wrap the files staged by `scripts/probe-build.sh <kind>`
# into a throwaway local Flatpak extension (no manifest; low-level
# build-export) and install it --user, so the real KWin-launched Fcitx5 on the
# host loads it. Research/debugging harness only — never shipped.
#
#   scripts/probe-install.sh [engine|gui]   # export + install as remote "obk-probe"
#   scripts/probe-install.sh --remove       # uninstall and drop the probe remote
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

PROBE_REMOTE="obk-probe"
PROBE_REPO="$OUT_DIR/probe/repo"

if [[ "${1:-}" == "--remove" ]]; then
    flatpak uninstall --user -y --noninteractive "$APP_ID" 2>/dev/null || true
    flatpak remote-delete --user --force "$PROBE_REMOTE" 2>/dev/null || true
    log "probe extension removed"
    exit 0
fi

kind="${1:-engine}"
stage="$OUT_DIR/probe/$kind/stage/app/addons/OpenBangla"
[[ -d "$stage" ]] || die "nothing staged at $stage (run scripts/probe-build.sh $kind)"

fcitx_ver="$(flatpak info "$FCITX_APP" | awk '/Sdk:/{print $2}')"   # e.g. org.kde.Sdk/x86_64/6.11
dir="$OUT_DIR/probe/ext-$kind"
rm -rf "$dir"; mkdir -p "$dir/files"
cp -a "$stage/." "$dir/files/"
cat > "$dir/metadata" <<EOF
[Runtime]
name=$APP_ID
runtime=$FCITX_APP/x86_64/stable
sdk=$fcitx_ver

[ExtensionOf]
ref=app/$FCITX_APP/x86_64/stable
EOF

log "exporting probe extension ($kind) to $PROBE_REPO"
flatpak build-export --runtime --subject="OBK probe ($kind)" "$PROBE_REPO" "$dir" stable
flatpak build-update-repo "$PROBE_REPO" >/dev/null

if ! flatpak remotes --user --columns=name | grep -qx "$PROBE_REMOTE"; then
    flatpak remote-add --user --no-gpg-verify "$PROBE_REMOTE" "$PROBE_REPO"
fi
flatpak install --user -y --noninteractive --reinstall "$PROBE_REMOTE" "runtime/$APP_ID/x86_64/stable"
log "installed; now run scripts/test-run.sh"
