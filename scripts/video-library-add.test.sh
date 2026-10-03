#!/bin/bash
# Tests for video-library-add.sh. Everything runs against a throwaway library under /tmp
# (VIDEO_LIBRARY_DIR), with tiny generated videos; the real ~/dev/videos is never touched.
S=~/.claude/scripts/video-library-add.sh; pass=0; fail=0; skip=0
ok() { pass=$((pass+1)); echo "ok   $1"; }; bad() { fail=$((fail+1)); echo "FAIL $1"; }
T=$(mktemp -d /tmp/vla-test.XXXX); export VIDEO_LIBRARY_DIR="$T/lib"
trap 'rm -rf "$T"' EXIT
ffmpeg -v error -f lavfi -i testsrc2=size=1080x1920:rate=30 -t 2 -pix_fmt yuv420p "$T/v.mp4" || { echo "ffmpeg failed"; exit 1; }
ffmpeg -v error -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 3 -pix_fmt yuv420p "$T/h.mp4"
printf 'caption text\n' > "$T/caption.txt"; printf 'thumb' > "$T/thumb.png"
IDX="$T/lib/.index.tsv"; RD="$T/lib/README.md"
rows() { [ -f "$IDX" ] && tail -n +2 "$IDX" | grep -c . || echo 0; }
links() { grep -cF "[$1](" "$RD"; }   # lines in the README that link to a folder
ready_block() { awk '/^## Ready to post/{f=1;next} /^## /{f=0} f' "$RD"; }

# 1. a new row: folder, clone, index row, README row in Ready and in the brand table
"$S" zalo-kabche reels "2026-10-02 first-reel" "$T/v.mp4" --text "$T/caption.txt" --what "First reel" >/dev/null; rc=$?
D="$T/lib/zalo-kabche/reels/2026-10-02 first-reel"
[ $rc -eq 0 ] && [ -f "$D/reel.mp4" ] && [ -f "$D/caption.txt" ] && [ "$(rows)" = 1 ] && grep -qF $'\t0:02\t9:16 1080x1920\tready\t' "$IDX" \
  && [ "$(links 'zalo-kabche/reels/2026-10-02 first-reel')" = 2 ] && ready_block | grep -qF 'first-reel' \
  && ok "new row: clone + caption + index row (0:02, 9:16 1080x1920) + README rows" || bad "new row rc=$rc rows=$(rows)"

# 2. the same call again updates in place: one index row, still two README lines
"$S" zalo-kabche reels "2026-10-02 first-reel" "$T/v.mp4" --text "$T/caption.txt" >/dev/null; rc=$?
[ $rc -eq 0 ] && [ "$(rows)" = 1 ] && [ "$(links 'zalo-kabche/reels/2026-10-02 first-reel')" = 2 ] && grep -qF $'\tFirst reel\t' "$IDX" \
  && [ -z "$(ls -A "$D" | grep '^\.vla-tmp')" ] \
  && ok "re-run updates, no duplicate row, --what kept, no temp files left" || bad "re-run rc=$rc rows=$(rows)"

# 3. a missing file: exit 2, nothing written, index byte-identical
before=$(md5 -q "$IDX")
"$S" zalo-kabche reels "2026-10-02 ghost" "$T/nope.mp4" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && [ ! -e "$T/lib/zalo-kabche/reels/2026-10-02 ghost" ] && [ "$(md5 -q "$IDX")" = "$before" ] \
  && ok "missing file -> exit 2, no folder, index unchanged" || bad "missing file rc=$rc"
"$S" zalo-kabche reels "2026-10-02 ghost-cover" "$T/v.mp4" --cover "$T/nope.png" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && [ ! -e "$T/lib/zalo-kabche/reels/2026-10-02 ghost-cover" ] && ok "missing cover -> exit 2 before anything is written" || bad "missing cover rc=$rc"

# 4. a slug with spaces: one folder, quoted correctly everywhere
"$S" delta-agents product-film "2026-09-25 again film master cut" "$T/h.mp4" --what "Again film" >/dev/null; rc=$?
D4="$T/lib/delta-agents/product-film/2026-09-25 again film master cut"
[ $rc -eq 0 ] && [ -f "$D4/final.mp4" ] && [ "$(rows)" = 2 ] && grep -qF "[delta-agents/product-film/2026-09-25 again film master cut](<delta-agents/product-film/2026-09-25 again film master cut/>)" "$RD" \
  && ok "slug with spaces -> one folder, final.mp4, linked row" || bad "slug with spaces rc=$rc"

# 5. a status change moves the row out of Ready and keeps one row
"$S" zalo-kabche reels "2026-10-02 first-reel" "$T/v.mp4" --status posted:instagram:2026-10-03 >/dev/null; rc=$?
[ $rc -eq 0 ] && [ "$(rows)" = 2 ] && grep -qF $'\tposted:instagram:2026-10-03\t' "$IDX" && ! ready_block | grep -qF 'first-reel' \
  && grep -qF '| posted instagram 2026-10-03 |' "$RD" && [ "$(links 'zalo-kabche/reels/2026-10-02 first-reel')" = 1 ] \
  && ok "status change -> posted row, gone from Ready, still one row" || bad "status change rc=$rc"
"$S" zalo-kabche reels "2026-10-02 first-reel" "$T/v.mp4" --status maybe >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && grep -qF $'\tposted:instagram:2026-10-03\t' "$IDX" && ok "a malformed status is refused, row untouched" || bad "bad status rc=$rc"

# 6. an unknown brand is refused before anything is created
"$S" acme reels "2026-10-02 x" "$T/v.mp4" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && [ ! -e "$T/lib/acme" ] && [ "$(rows)" = 2 ] && ok "unknown brand -> exit 2, nothing created" || bad "unknown brand rc=$rc"
"$S" zalo-kabche reels "first-reel" "$T/v.mp4" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "folder name without a date is refused" || bad "undated folder rc=$rc"

# 7. a clone on the same volume costs no space, is its own file, and survives the original
dd if=/dev/urandom of="$T/big.mp4" bs=1048576 count=256 2>/dev/null
sync; a=$(df -k "$T" | tail -1 | awk '{print $4}')
"$S" cmaa ads "2026-10-02 big" "$T/big.mp4" >/dev/null 2>&1; rc=$?
sync; b=$(df -k "$T" | tail -1 | awk '{print $4}')
used=$(( (a - b) / 1024 ))
B="$T/lib/cmaa/ads/2026-10-02 big/final.mp4"
if [ $rc -eq 0 ] && [ $used -lt 32 ] && cmp -s "$T/big.mp4" "$B" && [ "$(stat -f %i "$T/big.mp4")" != "$(stat -f %i "$B")" ]; then
  rm -f "$T/big.mp4"
  [ "$(stat -f %z "$B")" = 268435456 ] && ok "256 MiB clone used ${used} MiB of disk, separate inode, survives deleting the original" || bad "clone lost after deleting original"
else bad "clone rc=$rc used=${used}MiB"; fi

# 8. the README is well formed: one block, Ready before the brand tables, 7 cells per row,
#    hand-written text outside the markers survives, no folder listed twice in a brand table
printf '\nA hand-written note below the index.\n' >> "$RD"
"$S" --render; rc=$?
nb=$(grep -c '^<!-- INDEX:BEGIN' "$RD"); ne=$(grep -c '^<!-- INDEX:END -->' "$RD")
lr=$(grep -n '^## Ready to post' "$RD" | cut -d: -f1); lb=$(grep -n '^## All videos by brand' "$RD" | cut -d: -f1)
badrows=$(grep '^|' "$RD" | awk -F'|' 'NF!=9' | wc -l | tr -d ' ')
seps=$(grep -c '^|---|---|---|---|---|---|---|$' "$RD"); hdrs=$(grep -c '^| Folder | What it is | Length | Aspect | Status | Source | Copy |$' "$RD")
dups=$(awk '/^## All videos by brand/{f=1} f && /^\| \[/' "$RD" | cut -d'|' -f2 | sort | uniq -d | wc -l | tr -d ' ')
[ $rc -eq 0 ] && [ "$nb" = 1 ] && [ "$ne" = 1 ] && [ "$lr" -lt "$lb" ] && [ "$badrows" = 0 ] && [ "$seps" = "$hdrs" ] && [ "$dups" = 0 ] \
  && grep -qF 'A hand-written note below the index.' "$RD" && grep -qF '3 video folders in the library: 2 ready to post, 1 posted, 0 unknown.' "$RD" \
  && ok "README well formed (1 block, Ready first, 7 cells/row, $hdrs tables, hand text kept, counts right)" \
  || bad "README shape nb=$nb ne=$ne ready=$lr brand=$lb badrows=$badrows seps=$seps hdrs=$hdrs dups=$dups"
m1=$(md5 -q "$RD"); "$S" --render; [ "$(md5 -q "$RD")" = "$m1" ] && ok "--render is idempotent" || bad "--render changed the README"

# 9. a youtube cover lands in thumbnails/, a renamed text keeps its new name, an em dash in --what is normalized
"$S" zalo-kabche youtube "2026-10-01 long-form" "$T/h.mp4" --cover "$T/thumb.png" --text "description.txt=$T/caption.txt" \
  --what $'Long form \xe2\x80\x94 the whiteboard one' >/dev/null; rc=$?
D9="$T/lib/zalo-kabche/youtube/2026-10-01 long-form"
[ $rc -eq 0 ] && [ -f "$D9/thumbnails/thumb.png" ] && [ -f "$D9/description.txt" ] && grep -qF 'Long form, the whiteboard one' "$RD" \
  && bash ~/.claude/scripts/dash-check.sh "$RD" "$IDX" >/dev/null \
  && ok "youtube cover -> thumbnails/, name=path text rename, em dash normalized (dash-check 0)" || bad "youtube/cover/text rc=$rc"

# 10. a source on another volume is refused (cp -c would silently make a full copy there)
IMG="$T/vol.dmg"; MNT="$T/mnt"
if hdiutil create -size 20m -fs HFS+ -volname vlatest "$IMG" >/dev/null 2>&1 && mkdir -p "$MNT" && hdiutil attach -nobrowse -mountpoint "$MNT" "$IMG" >/dev/null 2>&1; then
  cp "$T/v.mp4" "$MNT/other.mp4"
  "$S" zalo-kabche reels "2026-10-02 other-volume" "$MNT/other.mp4" >/dev/null 2>&1; rc=$?
  [ $rc -eq 3 ] && [ ! -e "$T/lib/zalo-kabche/reels/2026-10-02 other-volume" ] && ok "source on another volume -> exit 3, nothing written" || bad "other volume rc=$rc"
  ln -s "$MNT/other.mp4" "$T/otherlink.mp4"
  "$S" zalo-kabche reels "2026-10-02 other-volume-link" "$T/otherlink.mp4" >/dev/null 2>&1; rc=$?
  [ $rc -eq 3 ] && [ ! -e "$T/lib/zalo-kabche/reels/2026-10-02 other-volume-link" ] && ok "symlink to another volume -> exit 3, nothing written" || bad "symlink to other volume rc=$rc"
  mkdir -p "$MNT/lib"; ln -s "$MNT/lib" "$T/liblink"
  VIDEO_LIBRARY_DIR="$T/liblink" "$S" zalo-kabche reels "2026-10-02 lib-on-other-volume" "$T/v.mp4" >/dev/null 2>&1; rc=$?
  [ $rc -eq 3 ] && [ ! -e "$MNT/lib/zalo-kabche" ] && ok "library root symlinked to another volume -> exit 3, nothing written" || bad "symlinked library root rc=$rc"
  hdiutil detach "$MNT" >/dev/null 2>&1 || hdiutil detach -force "$MNT" >/dev/null 2>&1
else skip=$((skip+3)); echo "skip other-volume cases (hdiutil unavailable)"; fi

# 11. a symlink on the same volume: the real file is cloned (not the link), Source is its real path
ln -s "$T/v.mp4" "$T/link.mp4"
"$S" zalo-kabche reels "2026-10-02 via-link" "$T/link.mp4" >/dev/null 2>&1; rc=$?
D11="$T/lib/zalo-kabche/reels/2026-10-02 via-link"; RV=$(/bin/realpath "$T/v.mp4")
[ $rc -eq 0 ] && [ -f "$D11/reel.mp4" ] && [ ! -L "$D11/reel.mp4" ] && cmp -s "$T/v.mp4" "$D11/reel.mp4" && grep -qF $'\t'"$RV"$'\tclone\t' "$IDX" \
  && ok "symlink source -> real file cloned, Source is the resolved path" || bad "symlink source rc=$rc"

# 12. relative paths: the Source column is absolute, a relative name=<file> text works, ~/ is expanded
(cd "$T" && "$S" zalo-kabche youtube "2026-10-01 relative" h.mp4 --text "description.txt=caption.txt" >/dev/null 2>&1); rc=$?
D12="$T/lib/zalo-kabche/youtube/2026-10-01 relative"; RH=$(/bin/realpath "$T/h.mp4")
[ $rc -eq 0 ] && [ -f "$D12/description.txt" ] && grep -qF $'\t'"$RH"$'\tclone\t' "$IDX" \
  && ok "relative video and name=relative text -> absolute Source, renamed text" || bad "relative paths rc=$rc"
HOME="$T" "$S" zalo-kabche youtube "2026-10-01 relative" "$T/h.mp4" --text "notes.txt=~/caption.txt" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ -f "$D12/notes.txt" ] && ok "name=~/file text -> ~ expanded" || bad "tilde text rc=$rc"

# 13. a status-only re-run with just the main cut keeps the other cuts listed
"$S" zalo-kabche reels "2026-10-02 three-cuts" "$T/v.mp4" --video "$T/h.mp4" --video "$T/v.mp4" >/dev/null; rc1=$?
"$S" zalo-kabche reels "2026-10-02 three-cuts" "$T/v.mp4" --status posted:instagram:2026-10-04 >/dev/null; rc=$?
[ $rc1 -eq 0 ] && [ $rc -eq 0 ] && grep -qF $'\tposted:instagram:2026-10-04\t' "$IDX" \
  && grep -F 'zalo-kabche/reels/2026-10-02 three-cuts' "$IDX" | grep -qE $'\treel\\.mp4;reel-2\\.mp4;reel-3\\.mp4$' \
  && grep -F 'zalo-kabche/reels/2026-10-02 three-cuts' "$IDX" | grep -qF '9:16 1080x1920 / 16:9 1920x1080' \
  && ok "status-only re-run keeps reel-2 and reel-3 listed, aspect of every cut" || bad "status-only re-run rc=$rc"

# 14. two covers with the same file name would overwrite each other in thumbnails/: refused, nothing written
mkdir -p "$T/a" "$T/b"; printf 'a' > "$T/a/thumb.png"; printf 'b' > "$T/b/thumb.png"
"$S" zalo-kabche youtube "2026-10-01 dup-thumbs" "$T/h.mp4" --cover "$T/a/thumb.png" --cover "$T/b/thumb.png" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && [ ! -e "$T/lib/zalo-kabche/youtube/2026-10-01 dup-thumbs" ] && ok "same-name covers -> exit 2, nothing written" || bad "same-name covers rc=$rc"

# 15. --set-status changes only the status: no clone, no new cut, the folder and the videos column untouched
D15="$T/lib/zalo-kabche/reels/2026-10-02 three-cuts"
mv "$D15/reel-2.mp4" "$D15/reel-v1-h2.mp4"   # a hand-named cut, like the whiteboard reel folders
sed -i '' 's/reel\.mp4;reel-2\.mp4;reel-3\.mp4$/reel.mp4;reel-v1-h2.mp4;reel-3.mp4/' "$IDX"
l1=$(ls -li "$D15"); v1=$(grep -F 'zalo-kabche/reels/2026-10-02 three-cuts' "$IDX" | cut -f10)
"$S" --set-status "zalo-kabche/reels/2026-10-02 three-cuts" posted:tiktok:2026-10-05 >/dev/null; rc=$?
[ $rc -eq 0 ] && [ "$(ls -li "$D15")" = "$l1" ] && [ "$(grep -F 'zalo-kabche/reels/2026-10-02 three-cuts' "$IDX" | cut -f10)" = "$v1" ] \
  && grep -F 'zalo-kabche/reels/2026-10-02 three-cuts' "$IDX" | grep -qF $'\tposted:tiktok:2026-10-05\t' && grep -qF '| posted tiktok 2026-10-05 |' "$RD" \
  && ok "--set-status -> status changed, folder and cuts untouched (hand-named cut kept, no reel-2 added)" || bad "--set-status rc=$rc"
before=$(md5 -q "$IDX")
"$S" --set-status "zalo-kabche/reels/2026-10-02 nowhere" posted:tiktok:2026-10-05 >/dev/null 2>&1; rc1=$?
"$S" --set-status "zalo-kabche/reels/2026-10-02 three-cuts" posted >/dev/null 2>&1; rc2=$?
[ $rc1 -eq 2 ] && [ $rc2 -eq 2 ] && [ "$(md5 -q "$IDX")" = "$before" ] && [ ! -e "$T/lib/zalo-kabche/reels/2026-10-02 nowhere" ] \
  && ok "--set-status on a missing folder or with a malformed status -> exit 2, index unchanged" || bad "--set-status refusals rc1=$rc1 rc2=$rc2"

echo "$pass/$((pass+fail)) passed, $skip skipped"; [ $fail -eq 0 ]
