# local/: AI-written manifest for local builds (never for Flathub)

`org.fcitx.Fcitx5.Addon.OpenBangla.yml` here was written by Claude. It builds the
real Flatpak add-on with Flatpak's own tooling, so we can test it, make `.flatpak`
bundles for testers, and spot problems early.

**It must never be submitted to Flathub, in whole or in part.** Flathub's rules:
*"Flathub manifests must not contain AI-generated or AI-assisted content. Disclosure
does not exempt manifests from this restriction."* A human reviewing or editing an
AI-written manifest doesn't change that.

## The Flathub manifest (`flathub/`, written by the maintainer)
- Write it yourself, without copying from this file. Learn from Flathub's
  human-written add-on manifests:
  - https://github.com/flathub/org.fcitx.Fcitx5.Addon.McBopomofo (a simple CMake add-on)
  - https://github.com/flathub/org.fcitx.Fcitx5.Addon.Chewing (Rust + CMake, the closest match)
- Claude can explain concepts, run `scripts/build.sh` / `scripts/lint.sh` on your file,
  and explain errors, but it won't write or suggest lines for it.
- The dependency lists (`cargo-sources-*.json`, `riti-Cargo.lock`) are tool output from
  `scripts/gen-cargo-sources.sh`, not AI-written. Regenerate your own into `flathub/`.

## Commands
```sh
MANIFEST=local/org.fcitx.Fcitx5.Addon.OpenBangla.yml scripts/build.sh   # build + install (--user)
MANIFEST=local/org.fcitx.Fcitx5.Addon.OpenBangla.yml scripts/lint.sh    # Flathub linter
scripts/gen-cargo-sources.sh -o local <obk-checkout>                     # refresh dependency lists
```
