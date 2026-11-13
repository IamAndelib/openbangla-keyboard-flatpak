# shellcheck shell=bash disable=SC2034
# Shared helpers for the workspace dev scripts. Source, don't execute.
#
# These scripts are workspace dev tooling. They are NOT part of the Flathub
# packaging repo (flathub/), which is hand-written by the maintainer.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="org.fcitx.Fcitx5.Addon.OpenBangla"
FCITX_APP="org.fcitx.Fcitx5"
DEV_CONTAINER="${DEV_CONTAINER:-dev}"
FLATHUB_DIR="${FLATHUB_DIR:-$ROOT/flathub}"
BUILD_DIR="$ROOT/build-dir"
STATE_DIR="$ROOT/.flatpak-builder"
REPO_DIR="$ROOT/repo"
OUT_DIR="$ROOT/out"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33mwarn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

in_container() { [[ -f /run/.containerenv || -n "${CONTAINER_ID:-}" ]]; }

# Inside distrobox, Fedora's flatpak only sees the container's (empty) system
# installation. Point it at the host's, read-only, so the installed
# org.fcitx.Fcitx5 app (the add-on's "runtime") is found. We only ever write
# to the --user installation, which lives in the shared $HOME.
if in_container && [[ -d /run/host/var/lib/flatpak/app ]]; then
    export FLATPAK_SYSTEM_DIR=/run/host/var/lib/flatpak
fi

# Re-exec the calling script inside the dev container when run on the host.
# Usage: ensure_container "$0" "$@"
ensure_container() {
    local script="$1"; shift
    if ! in_container; then
        command -v distrobox >/dev/null || die "not in a container and distrobox is missing"
        exec distrobox enter "$DEV_CONTAINER" -- "$script" "$@"
    fi
}

# Run a command on the host (for things that must touch the host session,
# e.g. restarting the running Fcitx5 that KWin launched).
host() {
    if in_container; then flatpak-spawn --host "$@"; else "$@"; fi
}

# Locate the maintainer's manifest in flathub/ (yml, yaml or json).
find_manifest() {
    if [[ -n "${MANIFEST:-}" ]]; then printf '%s\n' "$MANIFEST"; return; fi
    local ext
    for ext in yml yaml json; do
        if [[ -f "$FLATHUB_DIR/$APP_ID.$ext" ]]; then
            printf '%s\n' "$FLATHUB_DIR/$APP_ID.$ext"; return
        fi
    done
    die "no manifest found at $FLATHUB_DIR/$APP_ID.{yml,yaml,json} (set MANIFEST=... to override)"
}

flatpak_builder_lint() {
    # The linter is itself a Flatpak: give it access to the workspace (it keeps
    # a ccache/state dir next to the manifest).
    flatpak run --filesystem="$ROOT" --command=flatpak-builder-lint org.flatpak.Builder "$@"
}
