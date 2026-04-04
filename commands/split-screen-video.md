Create a polished split-screen video from raw talking-head footage. Top half = B-roll images with annotations, bottom half = zoomed presenter. Includes yellow subtitle bars, enhanced audio, and 1.2x speed.

## Usage
```
/split-screen-video /path/to/raw_video.MOV
```

## Pipeline Overview

Execute these 8 steps in order. This skill is **fully autonomous** — self-verify each step and auto-correct issues without asking the user. Only stop to ask the user if something is fundamentally ambiguous (e.g., which language to transcribe in).

---

## Step 1: Analyze Raw Video

Get video metadata and extract frames to understand the content:

```bash
ffprobe -v quiet -print_format json -show_format -show_streams "$RAW_VIDEO"
```

Extract 8-10 evenly spaced frames using the `/view-video` approach:
```bash
FRAMES_DIR=$(mktemp -d)
DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$RAW_VIDEO")
NUM_FRAMES=8
INTERVAL=$(echo "$DURATION / ($NUM_FRAMES + 1)" | bc -l)
for i in $(seq 1 $NUM_FRAMES); do
  TIMESTAMP=$(echo "$INTERVAL * $i" | bc -l)
  ffmpeg -y -ss "$TIMESTAMP" -i "$RAW_VIDEO" -frames:v 1 -q:v 2 "$FRAMES_DIR/frame_$(printf '%03d' $i).jpg" 2>/dev/null
done
```

View all frames with the Read tool to understand:
- What the presenter is discussing
- The environment/setting
- Any visual elements to reference in B-roll

Report: duration, resolution, fps, codec, and content summary.

**IMPORTANT iPhone notes:**
- iPhone videos have -90° rotation metadata; ffmpeg auto-rotates
- NEVER use `transpose` — it double-rotates
- Stored dimensions (e.g., 1920x1080) display as 1080x1920 after auto-rotation

---

## Step 2: Transcribe

Use the `/transcribe` skill or whisper-cli to generate an SRT file:

```bash
whisper-cli -m ~/.local/share/whisper-cpp/models/ggml-large-v3.bin \
  -f "$RAW_VIDEO" --output-srt -of "$PROJECT_DIR/subtitles" -l en
```

If whisper-cli is not available, use the `/transcribe` skill.

Review the SRT file and fix any transcription errors. Each subtitle block should be 2-3 lines max for readability.

**Self-verify:** Read the SRT file, check for obvious errors (garbled words, missing segments, overlapping timestamps). Auto-fix any issues. Report a brief summary of the transcript to the user but proceed without waiting.

---

## Step 3: Enhance Audio

Create an audio-enhanced copy of the raw video. Use aggressive wind noise reduction for outdoor footage:

```bash
ffmpeg -y \
  -i "$RAW_VIDEO" \
  -af "highpass=f=80,lowpass=f=8000,afftdn=nf=-20:nr=30:nt=w,acompressor=threshold=-20dB:ratio=4:attack=5:release=50,equalizer=f=200:t=h:width=100:g=3,equalizer=f=3000:t=h:width=1000:g=2,loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:v copy \
  "$ASSETS_DIR/raw_enhanced.MOV"
```

### Audio filter breakdown:
- `highpass=f=80` — Remove low rumble
- `lowpass=f=8000` — Cut wind/hiss above 8kHz (use 14000 for indoor)
- `afftdn=nf=-20:nr=30:nt=w` — Aggressive FFT noise reduction (nr=30 for outdoor wind, nr=15 for indoor)
- `acompressor` — Even out volume dynamics
- `equalizer=f=200:g=3` — Boost low-mid warmth
- `equalizer=f=3000:g=2` — Boost speech clarity
- `loudnorm=I=-16` — Normalize to streaming standard

For **indoor** footage, use lighter settings:
```bash
-af "highpass=f=80,lowpass=f=14000,afftdn=nf=-25:nr=15:nt=w,acompressor=threshold=-18dB:ratio=3:attack=10:release=100:makeup=2,equalizer=f=3000:t=q:w=1.5:g=3,loudnorm=I=-16:TP=-1.5:LRA=11"
```

---

## Step 4: Generate B-roll Images

Based on the transcription, identify 4-6 key visual concepts that need B-roll images. Use the `/nano-banana` skill to generate them.

### Guidelines for B-roll prompts:
- Match the topic being discussed at each point in the video
- Use photorealistic style — these should look like real photos
- Generate at landscape aspect ratio (the top half is 1080x960, roughly 9:8)
- Name files descriptively: `broll_gutter_full.png`, `broll_hand_granules.png`, etc.

### Timing map:
Create a timing map that maps each B-roll image to a time range in the video. Account for the speed multiplier (divide SRT times by 1.2):

```
Image 1: 0.00 - X.XX seconds (after speed adjustment)
Image 2: X.XX - Y.YY seconds
...
Last image: Z.ZZ - end (use gte() to keep showing through end)
```

**Self-verify:** View each generated image with the Read tool. Check that:
- Images are photorealistic (not cartoon/illustration)
- Subject matches the script topic
- No text artifacts or watermarks
- Resolution is adequate (at least 1024px wide)
If any image fails, regenerate it with an improved prompt. Proceed automatically once all pass.

---

## Step 5: Annotate B-roll Images

Add red arrows, circles, or green arrows to highlight key areas in each B-roll image. Use the bundled annotation script:

```bash
SCRIPTS="$HOME/.claude/commands/split-screen-video-scripts"
python3 "$SCRIPTS/annotate_broll.py" <image_path> <annotation_type> <params...>
```

### Annotation types:
- `red_arrow <start_x%> <start_y%> <end_x%> <end_y%> [head_size] [shaft_width]`
- `red_circle <center_x%> <center_y%> <radius%> [width]`
- `green_arrow <start_x%> <start_y%> <end_x%> <end_y%> [head_size] [shaft_width]`

All coordinates are **percentages (0-100)** of image dimensions. The script overwrites the original file, so annotate after all images are finalized.

### Examples:
```bash
python3 "$SCRIPTS/annotate_broll.py" assets/broll_gutter.png red_arrow 12 85 42 35
python3 "$SCRIPTS/annotate_broll.py" assets/broll_hand.png red_circle 48 52 22
python3 "$SCRIPTS/annotate_broll.py" assets/broll_shingle.png green_arrow 25 5 25 30
```

### Annotation guidelines:
- **Red arrow**: Point to the main subject being discussed (e.g., granules in gutter)
- **Red circle**: Highlight specific details (e.g., granules in palm, damaged area)
- **Green arrow**: Point to positive/good examples (e.g., new shingle)
- Coordinates are percentages 0-100 (e.g., `50 50` = center of image)
- View each B-roll image first to determine correct annotation placement
- Not every image needs annotation — skip if unnecessary

**Self-verify:** View each annotated image with the Read tool. Check that:
- Arrows/circles point to the correct area
- Annotations don't obscure important details
- Colors are visible against the image background
If placement is wrong, adjust coordinates and re-run. Proceed automatically once all look correct.

---

## Step 6: Generate Subtitle Overlays

Create transparent PNG overlays with yellow bars for each subtitle using the bundled script:

```bash
SCRIPTS="$HOME/.claude/commands/split-screen-video-scripts"
python3 "$SCRIPTS/generate_subtitles.py" "$PROJECT_DIR" 1.2
```

This reads `$PROJECT_DIR/subtitles.srt`, generates PNGs to `$PROJECT_DIR/assets/subs/`, and prints FFmpeg overlay timing (already divided by the speed multiplier).

### Design specs (handled automatically by the script):
- **Font**: Arial Bold 48pt, black text on yellow (255, 224, 0) rounded rectangle
- **Max width**: `1080 - 80px` (40px margin each side), auto word-wraps
- **Vertical position**: Centered at y=960 (the split line between B-roll and presenter)
- **Balanced padding**: Compensates for font ascent offset to center text vertically
- **Output**: 1080x1920 RGBA PNGs (transparent except for the yellow bar)

**Self-verify:** After generating all subtitle PNGs:
1. Read the widest subtitle image (highest bar_w in the output) with the Read tool
2. Confirm the yellow bar has at least 40px margin on each side
3. If any bar exceeds the margin, reduce FONT_SIZE by 2pt and regenerate all
4. Proceed automatically once margins are safe

---

## Step 7: FFmpeg Composite — Final Build

### Directory structure:
```
project_dir/
├── assets/
│   ├── raw_enhanced.MOV
│   ├── broll_*.png (annotated)
│   └── subs/
│       └── sub_01.png ... sub_NN.png
├── subtitles.srt
├── build_video.sh
└── output_video.mp4
```

### Presenter crop calculation:
The presenter video (after auto-rotation) is 1080x1920 portrait.

```
Scale: 1.5x → 1620x2880
Crop:  1080x960 from (270, 700)
  - X = (1620 - 1080) / 2 = 270 (horizontally centered)
  - Y = 700 (shows head near top, chest + hands visible)
```

**IMPORTANT:** Always test the crop on a single frame BEFORE full render:
```bash
ffmpeg -y -ss 10 -i "$ASSETS/raw_enhanced.MOV" \
  -vf "scale=1620:2880,crop=1080:960:270:700" \
  -frames:v 1 -q:v 2 /tmp/crop_test.jpg 2>/dev/null
```
View with Read tool. **Auto-adjust Y** until the framing is correct:
- Head too low (excess background above) → increase Y by 50-100, re-test
- Head cut off at top → decrease Y by 50-100, re-test
- Target: presenter's head at ~10-15% from the top, hands visible at bottom
- Test 2-3 different Y values if needed, pick the best one
- Y=700 is the default starting point for 1.5x zoom on iPhone portrait video

### FFmpeg filter_complex structure:

```
# 1. Presenter: speed up + zoom + crop
[0:v]setpts=PTS/{SPEED},scale=1620:2880,crop=1080:960:270:{CROP_Y}[presenter];
[0:a]atempo={SPEED}[audio_fast];

# 2. B-roll images: scale to top-half size
[1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[img1];
[2:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[img2];
...

# 3. Timed B-roll overlays on black base
color=black:1080x960:d=50,fps=30[base_top];
[base_top][img1]overlay=0:0:enable='between(t,0,T1)'[top1];
[top1][img2]overlay=0:0:enable='between(t,T1,T2)'[top2];
...
[topN-1][imgN]overlay=0:0:enable='gte(t,TN)'[top_final];  # LAST image uses gte()

# 4. Stack: B-roll on top, presenter on bottom
[top_final][presenter]vstack[stacked];

# 5. Subtitle overlays (already 1080x1920 RGBA PNGs)
[6:v]scale=1080:1920[s1];
...
[stacked][s1]overlay=0:0:enable='between(t,S1_start,S1_end)'[v1];
...
```

### Critical build rules:
1. **Last B-roll**: Always use `enable='gte(t,...)'` — never `between()` — so it stays through the end
2. **Base duration**: Set `d=50` (or higher than video duration) to prevent black frames
3. **Speed timing**: All overlay timings must be SRT_time / SPEED
4. **Output flags**: `-c:v libx264 -crf 20 -preset medium -c:a aac -b:a 192k -movflags +faststart`
5. **Duration**: `-t {final_duration}` where final_duration = original_duration / SPEED

### Post-render self-verification:
Extract 4-6 frames from the output and view them with the Read tool. Check for these issues and **auto-correct** if found:

| Issue | Check at | Fix |
|-------|----------|-----|
| Presenter head cut off | t=3s | Decrease crop Y by 50-100, re-render |
| Presenter too low (excess background above head) | t=3s | Increase crop Y by 50-100, re-render |
| B-roll shows raw footage at end | t=last 3s | Change last overlay to `gte()`, re-render |
| Subtitle clipped on sides | any frame with subtitle | Reduce MAX_BAR_W or FONT_SIZE, regenerate subs, re-render |
| Black frames in top half | any time | Increase base color `d=` value, re-render |
| No audio | check ffmpeg output | Verify `-map "[audio_fast]"` is present |

**Auto-correction loop:** If any issue is found, fix it and re-render. Extract new verification frames. Repeat until all checks pass (max 3 iterations).

**IMPORTANT:** If `drawtext` filter is unavailable in ffmpeg (common with Homebrew builds), this is why we use Pillow PNG overlays instead. Never attempt `drawtext` — it will fail silently.

### Final report to user:
Once all self-verification passes, report:
- Output file path and size
- Duration and resolution
- Number of B-roll images and subtitles
- Any auto-corrections that were made
- Show 2-3 representative frames from the final video

---

## Step 8: Trim Dead Air (Start & End)

After the final render passes visual verification, check for dead air (silence/ambient noise without speech) at the beginning and end of the video. Raw footage often has 1-3 seconds of silence before the presenter starts talking and after they stop.

### Detection method:

Use `astats` Peak_level analysis at 0.2s intervals to find where speech starts and ends:

```bash
OUTPUT="$PROJECT_DIR/output_video.mp4"
DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$OUTPUT")

echo "=== START ==="
for t in 0.0 0.2 0.4 0.6 0.8 1.0 1.2 1.4 1.6 1.8 2.0 2.2 2.4; do
  result=$(ffmpeg -ss "$t" -t 0.2 -i "$OUTPUT" \
    -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level" \
    -f null - 2>&1 | grep "Peak_level" | tail -1 | awk -F= '{print $2}')
  echo "  t=${t}s: Peak=${result} dB"
done

echo "=== END ==="
END_START=$(echo "$DURATION - 3.0" | bc -l)
for offset in 0.0 0.5 1.0 1.5 2.0 2.5; do
  t=$(echo "$END_START + $offset" | bc -l)
  result=$(ffmpeg -ss "$t" -t 0.2 -i "$OUTPUT" \
    -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level" \
    -f null - 2>&1 | grep "Peak_level" | tail -1 | awk -F= '{print $2}')
  printf "  t=%.1fs: Peak=%s dB\n" "$t" "$result"
done
```

### Interpreting results:

| Peak level | Meaning |
|-----------|---------|
| < -12 dB | **Speech** — clear voice present |
| -12 to -18 dB | **Borderline** — could be trailing speech or loud ambient |
| > -18 dB | **Ambient/silence** — no voice, safe to trim |

**IMPORTANT:** The `loudnorm` filter in Step 3 boosts ambient noise to -20 to -25 dB, so `silencedetect` won't work (it never finds silence). Use Peak_level instead — the jump from -20dB ambient to -5dB speech is unmistakable.

### Fine-grained analysis:

Once you identify the approximate transition, do 0.1s interval analysis around that point:

```bash
for t in 1.0 1.1 1.2 1.3 1.4 1.5 1.6 1.7 1.8 1.9 2.0; do
  result=$(ffmpeg -ss "$t" -t 0.1 -i "$OUTPUT" \
    -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level" \
    -f null - 2>&1 | grep "Peak_level" | tail -1 | awk -F= '{print $2}')
  echo "  t=${t}s: Peak=${result} dB"
done
```

### Trimming:

Add ~0.2s buffer before speech onset so it doesn't sound clipped:

```bash
# Trim start only:
ffmpeg -y -ss $TRIM_START -i "$OUTPUT" -t $NEW_DURATION \
  -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 192k \
  -movflags +faststart "$OUTPUT_TRIMMED"

# Trim end only:
ffmpeg -y -i "$OUTPUT" -t $TRIM_END \
  -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 192k \
  -movflags +faststart "$OUTPUT_TRIMMED"

# Trim both:
ffmpeg -y -ss $TRIM_START -i "$OUTPUT" -t $NEW_DURATION \
  -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 192k \
  -movflags +faststart "$OUTPUT_TRIMMED"
```

Where: `NEW_DURATION = TRIM_END - TRIM_START`

### Self-verify after trimming:

Re-run Peak_level analysis on the first 1s and last 1s of the trimmed video. Confirm speech is present within the first 0.4s (Peak < -12dB) and the video ends within 1s of the last speech.

---

## Quick Reference

| Parameter | Value |
|-----------|-------|
| Output resolution | 1080x1920 (9:16 vertical) |
| Top half | 1080x960 (B-roll images) |
| Bottom half | 1080x960 (presenter, zoomed 1.5x) |
| Speed | 1.2x (configurable) |
| Presenter crop | scale=1620:2880, crop=1080:960:270:700 |
| Subtitle font | Arial Bold 48pt |
| Subtitle bar color | Yellow (255, 224, 0) |
| Subtitle margin | 40px minimum each side |
| Audio preset | Podcast: hp=80, lp=14000, nr=15 (see Step 3) |
| Codec | H.264 CRF 20, AAC 192k |
| B-roll annotations | Red arrows, red circles, green arrows |

## Bundled Scripts

All reusable scripts are in `~/.claude/commands/split-screen-video-scripts/`:

| Script | Purpose |
|--------|---------|
| `generate_subtitles.py` | Generate yellow-bar subtitle PNGs from SRT file |
| `annotate_broll.py` | Add red arrows, circles, green arrows to B-roll images |
| `build_video.sh` | Template FFmpeg build script with placeholder variables |

Copy `build_video.sh` to the project directory and customize the variables for each video.

## Dependencies
- ffmpeg (Homebrew)
- Python 3 with Pillow (`pip3 install Pillow`)
- whisper-cli or `/transcribe` skill (for transcription)
- `/nano-banana` skill (for B-roll image generation)
- `/enhance-audio` skill (reference for audio presets)
- `/view-video` skill (for frame extraction and preview)
