---
name: seedance
description: Generates videos via Segmind Seedance 2.0 (ByteDance). Text-to-video and image-to-video with native synced audio, multi-shot prompts, 4-15s duration, 480p/720p/1080p, aspect ratios 16:9/9:16/1:1/4:3/3:4/21:9/adaptive, first/last-frame conditioning for clip chaining, up to 9 reference images for character/style consistency. Use when asked to "generate a video", "make a clip", "create b-roll", "animate this image", "make a 5 second video of X", or any AI video generation task.
---

Generate videos via the Segmind Seedance 2.0 API. Invoke `generate.sh` — do not hand-write the curl chain.

**Companion skill:** for turning a creative brief into a shot-by-shot prompt, use `seedance-video-prompt-builder` first, then feed its output to this skill via `--`:

```bash
~/.claude/skills/seedance/generate.sh --duration 15 --audio -- "$(cat shot-list.txt)"
```

## When to invoke

- User asks for a video, clip, b-roll, animation, or "make this image come alive"
- Need a short cinematic shot (4-15s) with optional native synced audio
- Multi-shot sequences (`Shot 1: ... Shot 2: ...` in the prompt)
- Animate a still image (image-to-video via `--first-frame`)
- Chain clips by reusing one clip's last frame as the next clip's first frame

Skip for: long-form video (>15s — chain clips instead), 3D scenes, talking-head lipsync (use a different model), or when the user needs editing rather than generation.

## /init - First-time setup

When the user says "init seedance", "setup seedance", or "add my segmind key":

1. Get an API key at https://www.segmind.com/ (account → API keys)
2. Persist it in shell rc:
   ```bash
   echo 'export SEGMIND_API_KEY="<paste-key>"' >> ~/.zshrc
   source ~/.zshrc
   ```
3. Verify `jq` is installed: `command -v jq || brew install jq`
4. Smoke test: `~/.claude/skills/seedance/generate.sh "test" --dry-run`

## Invocation

```bash
~/.claude/skills/seedance/generate.sh "PROMPT" [OPTIONS]
```

**Default output:** `~/Downloads/seedance/seedance-<timestamp>.mp4`

## Options

| Flag                  | Default                | Description                                                        |
| --------------------- | ---------------------- | ------------------------------------------------------------------ |
| `-d, --duration N`    | `5`                    | Seconds: 4, 5, 6, 8, 10, 12, 15                                    |
| `-r, --resolution X`  | `720p`                 | `480p`, `720p`, `1080p`                                            |
| `-a, --aspect X`      | `16:9`                 | `16:9`, `9:16`, `1:1`, `4:3`, `3:4`, `21:9`, `adaptive`            |
| `--audio`             | off                    | Co-generate synced audio (dialogue, SFX, ambient, music) — free    |
| `--seed N`            | `-1` (random)          | Reproducibility                                                    |
| `--first-frame X`     | —                      | i2v starting frame (URL or local path; auto-base64)                |
| `--last-frame X`      | —                      | Ending frame; requires `--first-frame`                             |
| `--ref-image X`       | —                      | Reference image for character/style (repeatable, ≤9; URL or local) |
| `--return-last-frame` | off                    | Also return final frame URL (for clip chaining)                    |
| `--skip-moderation`   | off                    | Bypass moderation pre-filter                                       |
| `-o, --output NAME`   | `seedance-<ts>`        | Filename without extension                                         |
| `--dir DIR`           | `~/Downloads/seedance` | Output directory                                                   |
| `--api-key KEY`       | `$SEGMIND_API_KEY`     | Override env                                                       |
| `--dry-run`           | —                      | Print request JSON and exit (no API call)                          |

**Mutual exclusion:** `--first-frame` and `--ref-image` cannot be combined (Segmind constraint).

**Real human faces are blocked in `--first-frame`** per ByteDance policy.

## Pricing (text-to-video, per second)

Audio is free at every tier. Video-to-video is ~39% cheaper than text-to-video.

| Resolution | 16:9 / 9:16 / 21:9  | 1:1       | 4:3 / 3:4 |
| ---------- | ------------------- | --------- | --------- |
| 480p       | $0.0703/s           | $0.0672/s | $0.0691/s |
| 720p       | $0.1512/s           | $0.1512/s | $0.1522/s |
| 1080p      | ~$0.30/s (estimate) | —         | —         |

**Quick reference:**

- 5s @ 720p 16:9 → ~$0.76
- 10s @ 720p 16:9 → ~$1.51
- 5s @ 480p 16:9 → ~$0.35

The script prints an estimated cost before and after the call.

## Workflows

### Basic text-to-video

```bash
~/.claude/skills/seedance/generate.sh "cinematic drone shot over a misty mountain range at sunrise"
```

### Multi-shot sequence (single clip)

```bash
~/.claude/skills/seedance/generate.sh \
  "Shot 1: wide establishing shot of a cyberpunk alley, rain. Shot 2: close-up on neon sign flickering. Shot 3: figure walks past camera." \
  -d 10 -r 720p
```

### Native synced audio

```bash
~/.claude/skills/seedance/generate.sh \
  "a thunderstorm rolling over a coastline at dusk, waves crashing" \
  -d 8 --audio
```

### Image-to-video (animate a still)

```bash
~/.claude/skills/seedance/generate.sh \
  "the wind picks up, leaves swirl, camera slowly pushes in" \
  --first-frame ./hero.jpg -d 6
```

### Character/style consistency via reference images

```bash
~/.claude/skills/seedance/generate.sh \
  "the same character walks through a forest, then sits by a stream" \
  --ref-image ./char-front.png --ref-image ./char-side.png \
  -d 10 -r 720p
```

### Clip chaining (15s+ via last-frame handoff)

The script currently saves only the video file — it does **not** extract the `last_frame_url` from the API response. Two practical options:

```bash
# Option 1 — extract the final frame yourself with ffmpeg after generation
~/.claude/skills/seedance/generate.sh "scene A" -d 8 -o clip-a
ffmpeg -sseof -0.1 -i ~/Downloads/seedance/clip-a.mp4 -vframes 1 last-a.png

# Option 2 — call the API directly with curl + `return_last_frame: true` and parse the JSON
# response, then download the `last_frame_url` field

# Clip B: continue from where A ended
~/.claude/skills/seedance/generate.sh "scene B continues" --first-frame ./last-a.png -d 8 -o clip-b

# Concatenate with ffmpeg or the optimize-video skill
```

### Cinematic widescreen

```bash
~/.claude/skills/seedance/generate.sh "anime chase scene through neon city" -a 21:9 -d 8 --seed 42
```

### Vertical (TikTok/Reels)

```bash
~/.claude/skills/seedance/generate.sh "vertical product showcase: rotating sneaker on pedestal" -a 9:16 -d 6
```

## API key resolution

1. `--api-key` flag
2. `SEGMIND_API_KEY` env var (set in `~/.zshrc`)

Get a key: https://www.segmind.com/

## Constraints (Segmind-enforced)

- `first_frame_url` and `reference_images` are mutually exclusive
- Real human faces blocked in `first_frame_url` (ByteDance policy)
- Up to 9 reference images, 3 reference videos, 3 reference audios per generation
- Max duration: 15 seconds per clip

## API endpoint

```
POST https://api.segmind.com/v1/seedance-2.0
Header: x-api-key: $SEGMIND_API_KEY
```

Returns binary video (sync). On error: JSON error payload with status code (400/401/403/406 insufficient credits/429 rate-limited/500/502/504).
