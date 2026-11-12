#!/usr/bin/env bash
# Generate offline cargo sources for an OpenBangla-Keyboard checkout.
# Deterministic tool output (flatpak-cargo-generator), meant to be run by the
# maintainer, who decides where the results go.
#
#   scripts/gen-cargo-sources.sh -o <out-dir> [obk-checkout]
#
# Default checkout: upstream/OpenBangla-Keyboard (with submodules).
# Writes to <out-dir>:
#   riti-Cargo.lock                  only if riti has no Cargo.lock upstream
#   cargo-sources-riti.json          sources for src/engine/riti
#   cargo-sources-platform.json      sources for src/platform (if it has a Cargo.lock)
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

out=""
while getopts "o:" opt; do
    case "$opt" in o) out="$OPTARG" ;; *) die "usage: $0 -o <out-dir> [obk-checkout]" ;; esac
done
shift $((OPTIND - 1))
[[ -n "$out" ]] || die "usage: $0 -o <out-dir> [obk-checkout]"
src="${1:-$ROOT/upstream/OpenBangla-Keyboard}"
[[ -f "$src/CMakeLists.txt" ]] || die "$src is not an OpenBangla-Keyboard checkout"
[[ -f "$src/src/engine/riti/Cargo.toml" ]] || die "riti submodule missing (git submodule update --init)"

gen="$ROOT/tools/flatpak-cargo-generator.py"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
log "OBK commit: $(git -C "$src" rev-parse HEAD 2>/dev/null || echo unknown)"
log "riti commit: $(git -C "$src/src/engine/riti" rev-parse HEAD 2>/dev/null || echo unknown)"

riti_lock="$src/src/engine/riti/Cargo.lock"
if [[ ! -f "$riti_lock" ]]; then
    log "riti has no Cargo.lock; generating one (resolves latest compatible versions)"
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    cp -a "$src/src/engine/riti/." "$tmp/"
    (cd "$tmp" && cargo generate-lockfile)
    cp "$tmp/Cargo.lock" "$out/riti-Cargo.lock"
    riti_lock="$out/riti-Cargo.lock"
fi
python3 "$gen" "$riti_lock" -o "$out/cargo-sources-riti.json"

if [[ -f "$src/src/platform/Cargo.lock" ]]; then
    python3 "$gen" "$src/src/platform/Cargo.lock" -o "$out/cargo-sources-platform.json"
fi
log "wrote:"; find "$out" -maxdepth 1 -type f -printf "    %f\n" >&2
