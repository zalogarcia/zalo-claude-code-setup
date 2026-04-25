#!/bin/bash
input=$(cat)
now=$(date +%s)

five_h=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty' 2>/dev/null)
five_r=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty' 2>/dev/null)
seven_d=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty' 2>/dev/null)
seven_r=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty' 2>/dev/null)
ctx=$(echo "$input" | jq -r '.context_window.used_percentage // empty' 2>/dev/null)

fmt_short() {
  local left=$(( $1 - now ))
  [ "$left" -le 0 ] && echo "now" && return
  local h=$(( left / 3600 )) m=$(( (left % 3600) / 60 ))
  [ "$h" -gt 0 ] && echo "${h}h${m}m" || echo "${m}m"
}
fmt_long() {
  local left=$(( $1 - now ))
  [ "$left" -le 0 ] && echo "now" && return
  local d=$(( left / 86400 )) h=$(( (left % 86400) / 3600 ))
  [ "$d" -gt 0 ] && echo "${d}d${h}h" || echo "${h}h"
}

parts=""
[ -n "$ctx" ] && parts="${ctx}% ctx"
if [ -n "$five_h" ]; then
  ttl=""; [ -n "$five_r" ] && ttl=" $(fmt_short "$five_r")"
  parts="${parts:+$parts · }5h ${five_h%.*}%${ttl}"
fi
if [ -n "$seven_d" ]; then
  ttl=""; [ -n "$seven_r" ] && ttl=" $(fmt_long "$seven_r")"
  parts="${parts:+$parts · }wk ${seven_d%.*}%${ttl}"
fi
[ -n "$parts" ] && echo "$parts"
