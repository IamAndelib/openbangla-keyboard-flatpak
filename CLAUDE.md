# OpenBangla Keyboard Flatpak (workspace)

Goal: ship OpenBangla Keyboard (OBK) on Flathub as the Fcitx5 add-on
`org.fcitx.Fcitx5.Addon.OpenBangla`, and maintain it.
Plan and progress: `plans/pending/obk-flathub.md`. Research and probe log: `docs/research.md`.

## HARD RULE — Flathub Generative AI policy
Flathub forbids AI-generated or AI-assisted content in manifests, and forbids AI
opening or writing Flathub PRs, commits, descriptions or review replies
(https://docs.flathub.org/docs/for-app-authors/requirements#generative-ai-policy).
- `flathub/` is a separate git repo that **the maintainer writes by hand**. Claude
  never creates, edits or writes into anything under `flathub/` (no Edit/Write, no
  shell redirection, no sed -i, no generators that output there), and never
  suggests literal manifest lines to paste.
- Claude never drafts Flathub PR titles or bodies, commit messages, or review replies.
- Allowed: research, explaining concepts and pointing at human-written reference
  manifests, running builds and lints on the maintainer's manifest, reading logs
  and explaining root causes (debugging), and everything in this workspace outside
  `flathub/`.
- Upstream (OpenBangla) code PRs may be AI-assisted, but must say so in the PR body.

## Facts
- Target: extension of `org.fcitx.Fcitx5` (Flathub, v5.1.23, runtime `org.kde.Platform//6.11`,
  sdk `org.kde.Sdk//6.11`), extension point `org.fcitx.Fcitx5.Addon`, prefix
  `/app/addons/OpenBangla`. Rust comes from `org.freedesktop.Sdk.Extension.rust-stable//25.08`.
- Upstream: fcitx5 support is only on OBK `develop` (unreleased 3.0.0). The submodules
  `src/engine/riti` (Rust, no Cargo.lock upstream) and `cmake/corrosion-rs` are used.
  Qt5 is required unconditionally by upstream CMake; the fcitx engine itself needs no Qt.
- v1 scope: engine only (no settings GUI) until upstream gains an optional or Qt6 GUI.
- IBus can't be shipped via Flatpak; out of scope.
- Host: Bazzite KDE Plasma Wayland. KWin launches the Fcitx5 Flatpak as the virtual keyboard;
  its config is in `~/.var/app/org.fcitx.Fcitx5/config/fcitx5`.

## Dev environment
All builds run in the distrobox container `dev` (Fedora 45, privileged, bwrap works).
It sees the host's system Flatpak installation. Builds install with `--user` into
`~/.local/share/flatpak`, which is shared with the host. Scripts re-exec themselves
in `dev` when called from the host.

| Task | Command |
| --- | --- |
| Check or repair the toolchain | `scripts/devenv-setup.sh [--check]` |
| Build + install the maintainer's manifest | `scripts/build.sh` (`NO_ROFILES=1` if FUSE fails) |
| Lint (Flathub linter) | `scripts/lint.sh` |
| Restart host Fcitx5 + verify add-on | `scripts/test-run.sh` |
| Cargo sources (maintainer runs) | `scripts/gen-cargo-sources.sh -o <dir> [obk-checkout]` |
| Tester bundle | `scripts/bundle.sh` → `out/*.flatpak` |

Ignored working dirs: `upstream/` (OBK clone for probes and upstream PRs), `flathub/`,
`build-dir/`, `.flatpak-builder/`, `repo/`, `out/`.

## Conventions
- Pin every upstream source by commit; record evidence (logs, PASS/FAIL) in `docs/research.md`.
- Update the Progress table in `plans/pending/obk-flathub.md` as phases land.
- Use the `gh` CLI for GitHub (the GitHub MCP plugin is not connected).
- Do not modify the host's system Flatpak installation or layer rpm-ostree packages.
