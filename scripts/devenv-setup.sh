#!/usr/bin/env bash
# Set up (or --check) the dev container toolchain and the --user Flatpak
# installation needed to build org.fcitx.Fcitx5.Addon.OpenBangla.
#
#   scripts/devenv-setup.sh          # install whatever is missing (idempotent)
#   scripts/devenv-setup.sh --check  # report only; exit 1 if anything is missing
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

DNF_PKGS=(flatpak flatpak-builder rust cargo python3-aiohttp python3-tomlkit
          gh jq git desktop-file-utils appstream python3-gobject rustfmt
          git-filter-repo)
USER_REFS=(org.kde.Sdk//6.11
           org.freedesktop.Sdk.Extension.rust-stable//25.08
           org.flatpak.Builder//stable)
# The add-on extends the host's Fcitx5 app; it must be installed (system or user).
REQUIRED_APP="$FCITX_APP"
GENERATOR="$ROOT/tools/flatpak-cargo-generator.py"
GENERATOR_COMMIT="9d86d336a39b9af38b86f114b6ce5820fe260f91"

missing=0
ok()   { printf '  \033[32mok\033[0m      %s\n' "$*"; }
miss() { printf '  \033[31mmissing\033[0m %s\n' "$*"; missing=1; }

log "dnf packages (container)"
need_pkgs=()
for p in "${DNF_PKGS[@]}"; do
    if rpm -q "$p" >/dev/null 2>&1; then ok "$p"; else miss "$p"; need_pkgs+=("$p"); fi
done
if (( ${#need_pkgs[@]} )) && (( ! CHECK_ONLY )); then
    sudo dnf install -y --setopt=install_weak_deps=False "${need_pkgs[@]}"
fi

log "flathub remote (--user)"
if flatpak remotes --user --columns=name | grep -qx flathub; then ok "flathub"
else
    miss "flathub"
    (( CHECK_ONLY )) || flatpak remote-add --user --if-not-exists flathub \
        https://dl.flathub.org/repo/flathub.flatpakrepo
fi

log "Flatpak refs (--user)"
need_refs=()
for r in "${USER_REFS[@]}"; do
    if flatpak info --user "$r" >/dev/null 2>&1; then ok "$r"; else miss "$r"; need_refs+=("$r"); fi
done
if (( ${#need_refs[@]} )) && (( ! CHECK_ONLY )); then
    flatpak install --user -y --noninteractive flathub "${need_refs[@]}"
fi

log "Fcitx5 app (system or user)"
if flatpak info "$REQUIRED_APP" >/dev/null 2>&1; then
    ok "$REQUIRED_APP $(flatpak info "$REQUIRED_APP" | awk '/Version:/{print $2}')"
else
    miss "$REQUIRED_APP"
    (( CHECK_ONLY )) || flatpak install --user -y --noninteractive flathub "$REQUIRED_APP"
fi

log "tools"
if [[ -f "$GENERATOR" ]]; then ok "flatpak-cargo-generator.py (pinned $GENERATOR_COMMIT)"
else
    miss "flatpak-cargo-generator.py"
    if (( ! CHECK_ONLY )); then
        mkdir -p "$(dirname "$GENERATOR")"
        curl -fsSL -o "$GENERATOR" \
            "https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/$GENERATOR_COMMIT/cargo/flatpak-cargo-generator.py"
        chmod +x "$GENERATOR"
    fi
fi

log "sandbox sanity"
if bwrap --unshare-all --ro-bind / / --dev /dev --proc /proc true 2>/dev/null; then ok "bwrap works"
else miss "bwrap cannot create namespaces in this container"; fi
if flatpak_builder_lint --version >/dev/null 2>&1 || flatpak_builder_lint --help >/dev/null 2>&1; then
    ok "flatpak-builder-lint runs"
else
    miss "flatpak-builder-lint (org.flatpak.Builder) does not run"
fi

if (( missing )); then
    if (( CHECK_ONLY )); then die "environment incomplete; run scripts/devenv-setup.sh"; fi
    log "installed missing pieces; re-run with --check to confirm"
else
    log "environment ready"
fi
