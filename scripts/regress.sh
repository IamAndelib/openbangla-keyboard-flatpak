#!/usr/bin/env bash
# Regression suite for the OpenBangla engine: every scenario runs in its OWN
# fresh, isolated Fcitx5 (private bus + private XDG dirs via stress-isolated.sh),
# so a crash or a seeded file can't leak into the next scenario.
#
#   scripts/regress.sh                  # fast regression set (F1–F7)
#   scripts/regress.sh --slow           # + rss-slope (F8) and selection-growth (F9)
#   scripts/regress.sh --behaviour      # + shift-tap,new-ic,refocus,soak,burst (one daemon)
#   CONFIG=default scripts/regress.sh   # Fcitx5 config profile (default: recommended)
#
# Exit status is non-zero if any scenario FAILs.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
ensure_container "$0" "$@"

config="${CONFIG:-recommended}"
fast=(persist-empty two-ic corrupt-selection unwritable-selection invalid-layout
      torn-autocorrect page-commit suffix-dup deactivate-midword reload-count)
slow=(rss-slope selection-growth)
run=("${fast[@]}")
behaviour=0
for arg in "$@"; do
    case "$arg" in
        --slow) run+=("${slow[@]}") ;;
        --behaviour) behaviour=1 ;;
        *) die "unknown option $arg" ;;
    esac
done

mkdir -p "$OUT_DIR"
summary="$OUT_DIR/regress-$(date +%Y%m%d-%H%M%S).txt"
fails=0
one() {
    local out line
    out="$("$ROOT/scripts/stress-isolated.sh" --config "$config" "$@" 2>&1 || true)"
    line="$(grep -E '^(PASS|FAIL)  ' <<<"$out" || true)"
    if [[ -z "$line" ]]; then
        line="FAIL  $*  (no result; runner output follows)"$'\n'"$(tail -5 <<<"$out")"
    fi
    printf '%s\n' "$line" | tee -a "$summary"
    grep -q '^FAIL' <<<"$line" && fails=$((fails + 1))
    return 0
}

log "regression suite, config=$config, $(git -C "$ROOT/upstream/OpenBangla-Keyboard" rev-parse --short HEAD 2>/dev/null || echo '?') (upstream checkout)"
log "installed add-on: $(flatpak info "$APP_ID" 2>/dev/null | awk '/Origin:/{o=$2} /Commit:/{c=substr($2,1,12)} END{print o " " c}')"
for s in "${run[@]}"; do one --only "$s"; done
if (( behaviour )); then one --only shift-tap,new-ic,refocus,soak,burst; fi

log "summary: $fails failing; saved to ${summary#"$ROOT"/}"
(( fails == 0 ))
