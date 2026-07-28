#!/usr/bin/env bash
# dub-video - dub a video/audio file into another language via ElevenLabs Dubbing v1 API
# Flow: POST /v1/dubbing (upload) -> poll GET /v1/dubbing/{id} -> GET /v1/dubbing/{id}/audio/{lang}
set -euo pipefail

API_BASE="https://api.elevenlabs.io/v1/dubbing"
OUT_DIR_DEFAULT="$HOME/Downloads/dubs"

usage() {
  cat <<'EOF'
dub-video - Translate the voice in a video/audio file into another language (ElevenLabs Dubbing v1)

USAGE:
  dub.sh INPUT [OPTIONS]

INPUT:
  A local file path (video or audio) OR a URL (YouTube, X, TikTok, Vimeo, direct link).

OPTIONS:
  -t, --target LANG        Target language code (default: es).  e.g. es, en, fr, de, pt, it, hi, ja
  -s, --source LANG        Source language code (default: auto-detect)
  -n, --num-speakers N     Number of speakers, 0 = auto-detect (default: 0)
      --watermark          Add ElevenLabs watermark (cheaper tier). Default: no watermark.
      --drop-background     Drop/mute the original background audio track
      --no-voice-clone      Disable speaker voice cloning (use a stock voice)
      --highest-resolution  Render output at the highest available resolution
      --start-time SEC      Only dub from this timestamp (seconds)
      --end-time SEC        Only dub up to this timestamp (seconds)
  -o, --output NAME        Output filename without extension (default: dub-<lang>-<ts>)
      --dir DIR            Output directory (default: ~/Downloads/dubs)
      --api-key KEY        Override ELEVENLABS_API_KEY env var
      --poll-interval SEC  Seconds between status polls (default: 10)
      --timeout SEC        Max seconds to wait for the dub (default: 1800 = 30 min)
      --dry-run            Print the request plan and exit (no API call)
  -h, --help               Show this help

ENV:
  ELEVENLABS_API_KEY   Required. Get one at https://elevenlabs.io/app/settings/api-keys

EXAMPLES:
  dub.sh ./promo.mp4                              # English -> Spanish (default)
  dub.sh ./promo.mp4 -t pt -o promo-portuguese    # -> Portuguese, custom name
  dub.sh ./interview.mp4 -t es -n 2               # two speakers, -> Spanish
  dub.sh "https://youtu.be/XXXX" -t es            # dub straight from a URL
  dub.sh ./clip.mp4 -t es --start-time 5 --end-time 35   # only dub 5s..35s
EOF
}

if [[ $# -eq 0 ]]; then usage; exit 1; fi

# Validate that a value-flag actually has a non-flag value following it.
require_val() {
  local flag="$1" val="${2:-}"
  if [[ -z "$val" || "$val" == -* ]]; then
    echo "ERROR: $flag requires a value" >&2; exit 1
  fi
}

INPUT=""
TARGET="es"
SOURCE="auto"
NUM_SPEAKERS=0
WATERMARK=false
DROP_BG=false
NO_VOICE_CLONE=false
HIGHEST_RES=false
START_TIME=""
END_TIME=""
OUTPUT_NAME=""
OUT_DIR="$OUT_DIR_DEFAULT"
API_KEY="${ELEVENLABS_API_KEY:-}"
POLL_INTERVAL=10
TIMEOUT=1800
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -t|--target) require_val "$1" "${2:-}"; TARGET="$2"; shift 2 ;;
    -s|--source) require_val "$1" "${2:-}"; SOURCE="$2"; shift 2 ;;
    -n|--num-speakers)
      if [[ -z "${2:-}" ]]; then echo "ERROR: --num-speakers requires a value" >&2; exit 1; fi
      if ! [[ "$2" =~ ^[0-9]+$ ]]; then echo "ERROR: --num-speakers must be a non-negative integer" >&2; exit 1; fi
      NUM_SPEAKERS="$2"; shift 2 ;;
    --watermark) WATERMARK=true; shift ;;
    --drop-background) DROP_BG=true; shift ;;
    --no-voice-clone) NO_VOICE_CLONE=true; shift ;;
    --highest-resolution) HIGHEST_RES=true; shift ;;
    --start-time) require_val "$1" "${2:-}"; START_TIME="$2"; shift 2 ;;
    --end-time) require_val "$1" "${2:-}"; END_TIME="$2"; shift 2 ;;
    -o|--output) require_val "$1" "${2:-}"; OUTPUT_NAME="$2"; shift 2 ;;
    --dir) require_val "$1" "${2:-}"; OUT_DIR="$2"; shift 2 ;;
    --api-key) require_val "$1" "${2:-}"; API_KEY="$2"; shift 2 ;;
    --poll-interval) require_val "$1" "${2:-}"; POLL_INTERVAL="$2"; shift 2 ;;
    --timeout) require_val "$1" "${2:-}"; TIMEOUT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --)
      shift
      if [[ -z "$INPUT" && $# -gt 0 ]]; then INPUT="$1"; shift; fi
      if [[ $# -gt 0 ]]; then echo "Unexpected arg after --: $1" >&2; exit 1; fi
      ;;
    -*) echo "Unknown flag: $1" >&2; usage; exit 1 ;;
    *)
      if [[ -z "$INPUT" ]]; then INPUT="$1"
      else echo "Unexpected arg: $1 (input already set)" >&2; exit 1
      fi
      shift ;;
  esac
done

# ---- Validate -------------------------------------------------------------
if [[ -z "$INPUT" ]]; then echo "ERROR: input file or URL is required" >&2; usage; exit 1; fi
if ! command -v jq   >/dev/null; then echo "ERROR: jq required (brew install jq)" >&2; exit 1; fi
if ! command -v curl >/dev/null; then echo "ERROR: curl required" >&2; exit 1; fi

IS_URL=false
if [[ "$INPUT" =~ ^https?:// ]]; then
  IS_URL=true
else
  if [[ ! -f "$INPUT" ]]; then echo "ERROR: file not found: $INPUT" >&2; exit 1; fi
fi

if ! $DRY_RUN && [[ -z "$API_KEY" ]]; then
  echo "ERROR: ELEVENLABS_API_KEY not set. export it in ~/.zshrc or pass --api-key" >&2
  echo "       Get a key: https://elevenlabs.io/app/settings/api-keys" >&2
  exit 1
fi

# ---- Output paths ---------------------------------------------------------
# TS includes seconds + PID so back-to-back calls within the same second don't collide.
TS=$(date +%Y%m%d-%H%M%S)-$$
NAME="${OUTPUT_NAME:-dub-$TARGET-$TS}"

# Guess the output extension: dubbing returns MP4 for video input, MP3 for audio input.
guess_ext() {
  if $IS_URL; then echo "mp4"; return; fi
  local ext; ext=$(printf '%s' "${INPUT##*.}" | tr '[:upper:]' '[:lower:]')
  case "$ext" in
    mp3|wav|m4a|flac|aac|ogg|opus) echo "mp3" ;;
    *) echo "mp4" ;;
  esac
}
OUT_EXT=$(guess_ext)
OUT_FILE="$OUT_DIR/$NAME.$OUT_EXT"

# ---- Cost estimate (best-effort; needs ffprobe for local files) -----------
# Dubbing is billed per SOURCE minute: ~$0.33/min watermarked, ~$0.50/min without.
RATE=0.50; $WATERMARK && RATE=0.33
COST_NOTE="~\$$RATE/source-minute"
if ! $IS_URL && command -v ffprobe >/dev/null; then
  DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$INPUT" 2>/dev/null || echo "")
  if [[ -n "$DUR" ]]; then
    COST=$(awk -v r="$RATE" -v d="$DUR" 'BEGIN { printf "%.2f", r * (d/60) }')
    COST_NOTE="est. \$$COST ($(awk -v d="$DUR" 'BEGIN{printf "%.1f", d/60}') min @ \$$RATE/min)"
  fi
fi

# Map a local media file to an explicit MIME type. macOS curl lacks a mime.types
# DB and defaults everything to application/octet-stream, which ElevenLabs rejects.
mime_for() {
  local ext; ext=$(printf '%s' "${1##*.}" | tr '[:upper:]' '[:lower:]')
  case "$ext" in
    mp4)  echo "video/mp4" ;;
    mov)  echo "video/quicktime" ;;
    m4v)  echo "video/x-m4v" ;;
    webm) echo "video/webm" ;;
    mkv)  echo "video/x-matroska" ;;
    avi)  echo "video/x-msvideo" ;;
    mp3)  echo "audio/mpeg" ;;
    wav)  echo "audio/wav" ;;
    m4a)  echo "audio/mp4" ;;
    flac) echo "audio/flac" ;;
    aac)  echo "audio/aac" ;;
    ogg)  echo "audio/ogg" ;;
    opus) echo "audio/opus" ;;
    *)    echo "video/mp4" ;;  # sensible default; octet-stream is rejected
  esac
}

# ---- Build the multipart form fields --------------------------------------
FORM=(-F "target_lang=$TARGET" -F "source_lang=$SOURCE" -F "num_speakers=$NUM_SPEAKERS")
$WATERMARK       && FORM+=(-F "watermark=true")             || FORM+=(-F "watermark=false")
$DROP_BG         && FORM+=(-F "drop_background_audio=true")
$NO_VOICE_CLONE  && FORM+=(-F "disable_voice_cloning=true")
$HIGHEST_RES     && FORM+=(-F "highest_resolution=true")
[[ -n "$START_TIME" ]] && FORM+=(-F "start_time=$START_TIME")
[[ -n "$END_TIME"   ]] && FORM+=(-F "end_time=$END_TIME")
if $IS_URL; then FORM+=(-F "source_url=$INPUT"); else FORM+=(-F "file=@$INPUT;type=$(mime_for "$INPUT")"); fi

if $DRY_RUN; then
  echo "DRY RUN — would POST to $API_BASE"
  echo "  input:        $INPUT ($([[ $IS_URL == true ]] && echo URL || echo file))"
  echo "  source_lang:  $SOURCE"
  echo "  target_lang:  $TARGET"
  echo "  num_speakers: $NUM_SPEAKERS (0=auto)"
  echo "  watermark:    $WATERMARK   drop_bg: $DROP_BG   no_voice_clone: $NO_VOICE_CLONE   highest_res: $HIGHEST_RES"
  [[ -n "$START_TIME$END_TIME" ]] && echo "  time range:   ${START_TIME:-0}s .. ${END_TIME:-end}s"
  echo "  output:       $OUT_FILE"
  echo "  cost:         $COST_NOTE"
  exit 0
fi

mkdir -p "$OUT_DIR"

TMP_BODY=$(mktemp); TMP_HEAD=$(mktemp)
trap 'rm -f "$TMP_BODY" "$TMP_HEAD"' EXIT

# ---- 1) Create the dubbing job -------------------------------------------
echo "→ Uploading & starting dub ($SOURCE → $TARGET, $COST_NOTE)..."
HTTP_CODE=$(curl -sS -o "$TMP_BODY" -w "%{http_code}" \
  --max-time 1800 \
  -X POST "$API_BASE" \
  -H "xi-api-key: $API_KEY" \
  "${FORM[@]}" || echo "000")

if [[ "$HTTP_CODE" != "200" && "$HTTP_CODE" != "201" ]]; then
  echo "ERROR: create dub failed — HTTP $HTTP_CODE" >&2
  jq . "$TMP_BODY" 2>/dev/null >&2 || head -c 2000 "$TMP_BODY" >&2; echo >&2
  exit 1
fi

DUB_ID=$(jq -r '.dubbing_id // empty' "$TMP_BODY")
if [[ -z "$DUB_ID" ]]; then
  echo "ERROR: no dubbing_id in response:" >&2; jq . "$TMP_BODY" >&2; exit 1
fi
EXP=$(jq -r '.expected_duration_sec // empty' "$TMP_BODY")
echo "→ Job created: $DUB_ID${EXP:+ (expected ~${EXP}s to process)}"

# ---- 2) Poll until dubbed / failed ---------------------------------------
ELAPSED=0
while :; do
  STATUS_JSON=$(curl -sS --max-time 60 -H "xi-api-key: $API_KEY" "$API_BASE/$DUB_ID" || echo '{}')
  STATUS=$(echo "$STATUS_JSON" | jq -r '.status // "unknown"')
  case "$STATUS" in
    dubbed) echo "→ Dub ready."; break ;;
    failed)
      echo "ERROR: dubbing failed." >&2
      echo "$STATUS_JSON" | jq -r '.error // "(no error message)"' >&2
      exit 1 ;;
    *)
      if [[ "$ELAPSED" -ge "$TIMEOUT" ]]; then
        echo "ERROR: timed out after ${TIMEOUT}s (last status: $STATUS). Job id: $DUB_ID" >&2
        exit 1
      fi
      printf '  … %s (%ds elapsed)\r' "$STATUS" "$ELAPSED"
      sleep "$POLL_INTERVAL"
      ELAPSED=$((ELAPSED + POLL_INTERVAL))
      ;;
  esac
done

# ---- 3) Download the dubbed media ----------------------------------------
echo "→ Downloading dubbed $TARGET track → $OUT_FILE"
DL_CODE=$(curl -sS -o "$TMP_BODY" -D "$TMP_HEAD" -w "%{http_code}" \
  --max-time 1800 \
  -H "xi-api-key: $API_KEY" \
  "$API_BASE/$DUB_ID/audio/$TARGET" || echo "000")

if [[ "$DL_CODE" != "200" ]]; then
  echo "ERROR: download failed — HTTP $DL_CODE" >&2
  jq . "$TMP_BODY" 2>/dev/null >&2 || head -c 2000 "$TMP_BODY" >&2; echo >&2
  exit 1
fi

# Correct the extension from the actual Content-Type if it disagrees with our guess.
CT=$( { grep -i '^content-type:' "$TMP_HEAD" || true; } | tail -1 | tr -d '\r' | awk '{print tolower($2)}')
case "$CT" in
  audio/mpeg|audio/mp3) [[ "$OUT_EXT" != "mp3" ]] && OUT_FILE="$OUT_DIR/$NAME.mp3" ;;
  video/mp4)            [[ "$OUT_EXT" != "mp4" ]] && OUT_FILE="$OUT_DIR/$NAME.mp4" ;;
esac
mv "$TMP_BODY" "$OUT_FILE"

SIZE=$(du -h "$OUT_FILE" | cut -f1)
echo "✓ Done. $OUT_FILE ($SIZE)"
echo "  $COST_NOTE  ·  dub id: $DUB_ID"
