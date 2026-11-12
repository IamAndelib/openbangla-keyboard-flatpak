#!/usr/bin/env bash
# Run Flathub's linter (from org.flatpak.Builder) on the manifest and,
# if a build has been exported, on ./repo.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

manifest="$(find_manifest)"
rc=0
log "flatpak-builder-lint manifest $(basename "$manifest")"
flatpak_builder_lint manifest "$manifest" || rc=1
if [[ -d "$REPO_DIR" ]]; then
    log "flatpak-builder-lint repo ./repo"
    flatpak_builder_lint repo "$REPO_DIR" || rc=1
else
    warn "no ./repo yet (run scripts/build.sh first); skipped repo lint"
fi
if [[ -f "$FLATHUB_DIR/flathub.json" ]]; then
    jq . "$FLATHUB_DIR/flathub.json" >/dev/null || { warn "flathub.json is not valid JSON"; rc=1; }
fi
if (( rc == 0 )); then log "lint clean"; else die "lint reported problems"; fi
