#!/usr/bin/env bash
# Feasibility probe: build the upstream checkout inside the real target build
# environment (org.fcitx.Fcitx5 in --devel mode = KDE SDK 6.11 + Fcitx5 headers
# at /app) WITHOUT any Flatpak manifest. Research/debugging tooling only.
#
#   scripts/probe-build.sh engine   # -DENABLE_FCITX=ON -DENABLE_GUI=OFF
#   scripts/probe-build.sh gui      # -DENABLE_FCITX=ON (needs the Qt6 probe branch)
#   scripts/probe-build.sh shell    # interactive shell in the same environment
#
# Output: out/probe/<kind>/{build,stage}; stage holds files installed with
# DESTDIR, i.e. stage/app/addons/OpenBangla/...
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

kind="${1:-engine}"
src="${SRC:-$ROOT/upstream/OpenBangla-Keyboard}"
work="$OUT_DIR/probe/$kind"
rust_ext="$HOME/.local/share/flatpak/runtime/org.freedesktop.Sdk.Extension.rust-stable/x86_64/25.08/active/files"
[[ -d "$rust_ext" ]] || die "rust-stable//25.08 not installed (--user); run scripts/devenv-setup.sh"
mkdir -p "$work"

case "$kind" in
    engine) cmake_opts="-DENABLE_FCITX=ON -DENABLE_GUI=OFF" ;;
    gui)    cmake_opts="-DENABLE_FCITX=ON -DENABLE_GUI=ON" ;;
    shell)  cmake_opts="" ;;
    *) die "usage: $0 engine|gui|shell" ;;
esac

inner=$(cat <<EOF
set -euo pipefail
export PATH="$rust_ext/bin:\$PATH" CARGO_HOME="$work/cargo-home"
cd "$work"
echo "cmake: \$(cmake --version | head -1)  cargo: \$(cargo --version)  rustc: \$(rustc --version)"
if [[ "$kind" == shell ]]; then exec bash -i; fi
rm -rf build stage
cmake -S "$src" -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/app/addons/OpenBangla -DCMAKE_INSTALL_LIBDIR=lib $cmake_opts
cmake --build build
DESTDIR="$work/stage" cmake --install build
find stage -type f | sort
EOF
)

log "probe '$kind' in org.fcitx.Fcitx5 --devel (KDE SDK 6.11)"
host flatpak run --devel --command=bash \
    --filesystem="$ROOT" --filesystem="$rust_ext:ro" \
    "$FCITX_APP" -c "$inner" 2>&1 | tee "$work/probe.log"
