# Research and probe log

Living document. Facts carry a date and a source. Probe results carry PASS/FAIL and log excerpts.

## 1. Why a Fcitx5 add-on (2026-11-12)
- **IBus:** ibus-daemon runs on the host and finds engines through `/usr/share/ibus/component/*.xml`.
  A Flatpak can't install files on the host, and there is no IBus Flatpak or extension point.
  This rules out an IBus engine.
- **Fcitx5:** Flathub's `org.fcitx.Fcitx5` is an app with an extension point:
  ```
  [Extension org.fcitx.Fcitx5.Addon]
  directory=addons  subdirectories=true  add-ld-path=lib  autodelete=true  no-autodownload=true  version=stable
  ```
  (from `flatpak info -m org.fcitx.Fcitx5` on this host, v5.1.23, runtime `org.kde.Platform/x86_64/6.11`).
- The launcher `/app/bin/fcitx5` (wrapper around `fcitx5-bin`), for each `/app/addons/<dir>`:
  - prepends `/app/addons/<dir>/lib/fcitx5` to `FCITX_ADDON_DIRS`
  - prepends `/app/addons/<dir>/share` to `XDG_DATA_DIRS`
  - prepends `/app/addons/<dir>/bin` to `PATH`
  - sets `LIBIME_MODEL_DIRS` when `/app/addons/<dir>/lib/libime` exists
- Add-ons already on Flathub: Chewing, ChineseAddons, Hangul, M17N, McBopomofo, McFoxIM, Mozc, Rime, Unikey, Zhuyin.
  M17N covers Bengali Probhat/Inscript, but not Avro phonetic, which is OBK's main value.
- Fcitx5 Flatpak `finish-args` include the session bus, Wayland, `inherit-wayland-socket`, x11,
  network, `xdg-config/fcitx:create` and `xdg-config/ibus` + `xdg-cache/ibus` (for the ibus frontend on GNOME).

## 2. Upstream: OpenBangla-Keyboard (2026-11-12)
- Repo: https://github.com/OpenBangla/OpenBangla-Keyboard. Maintainer: mominul.
- Release 2.0.0 (2020-10-01) is IBus only.
- `develop` @ `eea66aff18ac14cc43fa1273afd68729be5b5e67` (2026-10-17, "Merge #475 new-design") has `version.txt` = 3.0.0 (unreleased), with:
  - the fcitx5 engine (`src/engine/fcitx/`)
  - corrosion-based riti build (#465)
  - PlatformConfig
  - Khipro layout
  - GUI redesign
- Submodules: `src/engine/riti` @ `afee54a79e230165d38f6b17161cd8ff971e1c49`, `cmake/corrosion-rs` @ `f88df62d022d5a3a51118b0c8871f5d6b38a4771` (corrosion 0.6.1, needs CMake ≥ 3.22).
- CMake options: `ENABLE_IBUS`, `ENABLE_FCITX`, `ENABLE_BOTH` (one is required), and `BIN_DIR`, `DATADIR`, `LIBEXECDIR`, which default from `CMAKE_INSTALL_PREFIX`.
- `find_package(Qt5 COMPONENTS Widgets Network Svg REQUIRED)` is unconditional, and `src/frontend` (the GUI) is always built.
  The fcitx engine links only `Fcitx5::Core riti Pthread DL`.
- Rust:
  - riti (MPL-2.0, `rust-version = 1.75.0`) has **no Cargo.lock** (riti#362; nixpkgs vendors its own).
  - `src/platform` (the `system-theme` crate, which pulls in zbus/tokio) has a Cargo.lock.
- The fcitx build installs:
  - `lib/fcitx5/openbangla.so`
  - `share/fcitx5/{addon,inputmethod}/openbangla.conf` (Icon=openbangla-keyboard, Label=বা)
  - `share/openbangla-keyboard/{layouts,data,icons}`
  - hicolor icons, a desktop file, the metainfo `io.github.openbangla.keyboard.metainfo.xml`
  - `bin/openbangla-gui`
- Compile-time absolute paths:
  - `PROJECT_DATADIR "/data"` (riti database)
  - `BIN_DIR "/openbangla-gui"` (fcitx ExternalOption)
  - Both work if the prefix is `/app/addons/OpenBangla`.
- Config:
  - The GUI writes `QSettings("OpenBangla","Keyboard")` (`$XDG_CONFIG_HOME/OpenBangla/Keyboard.conf`), and the engine reads it through fcitx `StandardPath`.
  - User data goes to `$XDG_DATA_HOME/openbangla-keyboard`.
- `--setup-system` / `PlatformConfig.cpp` shell out to `dconf`, `gnome-extensions` and `kwriteconfig6`, and edit `~/.config/fcitx5/profile`. These won't work in the sandbox and aren't needed.
- Licenses: OBK GPL-3.0(+), riti MPL-2.0.
- Maintainer stance:
  - 2021: IMEs don't suit Flatpak (#267, #237).
  - 2026-11 (#485): prefers a pure-Rust GUI (GPUI or iced) over a Qt6 port.
  - #481 (2026-10-22): next release "next month".
  - wengxt (fcitx) on flathub/org.fcitx.Fcitx5#40 (2025-01): upstream should own the Flathub add-on.
- Prior art: https://github.com/tazihad/flatpaks/tree/main/org.fcitx.Fcitx5.Addon.OpenBangla
  (unofficial, from #390). It builds with KDE 5.15 SDK and copies Qt5 out of the SDK, needs a host-side
  icon script, has no license, and isn't on Flathub. Reference only; don't copy from it.
- Other packaging:
  - AUR `openbangla-keyboard-git` (split ibus/fcitx5, `-DBIN_DIR=/usr/bin`)
  - nixpkgs `openbangla-keyboard` + `fcitx5-openbangla-keyboard` (vendored riti Cargo.lock)
  - COPR `badshah/openbangla-keyboard`

## 3. Flathub conventions for Fcitx5 add-ons (2026-11-12)
From the human-written manifests at github.com/flathub/org.fcitx.Fcitx5.Addon.{Unikey,Hangul,Rime,M17N,McBopomofo,Chewing}:
- `runtime: org.fcitx.Fcitx5`, `runtime-version: stable`, `sdk: org.kde.Sdk//6.11`,
  `build-extension: true`, `separate-locales: false`, `build-options.prefix: /app/addons/<Name>`.
- They clean up `/include`, `/lib/pkgconfig`, `*.la`, and usually `/bin`.
- `flathub.json` = `{"skip-icons-check": true}`, because extensions can't export icons.
- The metainfo is installed by upstream, with `<component type="addon">`, `<extends>org.fcitx.Fcitx5</extends>` and `<project_group>Fcitx</project_group>`.
- Rust + corrosion reference: **Chewing** (rust-stable sdk-extension, `append-path`, corrosion built as its own module, per-module `CARGO_HOME`, cargo-sources JSON next to the manifest).
- Icons: the Fcitx5 app's `fcitx5-all-icons` module installs add-on icons inside the app, because extensions can't export them.
- Submission:
  - fork flathub/flathub, branch `new-pr`, PR "Add <id>", then `bot, build`
  - extension IDs must be prefixed with the extension point ID and are exempt from domain verification
  - McBopomofo and McFoxIM were submitted by their own upstreams and merged by Flathub reviewers
- Linter: `flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest|repo …`.
- **Generative AI policy** (flathub-infra/documentation `docs/02-for-app-authors/02-requirements.md`, restored 2026-09-21):
  > Flathub manifests must not contain AI-generated or AI-assisted content. Disclosure does not exempt manifests from this restriction.
  > AI tools or agents must not open or automate Flathub submission pull requests, or generate their commit messages, descriptions, review comments, or replies.

  Other AI-generated material in the app or packaging must be disclosed. AI used only for research, discussion or debugging needs no disclosure.

## 4. Dev environment (2026-11-12)
- Host: Bazzite 45 (Kinoite), KDE Plasma Wayland. KWin `InputMethod` is the Fcitx5 Flatpak desktop file.
  Fcitx5 config is in `~/.var/app/org.fcitx.Fcitx5/config/fcitx5`.
- Container `dev` (distrobox, Fedora 45 toolbox image):
  - runs with `--privileged`, `label=disable` and `unmask=all`
  - `bwrap --unshare-all` works and `/dev/fuse` is present
  - sees the host's system Flatpak installation (`org.fcitx.Fcitx5` visible)
  - `flatpak-spawn` and `distrobox-host-exec` are available
- Tooling pinned: flatpak-builder-tools `cargo/flatpak-cargo-generator.py` @ `9d86d336a39b9af38b86f114b6ce5820fe260f91`.

## 5. Probe log
_Phase 1 results go here (step, date, PASS/FAIL, evidence)._

| Probe | Result | Evidence |
| --- | --- | --- |
| 1.1 build shell (KDE 6.11 SDK + fcitx headers + cargo) | pending | |
| 1.2 engine-only build | pending | |
| 1.3 offline cargo sources | pending | |
| 1.4 runtime typing test | pending | |
| 1.5 Qt6 GUI port sizing | pending | |
