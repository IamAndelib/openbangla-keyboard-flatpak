#!/usr/bin/env bash
# Make a single-file .flatpak bundle from ./repo for testers.
# Install with: flatpak install --user ./org.fcitx.Fcitx5.Addon.OpenBangla.flatpak
# (the org.fcitx.Fcitx5 app from Flathub must already be installed).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

[[ -d "$REPO_DIR" ]] || die "no ./repo (run scripts/build.sh first)"
mkdir -p "$OUT_DIR"
bundle="$OUT_DIR/$APP_ID.flatpak"
flatpak build-bundle --runtime "$REPO_DIR" "$bundle" "$APP_ID" stable
log "bundle: $bundle ($(du -h "$bundle" | cut -f1))"
sha256sum "$bundle" | tee "$bundle.sha256"
