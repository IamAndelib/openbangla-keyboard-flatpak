#!/usr/bin/env bash
# Build the maintainer's manifest in flathub/ and install it into the --user
# Flatpak installation (shared with the host), exporting to ./repo as well.
#
#   scripts/build.sh                 # build + install
#   scripts/build.sh --no-install    # build + export to ./repo only
#   NO_ROFILES=1 scripts/build.sh    # pass --disable-rofiles-fuse
#   MANIFEST=path scripts/build.sh   # build another manifest
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

manifest="$(find_manifest)"
args=(--user --force-clean --ccache --install-deps-from=flathub
      --state-dir="$STATE_DIR" --repo="$REPO_DIR")
[[ "${1:-}" == "--no-install" ]] || args+=(--install)
[[ -n "${NO_ROFILES:-}" ]] && args+=(--disable-rofiles-fuse)

log "building $(basename "$manifest")"
mkdir -p "$OUT_DIR"
cd "$ROOT" || exit 1
flatpak-builder "${args[@]}" "$BUILD_DIR" "$manifest" 2>&1 | tee "$OUT_DIR/build.log"
log "done; log at out/build.log"
