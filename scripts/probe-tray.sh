#!/usr/bin/env bash
# Check that the OpenBangla settings app's tray icon is something the HOST tray
# can draw. Runs on the host (needs the session's StatusNotifierWatcher).
#
# Starts openbangla-gui --tray inside the Fcitx5 sandbox for a few seconds, with
# the add-on's share/ on XDG_DATA_DIRS exactly as when Fcitx5's configure button
# launches it, then reads the new StatusNotifierItem's properties. Inside a
# sandbox the host can't resolve our icon *name*, so the item must carry pixels.
#
# PASS: IconPixmap non-empty (IconName may also be set).
# FAIL: IconName set but IconPixmap empty, i.e. an empty slot in the panel.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

watcher() {
    host gdbus call --session --dest org.kde.StatusNotifierWatcher \
        --object-path /StatusNotifierWatcher \
        --method org.freedesktop.DBus.Properties.Get \
        org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems
}
prop() {
    host gdbus call --session --dest "$1" --object-path "$2" \
        --method org.freedesktop.DBus.Properties.Get org.kde.StatusNotifierItem "$3"
}

before="$(watcher)"
# shellcheck disable=SC2016  # expands inside the sandbox, on purpose
host timeout 8 flatpak run --die-with-parent --command=sh "$FCITX_APP" -c \
    'export XDG_DATA_DIRS=/app/addons/OpenBangla/share:$XDG_DATA_DIRS
     exec /app/addons/OpenBangla/bin/openbangla-gui --tray' >/dev/null 2>&1 &
sleep 4
after="$(watcher)"

item=""
for i in $(grep -o "':[0-9.]*/[A-Za-z_/]*'" <<<"$after" | tr -d "'"); do
    grep -q -- "$i" <<<"$before" || { item="$i"; break; }
done
[[ -n "$item" ]] || { wait; die "the settings app registered no tray item"; }
svc="${item%%/*}" path="/${item#*/}"
name="$(prop "$svc" "$path" IconName)"
pixmap="$(prop "$svc" "$path" IconPixmap)"
wait
log "tray item: IconName=$name"
if [[ "$pixmap" == *"@a(iiay) []"* ]]; then
    die "FAIL: tray icon has no pixels; the host tray can only look it up by name ($name) and shows an empty slot"
fi
log "PASS: tray icon carries pixels (${pixmap:0:40}…)"
