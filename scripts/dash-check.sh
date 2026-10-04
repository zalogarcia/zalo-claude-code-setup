#!/bin/bash
# dash-check.sh <file>...  : count em and en dashes per file, exit 1 if any found.
# Exists because `LC_ALL=C grep $'\xe2\x80\x93\|\xe2\x80\x94'` returns 0 on files that
# contain em dashes on this Mac (the \| alternation with byte escapes, measured 2026-09-19).
# Runs its own positive control first so a zero is a measurement, not a broken tool.
set -u
ctrl=$(printf 'a\xe2\x80\x94b \xe2\x80\x93 c' | python3 -c 'import sys;s=sys.stdin.read();print(s.count("–")+s.count("—"))')
if [ "$ctrl" != "2" ]; then echo "dash-check: positive control failed ($ctrl != 2)" >&2; exit 2; fi
rc=0
for f in "$@"; do
  if [ ! -f "$f" ]; then echo "missing: $f" >&2; rc=2; continue; fi
  n=$(python3 -c 'import sys;s=open(sys.argv[1],encoding="utf-8",errors="replace").read();print(s.count("–")+s.count("—"))' "$f")
  echo "$n $f"
  [ "$n" != "0" ] && rc=1
done
exit $rc
