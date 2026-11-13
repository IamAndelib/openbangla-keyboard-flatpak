# Reliability hardening: OBK Fcitx5 add-on
Parent plan: `plans/pending/obk-flathub.md` (this slots between Phase 1 and Phase 3).
Evidence: `docs/research.md` §6 and §6.1. Reviewer reproductions: `tests/reviewer-repros/`.
Status: **planned, not started.** The user approved the decisions below on 2026-11-12 and asked for a plan only;
execution is a later session.

## Context
- User report: typing works, but it "suddenly switches to English", and the tray icon is missing.
- The switch is explained by two Fcitx5 defaults: Left-Shift tap = AltTrigger, and per-window state starting in English.
- Three independent expert reviews (2026-11-12) also found upstream engine bugs:
  - three crash classes that kill the whole Fcitx5 daemon (one persists on disk)
  - two silent text-loss bugs
  - learned-candidate corruption
  - a per-word config re-read
  - RSS growth of roughly 0.6 MB per 25k keys
- The pressure harness itself has fidelity gaps.

## Decisions (user, 2026-11-12)
| # | Decision | Chosen |
| --- | --- | --- |
| D1 | Fcitx5 config on the user's machine | Apply all three: `AltTriggerKeys` empty, `ShareInputState=All`, `ActiveByDefault=True` (Ctrl+Space stays the toggle) |
| D2 | Engine bugs | Claude writes minimal fixes, each with a failing regression test first, on local OBK and riti branches, then installs a patched `obk-probe` build for daily use. The user reviews and opens upstream PRs (AI assistance disclosed). |
| D3 | Tray icon, interim | Classic UI "Prefer Text Icon" (tray shows বা). Proper fix via upstream + Flathub (user-authored Flathub part). |
| D4 | Public git history contains the local username in commits `712d602`, `a6dfe03` (paths in copied scripts and a `.pyc`) | Rewrite history and force-push `main` |

## Phases (execution order; highest risk first; every step proven by a named check)

### H0: Scrub git history (D4) (S)
- **Do:**
  - install `git-filter-repo` in `dev`
  - back up the repo (`git bundle create out/pre-scrub.bundle --all`)
  - run `git filter-repo --replace-text <rules> --invert-paths --path-glob 'scripts/__pycache__/*'`, with rules mapping the
    local username and absolute scratch/workspace paths to placeholders
  - re-add `origin`, then `git push --force-with-lease origin main`
- **Verify:** `git log --all -S <local-user>` is empty, and `gh api repos/IamAndelib/openbangla-keyboard-flatpak/commits` matches the local HEAD.
  The tree still builds: `scripts/devenv-setup.sh --check` and `shellcheck -x scripts/*.sh`.
- **Blocked by:** none. It runs first so later commits are made on the rewritten history.

### H1: User Fcitx5 config + text tray icon (D1, D3) (S)
- **Do:**
  - Back up `~/.var/app/org.fcitx.Fcitx5/config/fcitx5/{config,conf/classicui.conf}` to `out/backup/<date>/`.
  - Apply through Fcitx5's own API, not by hand-editing the files: `Controller1.SetConfig("fcitx://config/global", {Hotkey:{AltTriggerKeys:{}}, Behavior:{ShareInputState:"All", ActiveByDefault:"True"}})`.
    - Prototype: `tests/reviewer-repros/harness_setconfig.py`. Promote it to `scripts/fcitx-config.py` with `--apply`, `--show` and `--restore`.
  - Apply `SetConfig("fcitx://config/addon/classicui", {PreferTextIcon:"True"})` the same way.
- **Verify:**
  - `GetConfig` shows the values.
  - `scripts/stress-isolated.sh --config hardened --only shift-tap,new-ic` still passes, with a third profile `user-recommended` added to the runner.
  - Manual: a Left-Shift tap no longer switches, and a new window opens in Bangla.
  - The tray shows বা (user confirms visually).
- **Rollback:** `scripts/fcitx-config.py --restore out/backup/<date>`.
- **Blocked by:** none (independent of H2–H5).

### H2: Harness fidelity first (tests before fixes) (M)
Make `stress-ime.py` able to fail on every known bug before any fix lands.
- **Fidelity:**
  - capability `0x72` (Preedit | FormattedPreedit | SurroundingText | ClientUnfocusCommit), as on Wayland, plus a `--caps` switch
  - content checks: NFC-compare commits against expected words in burst and soak
  - in isolation, "focus stolen" counts as FAIL
  - remove the `pgrep fcitx5-bin` RSS fallback, which could match the live daemon; use `owner_pid()` only
- **Isolation:** unique run dirs (`out/stress/<profile>-<ts>`) so concurrent runs can't clobber each other.
- **New regression scenarios, one per bug:**
  - `persist-empty` (F1)
  - `two-ic` (F2; expects no crash and no cross-context reset)
  - `corrupt-json` (unwritable file, missing layout path, torn autocorrect) (F3)
  - `page-commit` (F4)
  - `suffix-dup` (F5)
  - `deactivate-midword` (F6)
  - `reload-count` (F7; counts "Reload openbangla configuration" log lines)
  - `rss-slope` (F8; chunked 25k-key soak, linear-fit slope with a threshold)
  - `selection-growth` (F9; size after N keys)
- Liveness: a check after every scenario that the daemon PID is unchanged.
- **Verify:** against the current (unfixed) probe build, every new scenario FAILs for the documented reason; existing scenarios still PASS.
  Command: `scripts/stress-isolated.sh --config hardened --only <new scenarios>`.
- **Blocked by:** none.

### H3: riti fixes (branch `fix/robustness` on the riti submodule) (M)
- **Do:** each fix comes with a `cargo test` regression first (red), then the fix (green):
  - F1: skip empty bases at `phonetic/suggestion.rs:265`, never store an empty key or value in `candidate_committed`,
    and drop empty or doubled values when loading.
  - F3: replace `unwrap`s on file I/O and JSON with fallbacks (log, then empty map or default layout). Write files atomically
    (temp + rename). Fall back to the Avro layout if the layout file fails to load. Wrap FFI entry points in `catch_unwind`
    so a panic returns a safe value instead of aborting fcitx5.
  - F5: add `break` after the first matching suffix, and stop writing derived values back into `selections`.
  - F9 (issue only, unless it's small): bound or trim the selection map.
- **Verify:** `cargo test` (the 44 existing tests plus the new ones) in `dev` on a copy, plus the H2 scenarios for F1/F3/F5 against a probe build
  that includes the branch.
- **Blocked by:** H2.

### H4: fcitx engine fixes (branch `fix/engine-robustness` on OBK) (M)
- **Do:**
  - F2: assign `currentIC_ = ic->watch()` and reset the riti session/suggestion on an IC change; null-check `candidateList`
    at `openbangla.cpp:337` and `142`.
  - F4: commit using `globalCursorIndex()` / `candidateFromAll()`, fall back to 0, and always end the session.
  - F6: add a `deactivate` override that commits the pending preedit (not `reset`).
  - F7: compare timestamps with `<=`, and skip the reload when the file is missing and defaults are already loaded.
- **Verify:** the H2 scenarios F2/F4/F6/F7 turn green, existing scenarios stay green, and the build has no new warnings.
- **Blocked by:** H2. It can run in parallel with H3 (different repos).

### Checkpoint B: patched daily build (S)
- **Do:**
  - Build the probe from `probe/engine-only` + `fix/engine-robustness` with riti at `fix/robustness` (`scripts/probe-build.sh engine`).
  - Run the full suite in isolation, both configs, then `scripts/probe-install.sh engine` and `scripts/test-run.sh`.
  - Run a 300k-key soak with `rss-slope`, then a heaptrack session on the isolated daemon if the slope stays above the threshold (F8).
- **Verify:** all scenarios PASS, no daemon PID change, the RSS slope is under threshold or F8 is diagnosed with a heaptrack report in `docs/research.md`.
- **The user's own check:** daily use for a few days; report any switch or crash. KWin's journal entries are checked read-only.
- **Blocked by:** H1, H3, H4.

### H5: upstream PR drafts (S each; user opens)
- **Do:**
  - One branch per fix, with commits in upstream style.
  - PR descriptions written for upstream, each containing a reproduction, test evidence and an explicit AI-assistance disclosure.
    These are OpenBangla/riti PRs, not Flathub, so this is allowed. The user reviews, edits and opens them.
  - Planned PRs:
    - riti: F1+F3, F5, Cargo.lock
    - OBK: F2, F4+F6, F7, ENABLE_GUI, Qt6, metainfo, icon rename (`Icon=fcitx-openbangla` + `data/icons/<size>/apps/` layout for `fcitx5-all-icons`)
  - Fold all of this into the Phase 2.1 upstream issue brief (`docs/upstream-brief.md`).
- **Verify:** each branch builds and passes its tests on its own, rebased on current `develop`.
- **Blocked by:** Checkpoint B.

### H6: docs (S)
- `docs/user-setup.md`: the recommended config (GUI steps + snippet), Ctrl+Space as the toggle, the text tray icon, and what
  password fields do (always English).
- Instructions for testers to reset learned data: delete `~/.var/app/org.fcitx.Fcitx5/data/openbangla-keyboard/phonetic-candidate-selection.json`
  (it may contain the F1 crash trigger or F5 junk from older builds).
- `docs/maintenance.md`: run the stress suite before every bump.
- **Blocked by:** H1 (validated settings).

### H7: proper tray icon (user-authored Flathub part)
- OBK icon-rename PR (from H5). After an OBK tag exists, **the user hand-writes** a PR to `flathub/org.fcitx.Fcitx5` adding
  OBK to the `fcitx5-all-icons` module (precedent: Unikey, McBopomofo). Claude may only explain the module and review build logs.
- **Blocked by:** H5 merged upstream, and an OBK release tag.

### Later (fog, research at pickup)
- Real-compositor end-to-end test: nested `kwin_wayland --virtual` plus a GTK4 text-input-v3 client. It covers commit/key ordering,
  per-window virtual ICs, and key repeat. It's the only fully faithful test of the user's path.
- Whether the Flatpak Fcitx5 can bind `org_kde_plasma_window_management` (affects per-window contexts). The user can check with
  read-only `Controller1.DebugInfo`.

## Execution notes
- 2026-11-14: The user asked to go **milestone by milestone, in small steps**. Stop and report after each milestone.
- H2: `missing-layout` was replaced by `invalid-layout`. A layout path that doesn't exist is safe, because riti keeps the previous layout; a torn
  layout file aborts in `fixed/method.rs:109`. The seeded files must exist before the daemon starts, because riti reads them when the add-on loads
  (`stress-ime.py --prepare`).
- H2: the Debug line "Reload openbangla configuration" only appears when Keyboard.conf exists, so `reload-count` seeds one: 15 reloads for 10 words.

- H3: riti's own `cargo fmt` baseline isn't clean, so formatting churn outside the changed hunks was reverted to keep the upstream diff minimal.
  Each commit builds and tests on its own (46/46 after the first, 53/53 after the second). The panicking `utility::read()` was removed.
  `catch_unwind` at the FFI boundary is **deferred**: every known panic site is fixed; revisit as defence in depth in H5.

## Always / Never
- **Always:**
  - Back up before touching user config.
  - Write a regression test that fails before each fix.
  - Run pressure tests only through the isolated runner (guarded XDG dirs, private bus).
  - Fingerprint the user's Fcitx5 dirs before and after.
  - Scrub absolute paths and usernames before committing copied artifacts.
- **Never:**
  - stress-test the user's live daemon
  - `flatpak kill` the user's IM
  - anything under `flathub/`
  - write Flathub PR or commit text
  - open upstream PRs on the user's behalf
  - bundle unrelated refactors into fix commits

## Progress
| Phase | Status |
| --- | --- |
| H0 History scrub | **done** 2026-11-14: username, scratch paths, session ID, `__pycache__` and AI trailers removed from history; force-pushed with lease (backup `out/pre-scrub.bundle`) |
| H1 User config + text tray icon | **done** 2026-11-14: PR #1. Applied live via `scripts/fcitx-config.py --apply` (backup `out/backup/20261114-001416`); isolated `recommended` profile 4/4 PASS. The user confirmed the tray icon shows correctly |
| H2 Harness fidelity + regression scenarios | **done (RED)** 2026-11-14: `scripts/regress.sh` gives 9/10 FAIL for the documented reason on the unfixed build. `suffix-dup` (F5) does not reproduce over D-Bus, so it is covered by a riti unit test in H3 |
| H3 riti fixes | **done** 2026-11-14: riti branch `fix/robustness` (2 commits, exported to `docs/patches/riti/`). 9 new cargo tests RED→GREEN, 53/53 pass, no warnings. The isolated regression suite turns F1 and F3 (×4) green; F2/F4/F6/F7 remain for H4 |
| H4 Engine fixes | planned |
| B Patched daily build | planned |
| H5 Upstream PR drafts | planned |
| H6 Docs | planned |
| H7 Proper tray icon (user, Flathub) | blocked on upstream tag |
