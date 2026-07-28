---
name: dub-video
description: Dubs the voice in a video or audio file into another language via the ElevenLabs Dubbing v1 API (English→Spanish by default, 90+ languages). Preserves each speaker's tone and pace; multi-speaker aware. Accepts a local file or a URL (YouTube, X, TikTok, Vimeo, direct link). Use when asked to "dub this video", "translate the voice/audio to Spanish", "make a Spanish version of this video", "localize this clip", or "revoice this in <language>". NOT for lip-sync (ElevenLabs replaces audio only — mouths won't re-sync).
---

Dub a video/audio file into another language via ElevenLabs Dubbing v1. Invoke `dub.sh` — do not hand-write the curl chain. The script handles the full async flow: upload → poll job status → download the dubbed media.

## When to invoke

- "Dub this video into Spanish", "translate the voice to <language>", "make a Spanish version"
- Localize a talking-head / voiceover / interview clip into another language
- Dub straight from a URL (YouTube, X, TikTok, Vimeo, direct link) — no download step needed

**Skip / caveat:**

- **No lip-sync.** ElevenLabs swaps the audio for a translated voice that keeps the speaker's tone, but it does **not** move their lips. Fine for voiceover, b-roll, narration; for a tight talking-head where mouth-match matters, use a lip-sync engine (Sieve / HeyGen / Rask) instead.
- For subtitles-only (no revoice), this is the wrong tool.

## Invocation

```bash
~/.claude/skills/dub-video/dub.sh INPUT [OPTIONS]
```

**INPUT** = a local file path (video or audio) OR a URL.
**Default:** auto-detect source language → **Spanish (`es`)**, no watermark, voice cloning on.
**Default output:** `~/Downloads/dubs/dub-<lang>-<timestamp>.mp4` (`.mp3` for audio input).

### ⚠️ Long jobs — run in the background

Dubbing is async and can take minutes. The script polls internally with `sleep`, so a real run will exceed the Bash tool's foreground limit. When YOU (Claude) run a real dub, launch it with `run_in_background: true` and collect the result when it finishes. `--dry-run` and the key check are instant and can run foreground.

## Options

| Flag                   | Default               | Description                                              |
| ---------------------- | --------------------- | -------------------------------------------------------- |
| `-t, --target LANG`    | `es`                  | Target language code (es, en, fr, de, pt, it, hi, ja, …) |
| `-s, --source LANG`    | `auto`                | Source language code (auto-detect by default)            |
| `-n, --num-speakers N` | `0`                   | Number of speakers; `0` = auto-detect                    |
| `--watermark`          | off                   | Add ElevenLabs watermark (cheaper ~$0.33/min tier)       |
| `--drop-background`    | off                   | Mute the original background audio track                 |
| `--no-voice-clone`     | off                   | Use a stock voice instead of cloning the speaker         |
| `--highest-resolution` | off                   | Render output at highest available resolution            |
| `--start-time SEC`     | —                     | Only dub from this timestamp (seconds)                   |
| `--end-time SEC`       | —                     | Only dub up to this timestamp (seconds)                  |
| `-o, --output NAME`    | `dub-<lang>-<ts>`     | Output filename without extension                        |
| `--dir DIR`            | `~/Downloads/dubs`    | Output directory                                         |
| `--api-key KEY`        | `$ELEVENLABS_API_KEY` | Override env                                             |
| `--poll-interval SEC`  | `10`                  | Seconds between status polls                             |
| `--timeout SEC`        | `1800`                | Max wait for the dub (30 min)                            |
| `--dry-run`            | —                     | Print the request plan and exit (no API call, no cost)   |

## /init - First-time setup

When the user says "init dub-video" or "add my elevenlabs key":

1. Get an API key at https://elevenlabs.io/app/settings/api-keys
2. Persist it in shell rc:
   ```bash
   echo 'export ELEVENLABS_API_KEY="<paste-key>"' >> ~/.zshrc
   source ~/.zshrc
   ```
3. Verify `jq` is installed (`ffprobe` optional, only for cost estimates):
   ```bash
   command -v jq || brew install jq
   ```
4. Smoke test (no cost): `~/.claude/skills/dub-video/dub.sh ./anything.mp4 --dry-run`
5. Confirm the key works (free, no dub created):
   ```bash
   curl -s -H "xi-api-key: $ELEVENLABS_API_KEY" \
     https://api.elevenlabs.io/v1/user/subscription | jq '{tier, character_count, character_limit}'
   ```

## Workflows

### Basic English → Spanish

```bash
~/.claude/skills/dub-video/dub.sh ./promo.mp4
```

### Into another language, custom filename

```bash
~/.claude/skills/dub-video/dub.sh ./promo.mp4 -t pt -o promo-portuguese
```

### Multi-speaker interview

```bash
~/.claude/skills/dub-video/dub.sh ./interview.mp4 -t es -n 2
```

### Straight from a URL

```bash
~/.claude/skills/dub-video/dub.sh "https://youtu.be/XXXXXXXX" -t es
```

### Only dub a segment (cheaper)

```bash
~/.claude/skills/dub-video/dub.sh ./clip.mp4 -t es --start-time 5 --end-time 35
```

### Audio-only file

```bash
~/.claude/skills/dub-video/dub.sh ./podcast.mp3 -t es    # -> dub-es-<ts>.mp3
```

## Pricing

Billed **per source minute** (not per output). Each target language is billed separately.

| Mode                                   | Rate                |
| -------------------------------------- | ------------------- |
| Automatic, no watermark (default)      | ~$0.50 / source min |
| Automatic, watermarked (`--watermark`) | ~$0.33 / source min |

The script prints an estimate before uploading when `ffprobe` is installed (local files only).
Max input: up to ~2 GB / 180 min. Verify your plan's included dubbing minutes at https://elevenlabs.io/pricing.

## API key resolution

1. `--api-key` flag
2. `ELEVENLABS_API_KEY` env var (set in `~/.zshrc`)

Get a key: https://elevenlabs.io/app/settings/api-keys

## API flow (what the script does)

```
POST https://api.elevenlabs.io/v1/dubbing            (multipart: file|source_url, target_lang, …)
  → { dubbing_id, expected_duration_sec }
GET  https://api.elevenlabs.io/v1/dubbing/{id}        (poll until status == "dubbed"; "failed" → error)
GET  https://api.elevenlabs.io/v1/dubbing/{id}/audio/{target_lang}   → dubbed MP4/MP3
```

Header on every call: `xi-api-key: $ELEVENLABS_API_KEY`.
Note: dubs edited in Dubbing Studio require the resource-render endpoint instead — this skill only handles automatic dubs.
