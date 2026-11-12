# OpenBangla Keyboard on Flathub — as a Fcitx5 add-on

## Context

OpenBangla Keyboard (OBK) is the main Bangla input method on Linux. Immutable distros (Bazzite, Silverblue, Kinoite, …) can't easily layer it, and it has no Flatpak. Our goal is to publish and maintain it on Flathub.

### Research findings that set the approach (verified 2026-11-12)
- **IBus can't use a Flatpak engine.** ibus-daemon on the host finds engines through `/usr/share/ibus/component/*.xml`, and an extension can't install files there.
- **Fcitx5 add-on is the only workable route.** Flathub's `org.fcitx.Fcitx5` (5.1.23, runtime `org.kde.Platform//6.11`) is already installed on this host. It has the extension point `org.fcitx.Fcitx5.Addon` (`directory=addons`, `subdirectories`, `add-ld-path=lib`). Its launcher `/app/bin/fcitx5` adds `/app/addons/<Name>/{lib/fcitx5,share,bin}` to `FCITX_ADDON_DIRS`, `XDG_DATA_DIRS` and `PATH`. Ten add-ons already ship this way (Unikey, Hangul, Rime, M17N, Chewing, McBopomofo, …).
  - Target ID: **`org.fcitx.Fcitx5.Addon.OpenBangla`**.
  - Extensions are exempt from domain verification.
- **Upstream (OpenBangla/OpenBangla-Keyboard):**
  - The last release is 2.0.0 (2020), IBus only. fcitx5 support exists only on `develop` (tip `eea66aff`, 2026-10-17, version.txt 3.0.0, unreleased).
  - The build uses CMake, with git submodules `src/engine/riti` (Rust, MPL-2.0) and `cmake/corrosion-rs` (0.6.1).
  - Options: `ENABLE_FCITX`, `ENABLE_IBUS`, `BIN_DIR`, `DATADIR`, `LIBEXECDIR`. Install paths come from `CMAKE_INSTALL_PREFIX`, so `/app/addons/OpenBangla` works.
  - **Blocker:** `find_package(Qt5 … REQUIRED)` is unconditional, but the fcitx engine itself needs no Qt (it links only `Fcitx5::Core riti`).
  - **riti has no Cargo.lock.** `src/platform/Cargo.lock` exists.
  - The maintainer (mominul) prefers a future Rust GUI over a Qt6 port (#485). The next release was promised "soon" (#481).
  - wengxt (fcitx) said upstream should own the Flathub add-on (flathub/org.fcitx.Fcitx5#40).
- **Packaging conventions, from the Flathub add-on manifests:**
  - `runtime: org.fcitx.Fcitx5`, `runtime-version: stable`, `sdk: org.kde.Sdk//6.11`, `build-extension: true`, `prefix: /app/addons/<Name>`, `flathub.json {"skip-icons-check": true}`.
  - Metainfo uses `type="addon"` with `<extends>org.fcitx.Fcitx5</extends>`.
  - The rust-stable sdk-extension (25.08) plus corrosion example is `flathub/org.fcitx.Fcitx5.Addon.Chewing`.
  - Extensions can't export icons; the Fcitx5 app bundles add-on icons in its `fcitx5-all-icons` module.
- **Prior art:** tazihad/flatpaks `org.fcitx.Fcitx5.Addon.OpenBangla` (unofficial). It uses the KDE 5.15 SDK and copies Qt5 out of the SDK, needs host-side icon installs, and has no license. Reference only.
- **Flathub Generative AI policy (requirements doc, updated 2026-09-21):** "Flathub manifests must not contain AI-generated or AI-assisted content." AI must not open, automate or write the text of submission PRs, commits or replies. AI used for research, discussion or debugging is fine.

### Decisions (from the Q&A gate)
| Decision | Chosen | Why |
| --- | --- | --- |
| Who authors the Flathub packaging | **User hand-writes the manifest, metainfo (if in the Flathub repo), flathub.json and every Flathub PR, commit and reply.** Claude does the environment, research, feasibility probes, dev scripts, testing and debugging help. | Flathub AI policy. |
| Settings GUI | **v1 is engine-only.** Upstream is asked for a no-GUI build switch and Qt6 support; the GUI follows once that lands. | Qt5 isn't in the KDE 6.11 runtime, and bundling Qt5 would be rejected or costly. |
| Upstream | **User contacts upstream first**, offering to maintain the Flathub add-on. Claude may write and test upstream code PRs, with AI use disclosed in the PR. | Fcitx's maintainer and Flathub both prefer upstream involvement, and the metainfo and build switch need to live upstream. |
| Working repo | **Public GitHub repo under the user's account.** The Flathub packaging is a separate repo. | Shareable with upstream and testers. |
| Build location | Dev container `dev` (Fedora 45 distrobox, privileged; bwrap verified working, `/dev/fuse` present). It sees the host system Flatpak installation (incl. `org.fcitx.Fcitx5`). Builds install with `--user` into `~/.local/share/flatpak`, which the host shares. | The user's dev container, and installs show up on the host for real testing. |

## Workspace layout (project dir = workspace git repo)
```
Openbangla Keyboard Flatpak/
  CLAUDE.md                     # project facts, AI-policy boundary, commands
  .claude/settings.json         # permissions: allow dev-container build cmds; DENY Edit/Write on flathub/**
  .claude/skills/obk-flatpak-dev/SKILL.md   # build→install→test→lint loop in the dev container
  plans/pending/obk-flathub.md  # this plan, committed; Progress table kept current
  docs/research.md              # findings + sources (above, expanded) + probe results
  docs/user-setup.md            # end-user enablement: KDE Wayland, GNOME (ibus frontend + Kimpanel), XWayland, host im-modules
  docs/maintenance.md           # update procedure (bump commit → regen lock/cargo sources → build → lint → test)
  scripts/                      # dev tooling (AI-written; NOT part of Flathub packaging)
    devenv-setup.sh  build.sh  lint.sh  test-run.sh  gen-cargo-sources.sh  bundle.sh
  tools/flatpak-cargo-generator.py   # pinned upstream copy (flatpak/flatpak-builder-tools)
  .gitignore                    # upstream/, flathub/, build-dir/, .flatpak-builder/, repo/, *.flatpak
  upstream/                     # (ignored) OBK develop clone + submodules, for probes and upstream PRs
  flathub/                      # (ignored) SEPARATE git repo = future flathub/org.fcitx.Fcitx5.Addon.OpenBangla — USER-AUTHORED ONLY
```

## Phases

### Phase 0: Environment and Claude Code setup (Claude)
Verified when: `scripts/devenv-setup.sh --check` passes in `dev`, the workspace repo is pushed to GitHub, and the Claude config loads.

#### Step 0.1: Dev container toolchain (S)
- In `dev`: `sudo dnf install -y flatpak-builder rust cargo python3-aiohttp python3-tomlkit gh jq desktop-file-utils appstream`. Check `appstreamcli` is present.
- Flatpak `--user` setup (shared with the host): add the flathub remote, then install `org.kde.Sdk//6.11`, `org.freedesktop.Sdk.Extension.rust-stable//25.08` and `org.flatpak.Builder` (which provides `flatpak-builder-lint`).
- Pin `tools/flatpak-cargo-generator.py` to a specific flatpak-builder-tools commit.
- Write `scripts/devenv-setup.sh` so the setup is reproducible and idempotent, with a `--check` mode.
- Run linting through `flatpak run --command=flatpak-builder-lint org.flatpak.Builder` (it works from the container because the host installations are visible; otherwise use `flatpak-spawn --host`).
- Verify: `distrobox enter dev -- scripts/devenv-setup.sh --check`.
- Blocked by: none.

#### Step 0.2: Workspace repo and Claude config (S)
- `git init`; add `.gitignore`, `CLAUDE.md`, `.claude/settings.json`, `.claude/skills/obk-flatpak-dev/SKILL.md`, and this plan under `plans/pending/`.
- `CLAUDE.md` content:
  - the AI-policy boundary (Claude never edits `flathub/`, and never writes Flathub PR, commit or reply text)
  - build commands, the IDs and the runtime
- `.claude/settings.json`:
  - allow the `distrobox enter dev -- …` build, lint and git read-only commands
  - deny `Edit(flathub/**)` and `Write(flathub/**)` (a mechanical guard for the policy)
- Create the public GitHub repo with `gh repo create IamAndelib/openbangla-keyboard-flatpak --public` (name adjustable) and push.
- Save project memories:
  - the AI-policy boundary
  - dev container facts
  - that upstream fcitx support is on `develop` only
- Skills and plugins: the installed ones cover this project, so nothing new is needed.
  - **process:** superpowers (systematic-debugging, verification-before-completion), zizi-skills (planning, git-sync, project-config, infrastructure, source-driven-development, handoff)
  - **upstream C++/CMake/Qt6 work:** qt-development-skills (qt-cmake-project, qt-cpp-review, qt-cpp-docs)
  - **GitHub MCP:** it fails to connect (bad auth header), so use the `gh` CLI. Re-authenticating the plugin is optional.
- Blocked by: 0.1 (for the gh-in-container check; the repo itself can come first).

### Phase 1: Feasibility probes, no manifest (Claude; counts as research/debugging under the policy)
Highest-risk work first. Everything happens in `upstream/` and the scratchpad, without writing a Flatpak manifest. Results go to `docs/research.md`.
Verified when: each probe below has a recorded PASS/FAIL with logs, and the engine-only add-on types Bangla in a real app on this KDE Wayland host.

#### Step 1.1: Clone and build-environment probe (S)
- Shallow-clone OBK `develop` with submodules into `upstream/`.
- Open a build shell matching the real environment: `flatpak run --devel --command=bash --filesystem=<workspace> org.fcitx.Fcitx5` (KDE 6.11 SDK, with the fcitx5 headers and CMake config at `/app`).
- Put a Rust toolchain on PATH: the `--user` rust-stable extension at `~/.local/share/flatpak/runtime/org.freedesktop.Sdk.Extension.rust-stable/...`, bind-mounted with `--filesystem`.
- Pass: `cmake --version` ≥ 3.22, `cargo --version`, and `find_package(Fcitx5Core)` resolves.
- Blocked by: 0.1.

#### Step 1.2: Engine-only build (S)
- Apply a throwaway local CMake change that skips `src/frontend` and the Qt5 `find_package` when building fcitx only. This also becomes the draft of the upstream `ENABLE_GUI` switch.
- Configure with `-DENABLE_FCITX=ON -DCMAKE_INSTALL_PREFIX=/app/addons/OpenBangla` into a scratch DESTDIR, then build.
- Pass: `openbangla.so`, the addon/inputmethod `.conf` files, layouts and data JSON all install, and the build compiles cleanly against Fcitx 5.1.23 (watch the deprecated `StandardPath` calls).
- Blocked by: 1.1.

#### Step 1.3: Offline Rust probe (S)
- Run `cargo generate-lockfile` for riti.
- Run `flatpak-cargo-generator` on the riti lock and `src/platform/Cargo.lock`, and check both resolve fully offline (`CARGO_NET_OFFLINE=true`, vendored `CARGO_HOME`).
- Record the minimum Rust version of `system-theme`, and whether `src/platform` is built at all in the engine-only configuration. If it is, check whether its zbus/tokio dependency is needed.
- Blocked by: 1.1.

#### Step 1.4: Runtime test without a manifest (M)
- Run the host's Fcitx5 Flatpak with the scratch add-on on its paths: `--filesystem=<scratch>` plus `--command=sh -c 'FCITX_ADDON_DIRS=<scratch>/lib/fcitx5:/app/lib/fcitx5 XDG_DATA_DIRS=<scratch>/share:… fcitx5-bin -r'`.
- Check:
  - (a) the add-on loads (`fcitx5-diagnose`)
  - (b) with no `OpenBangla/Keyboard.conf`, the default layout is Avro Phonetic, and `ami banglay gan gai` produces `আমি বাংলায় গান গাই` with candidates
  - (c) typing works in Kate (Flatpak), a native Qt app, a GTK app, and an XWayland app
  - (d) the tray/kimpanel icon shows, or how it fails
  - (e) where config and user data land inside the sandbox
- If the default isn't usable without the GUI, fall back to config: work out the minimal `Keyboard.conf` keys and decide whether a fcitx-native config (in-engine options shown by fcitx5-configtool) is the right upstream ask. **This is the main risk to "engine-only v1".**
- Blocked by: 1.2, 1.3.

#### Step 1.5: Qt6 GUI port sizing (S)
- Make a throwaway Qt6 port of `src/frontend` (Qt5→Qt6 CMake targets, `QStringRef`, `QRegExp`, …).
- Build it against KDE 6.11 and launch it inside the sandbox (`--command=openbangla-gui`).
- Record the diff size and what breaks. This sizes the upstream Qt6 PR.
- Blocked by: 1.2.

#### Checkpoint A
Present the probe results to the user. If 1.4(b) fails, the "engine-only v1" decision gets re-examined: the decision stays, but the information behind it changed.

### Phase 2: Upstream engagement (user posts; Claude researches, drafts code, tests)
Verified when: an upstream issue is open and the maintainer has responded, and each requested change is either merged or has a decided fallback.

#### Step 2.1: User opens an upstream issue (XS, user)
- The user writes and posts it from their own account. Claude provides a factual brief of the findings and asks, not the text.
- The asks:
  - (1) an `ENABLE_GUI` (or engine-only) build switch
  - (2) Qt6 build support, or whatever plan the maintainer prefers
  - (3) commit `Cargo.lock` to riti (#362)
  - (4) add `org.fcitx.Fcitx5.Addon.OpenBangla.metainfo.xml` (type=addon) upstream, plus icons in a layout the Fcitx5 `fcitx5-all-icons` module can pick up
  - (5) tag 3.0.0
  - (6) consent to the user maintaining the Flathub add-on, or co-maintainership
- **Confirm-the-human-did-it step:** record the issue URL in the plan before moving on.
- Blocked by: Checkpoint A.

#### Step 2.2: Upstream code PRs (S each, Claude writes and tests, user reviews and opens them)
- Draft PRs on a fork of OpenBangla-Keyboard and on riti. **Disclose AI assistance in each PR body.**
- The PRs:
  - PR-a: `ENABLE_GUI` switch (from 1.2)
  - PR-b: addon metainfo, with release entries following upstream's own metainfo style
  - PR-c: riti Cargo.lock
  - PR-d: Qt6 port (from 1.5, only if the maintainer agrees)
- Each PR builds in the probe shell from 1.1 and passes its tests (`cargo test` in riti).
- Blocked by: 2.1, and the maintainer's stance on each item.
- Fallback if upstream is silent for longer than the timeout the user sets: carry the minimal patches in the Flathub repo. The user writes them by hand, or a disclosed AI patch is used, at reviewer discretion. This is decided at that point with the user.

### Phase 3: Packaging (USER writes; Claude runs builds and explains errors)
Verified when: `scripts/build.sh` installs `org.fcitx.Fcitx5.Addon.OpenBangla` (`--user`), `scripts/lint.sh` passes (manifest and repo), and `scripts/test-run.sh` restarts Fcitx5 with the add-on listed and typing working.

#### Step 3.1: Flathub repo skeleton (XS, user)
- Create `flathub/` as its own git repo containing the manifest, `flathub.json`, cargo sources and any license install.
- The user studies the human-written reference manifests:
  - `flathub/org.fcitx.Fcitx5.Addon.McBopomofo` (simple CMake add-on)
  - `.Chewing` (rust-stable + corrosion + `CARGO_HOME` + cargo-sources)
  - Flathub's manifest and metainfo docs
- Claude explains concepts on request, but doesn't write manifest lines.
- Blocked by: Checkpoint A.

#### Step 3.2: Cargo sources (XS, user runs)
- The user runs `scripts/gen-cargo-sources.sh <obk-commit>`. It generates the riti lock if upstream has none, runs the pinned generator, and writes `flathub/cargo-sources.json`.
- The output is deterministic tool output, not AI content.
- Blocked by: 1.3.

#### Step 3.3: Build–lint–test loop (M, user writes, Claude debugs)
- Iterate until green, using:
  - `scripts/build.sh` (`flatpak-builder --user --install --force-clean --install-deps-from=flathub --repo=repo build-dir flathub/<manifest>`, with `--disable-rofiles-fuse` if FUSE fails in the container)
  - `scripts/lint.sh` (`flatpak-builder-lint manifest` + `repo`)
  - `scripts/test-run.sh` (restart host Fcitx5, run `fcitx5-diagnose`, show the add-on list)
- Claude reads the logs and explains root causes; the user edits.
- Blocked by: 3.1, 3.2.

### Phase 4: Test matrix and interim distribution (Claude tests, user confirms)
Verified when: every cell of the matrix in `docs/research.md` is PASS or a documented known-issue, and `docs/user-setup.md` has been validated by following it.

#### Step 4.1: Test matrix (M)
- **Environments:** KDE Plasma Wayland (this host), GNOME Wayland (a Silverblue VM in GNOME Boxes or similar; it needs the ibus frontend + Kimpanel).
- **Apps:** Flatpak apps, native host apps, XWayland apps.
- **Behaviour:** the Avro phonetic sample sentence, candidate window, toggle hotkey, persistence across restarts, the tray icon.
- Blocked by: 3.3.

#### Step 4.2: Interim bundle (S)
- `scripts/bundle.sh` → `flatpak build-bundle --runtime`. The user publishes the `.flatpak` as a GitHub pre-release on the workspace repo for early testers while Flathub review is pending.
- **Open choice:** the release notes are the user's, since the bundle is built from their manifest.
- Blocked by: 4.1.

### Phase 5: Flathub submission (USER only)
Verified when: the Flathub PR is merged, `flathub/org.fcitx.Fcitx5.Addon.OpenBangla` exists, and `flatpak install flathub org.fcitx.Fcitx5.Addon.OpenBangla` works on a clean machine or user.

#### Step 5.1: Submission (user)
- Fork `flathub/flathub` with all branches, branch from `new-pr`, and open the PR "Add org.fcitx.Fcitx5.Addon.OpenBangla". The user writes the PR text, records the required demo video, and comments `bot, build`.
- **Disclosure:** state that the upstream PRs and the dev tooling were AI-assisted, if applicable. The manifest is hand-written.
- Claude takes no part in the PR, commits, or review replies.
- Blocked by: 4.1, and 2.1 consent if obtained.

#### Step 5.2: Icon follow-up (user)
- Propose adding OBK icons to `flathub/org.fcitx.Fcitx5`'s `fcitx5-all-icons` module, so the tray icon resolves on the host. This is a Flathub manifest edit, so the user writes it.
- Blocked by: 2.2 PR-b (icon layout upstream).

### Phase 6: Maintenance (ongoing)
- `docs/maintenance.md` covers the update procedure: x-checker-data opens bump PRs on Flathub, which can't regenerate cargo sources, so the user runs `gen-cargo-sources.sh`, then build, lint and test-run, then pushes the bump themselves.
- Optional workspace CI (GitHub Actions) builds the user's manifest nightly against upstream `develop` to catch breakage early. Claude may write the workflow because it lives in the workspace repo, not Flathub.
- GUI release: once upstream ships an optional/Qt6 GUI (or the planned Rust GUI), add it to the add-on and test `openbangla-gui` via the fcitx configure button (`ExternalOption BIN_DIR/openbangla-gui`). Don't clean `/bin` once the GUI ships.

## Execution notes (deviations and discoveries)
- 2026-11-12: Installing `flatpak-builder` in `dev` brought in Fedora's real `flatpak`, which hides the host system installation. Fix: `FLATPAK_SYSTEM_DIR=/run/host/var/lib/flatpak` (set in `scripts/lib.sh`).
- 2026-11-12: `flatpak kill org.fcitx.Fcitx5` is NOT respawned by KWin. Restart it by toggling `kwinrc [Wayland] InputMethod` with `kwriteconfig6 --notify` (empty, then the value), then restore the original kwinrc. `scripts/test-run.sh` needs this change.
- 2026-11-12: Added manifest-free probe harnesses: `scripts/probe-build.sh`, `scripts/probe-install.sh` (local `obk-probe` remote), `scripts/probe-type.py` (headless D-Bus typing test).
- 2026-11-12 (re-derive, for the user): the Qt6 GUI port is only 7 files / +14 −11 and runs in the sandbox. If upstream merges it, v1 could include the GUI instead of being engine-only.

- 2026-11-12: User feedback: the tray icon is missing, and it "suddenly switches to English". Pressure tests and 3 expert reviews
  traced the switching to Fcitx5 defaults, and also found upstream engine crash and text-loss bugs (docs/research.md §6.1).
  Hardening plan: `plans/pending/obk-hardening.md`.

## Not yet specified
- Phase 1.4: whether engine defaults are usable without the GUI. This decides v1's scope (Checkpoint A).
- Phase 2: the maintainer's response, and whether upstream wants to own the Flathub add-on itself. If so, the user becomes co-maintainer or helper instead.
- Phase 2.2 fallback timeout: the user sets it when the issue is posted.
- Phase 4.1 GNOME testing: VM availability is fog, researched at pickup.
- Phase 5.2: whether Flathub/fcitx accept an OBK icon entry in Fcitx5's manifest is fog.

## Assumptions (correct me before approval)
1. Toolchain installs go into the `dev` container (dnf, mutable). SDKs and org.flatpak.Builder go into the **`--user`** Flatpak installation (~2–3 GB in `~/.local/share/flatpak`). The host's system install is untouched.
2. The workspace repo name is `openbangla-keyboard-flatpak` (public, IamAndelib).
3. We build from a pinned upstream `develop` commit until 3.0.0 is tagged. Flathub accepts a commit pin, but a tag is preferred.
4. v1 is x86_64 only for local testing. Flathub builds aarch64 automatically; we don't test it locally.
5. Claude may write throwaway probe patches and upstream PR code (disclosed), and may write anything in the workspace repo. Claude never writes in `flathub/`, and never writes Flathub PR, commit or reply text.

## Always / Never
- **Always:** keep `flathub/` human-authored; pin every source by commit; record probe evidence in `docs/research.md`; update the Progress table as phases land.
- **Never:**
  - Claude editing `flathub/**` or drafting Flathub PR, commit or reply text
  - bundling Qt5 or copying SDK libraries into the extension
  - changing the host's system Flatpak installation or layering rpm-ostree packages
  - shipping IBus support (not possible via Flatpak)
  - Windows or macOS

## Verification (end to end)
1. `distrobox enter dev -- scripts/devenv-setup.sh --check` passes.
2. Probe log in `docs/research.md` shows an engine build and a typing test passing (Phase 1).
3. `scripts/build.sh && scripts/lint.sh` exit 0 on the user's manifest. `flatpak list --user | grep Addon.OpenBangla` shows it installed.
4. `scripts/test-run.sh`: `fcitx5-diagnose` lists OpenBangla. Typing `ami banglay gan gai` in Kate (Flatpak) and a native app produces `আমি বাংলায় গান গাই`.
5. After the Flathub merge: `flatpak install flathub org.fcitx.Fcitx5.Addon.OpenBangla` works on a fresh user, and the typing test passes.

## Progress
| Phase | Status |
| --- | --- |
| 0 Environment + Claude setup | **done** 2026-11-12 (`devenv-setup.sh --check` green; repo pushed) |
| 1 Feasibility probes | **done** 2026-11-12, all PASS (see docs/research.md §5); manual in-app typing + tray icon check pending user |
| A Checkpoint | **in progress**, results presented 2026-11-12 |
| H Reliability hardening | **planned** 2026-11-12, see `plans/pending/obk-hardening.md` (user asked: plan only, execute later) |
| 2 Upstream engagement | pending (fold in the hardening PRs, H5) |
| 3 Packaging (user) | pending |
| 4 Test matrix + interim bundle | pending |
| 5 Flathub submission (user) | pending |
| 6 Maintenance | ongoing |
