#!/usr/bin/env bash
# seedance - generate videos via Segmind Seedance 2.0 API
# Usage: ./generate.sh "prompt" [options]
set -euo pipefail

API_URL="https://api.segmind.com/v1/seedance-2.0"
API_URL_ASYNC="https://api.segmind.com/v2/seedance-2.0"
OUT_DIR_DEFAULT="$HOME/Downloads/seedance"

usage() {
  cat <<'EOF'
seedance - Generate videos via Segmind Seedance 2.0

USAGE:
  generate.sh "PROMPT" [OPTIONS]

OPTIONS:
  -d, --duration N        4|5|6|8|10|12|15  (default: 5)
  -r, --resolution X      480p|720p|1080p|4k (default: 720p)
  -a, --aspect X          16:9|9:16|1:1|4:3|3:4|21:9|adaptive (default: 16:9)
      --audio             Co-generate native synced audio (free)
      --seed N            Seed for reproducibility (-1=random, default: -1)
      --first-frame X     Image-to-video starting frame (URL or local path)
      --last-frame X      Ending frame (URL or local path; requires --first-frame)
      --ref-image X       Reference image (URL or local path; repeatable, up to 9)
      --ref-video X       Reference video, 2-15s, for motion/style transfer (URL or local path;
                          repeatable, up to 3; billed at the cheaper v2v token rate)
      --ref-audio X       Reference audio MP3 (URL or local path; repeatable, up to 3;
                          requires an image or video input alongside)
      --bitrate X         standard|high (default: standard; high ≈ 5-6x bitrate, same price)
      --async             Submit via the v2 async API and poll until done. REQUIRED for
                          long renders: the v1 sync connection is cut by a gateway at ~60s
                          ("Empty reply from server"); ref-image runs regularly exceed that.
      --return-last-frame Also return final frame as image URL
      --skip-moderation   Bypass moderation pre-filter
  -o, --output NAME       Output filename (no extension; default: seedance-<ts>)
      --dir DIR           Output directory (default: ~/Downloads/seedance)
      --api-key KEY       Override SEGMIND_API_KEY env var
      --dry-run           Print the request JSON and exit
  -h, --help              Show this help

ENV:
  SEGMIND_API_KEY   Required. Get one at https://www.segmind.com/

EXAMPLES:
  generate.sh "a corgi surfing at sunset, cinematic"
  generate.sh "Shot 1: city skyline. Shot 2: zoom to a window." -d 10 -r 720p --audio
  generate.sh "make this photo come alive" --first-frame ./hero.jpg -d 6
  generate.sh "anime style chase scene" -a 21:9 -d 8 --seed 42
EOF
}

if [[ $# -eq 0 ]]; then usage; exit 1; fi

# Helper: validate that a value-flag actually has a non-flag value following it.
# Usage: require_val "$1" "${2:-}"  → exits 1 if $2 missing or starts with '-'.
require_val() {
  local flag="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == -* ]]; then
    echo "ERROR: $flag requires a value" >&2
    exit 1
  fi
}

PROMPT=""
DURATION=5
RESOLUTION="720p"
ASPECT="16:9"
AUDIO=false
SEED=-1
FIRST_FRAME=""
LAST_FRAME=""
REF_IMAGES=()
REF_VIDEOS=()
REF_AUDIOS=()
BITRATE_MODE=""
ASYNC=false
RETURN_LAST_FRAME=false
SKIP_MODERATION=false
OUTPUT_NAME=""
OUT_DIR="$OUT_DIR_DEFAULT"
API_KEY="${SEGMIND_API_KEY:-}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -d|--duration) require_val "$1" "${2:-}"; DURATION="$2"; shift 2 ;;
    -r|--resolution) require_val "$1" "${2:-}"; RESOLUTION="$2"; shift 2 ;;
    -a|--aspect) require_val "$1" "${2:-}"; ASPECT="$2"; shift 2 ;;
    --audio) AUDIO=true; shift ;;
    --seed)
      # --seed legitimately takes negative integers (e.g. -1 = random), so use a numeric
      # validator instead of the generic require_val which rejects leading '-'.
      if [[ -z "${2:-}" ]]; then echo "ERROR: --seed requires a value" >&2; exit 1; fi
      if ! [[ "$2" =~ ^-?[0-9]+$ ]]; then echo "ERROR: --seed must be an integer (got: $2)" >&2; exit 1; fi
      SEED="$2"; shift 2 ;;
    --first-frame) require_val "$1" "${2:-}"; FIRST_FRAME="$2"; shift 2 ;;
    --last-frame) require_val "$1" "${2:-}"; LAST_FRAME="$2"; shift 2 ;;
    --ref-image) require_val "$1" "${2:-}"; REF_IMAGES+=("$2"); shift 2 ;;
    --ref-video) require_val "$1" "${2:-}"; REF_VIDEOS+=("$2"); shift 2 ;;
    --ref-audio) require_val "$1" "${2:-}"; REF_AUDIOS+=("$2"); shift 2 ;;
    --bitrate) require_val "$1" "${2:-}"; BITRATE_MODE="$2"; shift 2 ;;
    --async) ASYNC=true; shift ;;
    --return-last-frame) RETURN_LAST_FRAME=true; shift ;;
    --skip-moderation) SKIP_MODERATION=true; shift ;;
    -o|--output) require_val "$1" "${2:-}"; OUTPUT_NAME="$2"; shift 2 ;;
    --dir) require_val "$1" "${2:-}"; OUT_DIR="$2"; shift 2 ;;
    --api-key) require_val "$1" "${2:-}"; API_KEY="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --)
      # End-of-options separator: next arg is the prompt verbatim, even if it starts with '-'.
      shift
      if [[ -z "$PROMPT" && $# -gt 0 ]]; then PROMPT="$1"; shift; fi
      if [[ $# -gt 0 ]]; then echo "Unexpected arg after --: $1" >&2; exit 1; fi
      ;;
    -*) echo "Unknown flag: $1" >&2; usage; exit 1 ;;
    *)
      if [[ -z "$PROMPT" ]]; then PROMPT="$1"
      else echo "Unexpected arg: $1 (prompt already set)" >&2; exit 1
      fi
      shift ;;
  esac
done

# Validate
if [[ -z "$PROMPT" ]]; then echo "ERROR: prompt is required" >&2; usage; exit 1; fi
if ! [[ "$DURATION" =~ ^(4|5|6|8|10|12|15)$ ]]; then
  echo "ERROR: --duration must be one of 4,5,6,8,10,12,15 (got: $DURATION)" >&2; exit 1
fi
case "$RESOLUTION" in 480p|720p|1080p|4k) ;; *) echo "ERROR: --resolution must be 480p|720p|1080p|4k" >&2; exit 1 ;; esac
case "$ASPECT" in 16:9|9:16|1:1|4:3|3:4|21:9|adaptive) ;; *) echo "ERROR: invalid --aspect" >&2; exit 1 ;; esac
if [[ ${#REF_IMAGES[@]} -gt 9 ]]; then echo "ERROR: max 9 --ref-image entries" >&2; exit 1; fi
if [[ ${#REF_VIDEOS[@]} -gt 3 ]]; then echo "ERROR: max 3 --ref-video entries" >&2; exit 1; fi
if [[ ${#REF_AUDIOS[@]} -gt 3 ]]; then echo "ERROR: max 3 --ref-audio entries" >&2; exit 1; fi
if [[ -n "$BITRATE_MODE" ]]; then
  case "$BITRATE_MODE" in standard|high) ;; *) echo "ERROR: --bitrate must be standard|high" >&2; exit 1 ;; esac
fi
if [[ ${#REF_AUDIOS[@]} -gt 0 && -z "$FIRST_FRAME" && ${#REF_IMAGES[@]} -eq 0 && ${#REF_VIDEOS[@]} -eq 0 ]]; then
  echo "ERROR: --ref-audio cannot be used with text+audio only — add --first-frame, --ref-image, or --ref-video (per Segmind)" >&2; exit 1
fi
# Reference assets MUST be hosted HTTP(S) URLs. The upstream (ByteDance ark) rejects
# data URIs for reference_* fields with InvalidParameter.URL — local files cannot be
# inlined the way --first-frame allows. Host first (e.g. HeyGen asset upload, GHL media).
for ref in ${REF_IMAGES[@]+"${REF_IMAGES[@]}"} ${REF_VIDEOS[@]+"${REF_VIDEOS[@]}"} ${REF_AUDIOS[@]+"${REF_AUDIOS[@]}"}; do
  if ! [[ "$ref" =~ ^https?:// ]]; then
    echo "ERROR: reference assets must be public HTTP(S) URLs (got: $ref). Upstream rejects data URIs/local files for reference fields — upload the file somewhere public first." >&2
    exit 1
  fi
done
if [[ -n "$LAST_FRAME" && -z "$FIRST_FRAME" ]]; then echo "ERROR: --last-frame requires --first-frame" >&2; exit 1; fi
if [[ -n "$FIRST_FRAME" && ${#REF_IMAGES[@]} -gt 0 ]]; then
  echo "ERROR: --first-frame and --ref-image are mutually exclusive (per Segmind)" >&2; exit 1
fi
if ! command -v jq >/dev/null; then echo "ERROR: jq required (brew install jq)" >&2; exit 1; fi
if ! $DRY_RUN && [[ -z "$API_KEY" ]]; then
  echo "ERROR: SEGMIND_API_KEY not set. export it in ~/.zshrc or pass --api-key" >&2; exit 1
fi

# Convert local file path to data URI (base64); pass URLs through unchanged.
to_uri() {
  local input="$1"
  if [[ "$input" =~ ^https?:// || "$input" =~ ^data: ]]; then
    printf '%s' "$input"
  else
    if [[ ! -f "$input" ]]; then echo "ERROR: file not found: $input" >&2; exit 1; fi
    local mime ext
    ext=$(printf '%s' "${input##*.}" | tr '[:upper:]' '[:lower:]')
    case "$ext" in
      jpg|jpeg) mime="image/jpeg" ;;
      png) mime="image/png" ;;
      webp) mime="image/webp" ;;
      gif) mime="image/gif" ;;
      mp4) mime="video/mp4" ;;
      mov) mime="video/quicktime" ;;
      webm) mime="video/webm" ;;
      mp3) mime="audio/mpeg" ;;
      wav) mime="audio/wav" ;;
      m4a) mime="audio/mp4" ;;
      *) mime="application/octet-stream" ;;
    esac
    # `base64 < file` is portable across BSD (macOS) and GNU coreutils; `-i` is BSD-only.
    printf 'data:%s;base64,%s' "$mime" "$(base64 < "$input" | tr -d '\n')"
  fi
}

# Build JSON
PAYLOAD=$(jq -n \
  --arg prompt "$PROMPT" \
  --arg aspect "$ASPECT" \
  --arg resolution "$RESOLUTION" \
  --argjson duration "$DURATION" \
  --argjson seed "$SEED" \
  --argjson audio "$AUDIO" \
  --argjson return_last_frame "$RETURN_LAST_FRAME" \
  --argjson skip_moderation "$SKIP_MODERATION" \
  '{
    prompt: $prompt,
    aspect_ratio: $aspect,
    resolution: $resolution,
    duration: $duration,
    seed: $seed,
    generate_audio: $audio,
    return_last_frame: $return_last_frame,
    skip_moderation: $skip_moderation
  }')

# Base64 data URIs can exceed ARG_MAX (~1MB on macOS). Pass them to jq via --rawfile
# (reads from a file), NOT --arg "$(...)", which puts the whole string on the command line
# and fails with "Argument list too long" for any multi-MB image.
if [[ -n "$FIRST_FRAME" ]]; then
  _ff=$(mktemp); to_uri "$FIRST_FRAME" > "$_ff"
  PAYLOAD=$(printf '%s' "$PAYLOAD" | jq --rawfile v "$_ff" '. + {first_frame_url: $v}')
  rm -f "$_ff"
fi
if [[ -n "$LAST_FRAME" ]]; then
  _lf=$(mktemp); to_uri "$LAST_FRAME" > "$_lf"
  PAYLOAD=$(printf '%s' "$PAYLOAD" | jq --rawfile v "$_lf" '. + {last_frame_url: $v}')
  rm -f "$_lf"
fi
# Reference assets are validated as URLs above — no base64 conversion needed.
if [[ ${#REF_IMAGES[@]} -gt 0 ]]; then
  REF_JSON=$(printf '%s\n' "${REF_IMAGES[@]}" | jq -R . | jq -s .)
  PAYLOAD=$(printf '%s' "$PAYLOAD" | jq --argjson refs "$REF_JSON" '. + {reference_images: $refs}')
fi
if [[ ${#REF_VIDEOS[@]} -gt 0 ]]; then
  REF_JSON=$(printf '%s\n' "${REF_VIDEOS[@]}" | jq -R . | jq -s .)
  PAYLOAD=$(printf '%s' "$PAYLOAD" | jq --argjson refs "$REF_JSON" '. + {reference_videos: $refs}')
fi
if [[ ${#REF_AUDIOS[@]} -gt 0 ]]; then
  REF_JSON=$(printf '%s\n' "${REF_AUDIOS[@]}" | jq -R . | jq -s .)
  PAYLOAD=$(printf '%s' "$PAYLOAD" | jq --argjson refs "$REF_JSON" '. + {reference_audios: $refs}')
fi
if [[ -n "$BITRATE_MODE" ]]; then
  PAYLOAD=$(printf '%s' "$PAYLOAD" | jq --arg v "$BITRATE_MODE" '. + {bitrate_mode: $v}')
fi

# Cost estimate (per-second, text-to-video tier)
estimate_cost() {
  local rate=0
  if [[ "$RESOLUTION" == "480p" ]]; then
    case "$ASPECT" in
      1:1) rate=0.0672 ;;
      4:3|3:4) rate=0.0691 ;;
      *) rate=0.0703 ;;
    esac
  elif [[ "$RESOLUTION" == "720p" ]]; then
    case "$ASPECT" in
      4:3|3:4) rate=0.1522 ;;
      21:9) rate=0.1519 ;;
      *) rate=0.1512 ;;
    esac
  elif [[ "$RESOLUTION" == "1080p" ]]; then
    rate=0.30  # 1080p estimate (not on public pricing page; ~2x 720p)
  else
    rate=0.60  # 4k estimate (not on public pricing page; ~2x 1080p)
  fi
  # Reference videos switch billing to the video-to-video token rate (~39% cheaper)
  if [[ ${#REF_VIDEOS[@]} -gt 0 ]]; then
    rate=$(awk -v r="$rate" 'BEGIN { printf "%.4f", r * 0.61 }')
  fi
  awk -v r="$rate" -v d="$DURATION" 'BEGIN { printf "%.4f", r * d }'
}
COST=$(estimate_cost)

# Output paths — TS includes seconds + PID so back-to-back calls within the same second don't collide.
TS=$(date +%Y%m%d-%H%M%S)-$$
NAME="${OUTPUT_NAME:-seedance-$TS}"
OUT_FILE="$OUT_DIR/$NAME.mp4"

if $DRY_RUN; then
  echo "DRY RUN — would POST to $API_URL"
  echo "Estimated cost: \$$COST (text-to-video, $DURATION s @ $RESOLUTION $ASPECT)"
  echo "Output would be: $OUT_FILE"
  echo "Payload (truncated long fields):"
  echo "$PAYLOAD" | jq 'with_entries(if (.value | type == "string" and (. | length > 200)) then .value = (.value[0:80] + "...<truncated>") else . end)'
  exit 0
fi

# Only create the output dir for real calls — dry runs must be side-effect free.
mkdir -p "$OUT_DIR"

echo "→ Generating ($DURATION s @ $RESOLUTION $ASPECT, est. \$$COST)..."
echo "→ Saving to $OUT_FILE"

TMP_BODY=$(mktemp)
TMP_HEAD=$(mktemp)
TMP_PAYLOAD=$(mktemp)
trap 'rm -f "$TMP_BODY" "$TMP_HEAD" "$TMP_PAYLOAD"' EXIT

# Write the payload to a file and POST with --data @file. Passing a multi-MB base64 payload
# via --data "$PAYLOAD" puts it on the command line and trips ARG_MAX.
printf '%s' "$PAYLOAD" > "$TMP_PAYLOAD"

# Async path: submit to v2, poll status, download result. Survives renders >60s that
# the v1 sync gateway would cut ("Empty reply from server").
if $ASYNC; then
  SUBMIT=$(curl -sS -X POST "$API_URL_ASYNC" \
    -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
    --data @"$TMP_PAYLOAD")
  REQ_ID=$(printf '%s' "$SUBMIT" | jq -r '.request_id // empty')
  if [[ -z "$REQ_ID" ]]; then
    echo "ERROR: async submit failed:" >&2
    printf '%s\n' "$SUBMIT" | head -c 2000 >&2
    exit 1
  fi
  STATUS_URL="https://api.segmind.com/v2/requests/$REQ_ID/status"
  RESULT_URL="https://api.segmind.com/v2/requests/$REQ_ID"
  echo "→ Submitted async (request_id: $REQ_ID). Polling every 20s..."
  for _i in $(seq 1 60); do
    sleep 20
    STATUS=$(curl -s -H "x-api-key: $API_KEY" "$STATUS_URL" | jq -r '.status // empty')
    echo "  [poll $_i] ${STATUS:-no-response}"
    if [[ "$STATUS" == "COMPLETED" ]]; then
      RESULT=$(curl -s -H "x-api-key: $API_KEY" "$RESULT_URL")
      if printf '%s' "$RESULT" | jq -e . >/dev/null 2>&1; then
        # NOTE: .video is an OBJECT ({url, file_name, ...}), not a string — the flat
        # string URL lives at .output (verified 2026-07-27). Guard that the extraction
        # produced an actual URL, not a JSON object.
        URL=$(printf '%s' "$RESULT" | jq -r '.output // .video.url // .video_url // .url // empty')
        if ! [[ "$URL" =~ ^https?:// ]]; then
          echo "ERROR: COMPLETED but no usable video URL in result:" >&2
          printf '%s\n' "$RESULT" | head -c 2000 >&2
          exit 1
        fi
        curl -sS -L --max-time 600 -o "$OUT_FILE" "$URL"
        ACTUAL_COST=$(printf '%s' "$RESULT" | jq -r '.metrics.cost // empty')
        REMAINING=$(printf '%s' "$RESULT" | jq -r '.metrics.remaining_credits // empty')
      else
        # Non-JSON result — assume binary video
        curl -s -H "x-api-key: $API_KEY" -o "$OUT_FILE" "$RESULT_URL"
        ACTUAL_COST=""; REMAINING=""
      fi
      SIZE=$(du -h "$OUT_FILE" | cut -f1)
      echo "✓ Done. $OUT_FILE ($SIZE)"
      echo "  Cost: \$${ACTUAL_COST:-$COST (estimate)}${REMAINING:+ — remaining credits: $REMAINING}"
      exit 0
    elif [[ "$STATUS" == "FAILED" ]]; then
      echo "ERROR: generation FAILED:" >&2
      curl -s -H "x-api-key: $API_KEY" "$RESULT_URL" | head -c 2000 >&2
      echo >&2
      exit 1
    fi
  done
  echo "ERROR: polling timed out after 20 min. Results are kept 1h — re-poll: $RESULT_URL (request_id: $REQ_ID)" >&2
  exit 1
fi

HTTP_CODE=$(curl -sS -o "$TMP_BODY" -D "$TMP_HEAD" -w "%{http_code}" \
  --http1.1 \
  --max-time 600 \
  -X POST "$API_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  --data @"$TMP_PAYLOAD" || echo "000")

# Tolerate missing Content-Type header: pipefail + set -e would otherwise abort and the trap
# would delete the (already-paid-for) response body. Empty string falls through to the
# "Unknown content type — assume binary" branch below.
CONTENT_TYPE=$( { grep -i '^content-type:' "$TMP_HEAD" || true; } | tail -1 | tr -d '\r' | awk '{print tolower($2)}')

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "ERROR: HTTP $HTTP_CODE" >&2
  if [[ "$HTTP_CODE" == "000" ]]; then
    echo "HINT: connection dropped — the v1 sync gateway cuts at ~60s. Re-run with --async." >&2
  fi
  if [[ "$CONTENT_TYPE" == application/json* ]]; then
    jq . "$TMP_BODY" >&2 || cat "$TMP_BODY" >&2
  else
    head -c 2000 "$TMP_BODY" >&2; echo >&2
  fi
  exit 1
fi

# Success path: video binary OR JSON with a URL field
if [[ "$CONTENT_TYPE" == video/* || "$CONTENT_TYPE" == application/octet-stream* ]]; then
  mv "$TMP_BODY" "$OUT_FILE"
elif [[ "$CONTENT_TYPE" == application/json* ]]; then
  URL=$(jq -r '.video // .video_url // .output // .url // empty' "$TMP_BODY")
  if [[ -z "$URL" ]]; then
    echo "ERROR: 200 OK but no video field in JSON response:" >&2
    jq . "$TMP_BODY" >&2
    exit 1
  fi
  echo "→ Downloading $URL"
  curl -sS -L --max-time 600 -o "$OUT_FILE" "$URL"
else
  # Unknown content type — assume binary
  mv "$TMP_BODY" "$OUT_FILE"
fi

SIZE=$(du -h "$OUT_FILE" | cut -f1)
echo "✓ Done. $OUT_FILE ($SIZE)"
echo "  Estimated cost: \$$COST"
