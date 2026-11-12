---
name: obk-flatpak-dev
description: Build, install, lint and test the OpenBangla Fcitx5 Flatpak add-on in this workspace, and debug failures. Use when asked to build, lint, test, bundle, bump upstream, regenerate cargo sources, or explain a flatpak-builder/linter/Fcitx5 error for org.fcitx.Fcitx5.Addon.OpenBangla. Enforces the Flathub AI-policy boundary (never write into flathub/).
---

# OBK Flatpak dev loop

## Boundary first
`flathub/` is hand-written by the maintainer (Flathub Generative AI policy). You may
**read** it and **run** builds and lints against it. You never write, edit, generate
into or propose literal lines for it, and never draft Flathub PR, commit or reply text.
When a fix is needed there, explain the root cause and point at the relevant docs or a
human-written reference manifest (e.g. github.com/flathub/org.fcitx.Fcitx5.Addon.Chewing
for rust-stable + corrosion + cargo sources, McBopomofo for a plain CMake add-on).
The maintainer makes the edit.

## Loop
1. `scripts/devenv-setup.sh --check`. If anything is missing, run it without `--check`.
2. `scripts/build.sh`. Logs go to `out/build.log`. On `rofiles-fuse` errors, retry with `NO_ROFILES=1`.
3. `scripts/lint.sh` (manifest, plus repo if `./repo` exists).
4. `scripts/test-run.sh`. It restarts the KWin-launched host Fcitx5 and greps `fcitx5-diagnose`
   (`out/fcitx5-diagnose.txt`).
5. Manual typing check: add OpenBangla in Fcitx5 config, then type `ami banglay gan gai`, expecting
   `আমি বাংলায় গান গাই`. Test a Flatpak app (Kate) and a native app.

## Debugging notes
- Manifest-free probes: `scripts/probe-build.sh engine|gui` → `scripts/probe-install.sh engine|gui`
  (local remote `obk-probe`; remove with `--remove` before installing a real build) → `scripts/test-run.sh`.
- Running the GUI or any one-off command in the Fcitx5 sandbox: always pass `flatpak run --die-with-parent ...`,
  or the sandbox outlives `timeout` and leaves an extra `org.fcitx.Fcitx5` instance. Never `flatpak kill`
  just to stop a probe, because that also kills the user's input method and KWin won't respawn it (use test-run.sh's restart).
- Build env for probes without a manifest: `flatpak run --devel --command=bash org.fcitx.Fcitx5`
  gives KDE SDK 6.11 with the Fcitx5 headers and CMake config at `/app`.
- Add-on files resolve under `/app/addons/OpenBangla/{lib/fcitx5,share,bin}` through the Fcitx5 launcher
  (`/app/bin/fcitx5` sets `FCITX_ADDON_DIRS`, `XDG_DATA_DIRS`, `PATH`).
- Engine data path is compiled in (`PROJECT_DATADIR`), so the prefix must be `/app/addons/OpenBangla`.
- Extensions can't export icons to the host; a missing tray icon is expected until Fcitx5's
  `fcitx5-all-icons` module includes OBK.
- Upstream bump: update `upstream/` to the new commit, then the maintainer runs
  `scripts/gen-cargo-sources.sh -o <dir>`, edits the manifest, and you run steps 2–5.
- Record findings in `docs/research.md` and update the Progress table in `plans/pending/obk-flathub.md`.
