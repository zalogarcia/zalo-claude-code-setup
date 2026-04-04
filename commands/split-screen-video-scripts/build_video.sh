#!/bin/bash
# Template: Build split-screen video from raw footage + B-roll images + subtitle overlays
# Layout: Top half = B-roll images, Bottom half = talking head (zoomed in)
#
# Usage: Copy this template to your project directory and customize:
#   - BASE: project directory path
#   - B-roll image paths and count
#   - B-roll timing map (between/gte expressions)
#   - Subtitle count and timing
#   - SPEED, CROP_Y, DURATION values
#
# ffmpeg auto-rotates iPhone video, so no transpose needed

# === CUSTOMIZE THESE ===
BASE="/path/to/project"
ASSETS="$BASE/assets"
SUBS="$ASSETS/subs"
OUTPUT="$BASE/output_video.mp4"
SPEED=1.2
CROP_Y=700        # Presenter vertical crop offset (test with single frame first)
DURATION=44.13    # Final video duration (original_duration / SPEED)
# === END CUSTOMIZE ===

ffmpeg -y \
  -i "$ASSETS/raw_enhanced.MOV" \
  -loop 1 -i "$ASSETS/broll_1.png" \
  -loop 1 -i "$ASSETS/broll_2.png" \
  -loop 1 -i "$ASSETS/broll_3.png" \
  -loop 1 -i "$ASSETS/broll_4.png" \
  -loop 1 -i "$ASSETS/broll_5.png" \
  -loop 1 -i "$SUBS/sub_01.png" \
  -loop 1 -i "$SUBS/sub_02.png" \
  -loop 1 -i "$SUBS/sub_03.png" \
  -loop 1 -i "$SUBS/sub_04.png" \
  -loop 1 -i "$SUBS/sub_05.png" \
  -loop 1 -i "$SUBS/sub_06.png" \
  -loop 1 -i "$SUBS/sub_07.png" \
  -loop 1 -i "$SUBS/sub_08.png" \
  -loop 1 -i "$SUBS/sub_09.png" \
  -loop 1 -i "$SUBS/sub_10.png" \
  -filter_complex "
    [0:v]setpts=PTS/$SPEED,scale=1620:2880,crop=1080:960:270:$CROP_Y[presenter];

    [0:a]atempo=$SPEED[audio_fast];

    [1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[img1];
    [2:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[img2];
    [3:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[img3];
    [4:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[img4];
    [5:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[img5];

    color=black:1080x960:d=50,fps=30[base_top];

    [base_top][img1]overlay=0:0:enable='between(t,0,T1)'[top1];
    [top1][img2]overlay=0:0:enable='between(t,T1,T2)'[top2];
    [top2][img3]overlay=0:0:enable='between(t,T2,T3)'[top3];
    [top3][img4]overlay=0:0:enable='between(t,T3,T4)'[top4];
    [top4][img5]overlay=0:0:enable='gte(t,T4)'[top_final];

    [top_final][presenter]vstack[stacked];

    [6:v]scale=1080:1920[s1];
    [7:v]scale=1080:1920[s2];
    [8:v]scale=1080:1920[s3];
    [9:v]scale=1080:1920[s4];
    [10:v]scale=1080:1920[s5];
    [11:v]scale=1080:1920[s6];
    [12:v]scale=1080:1920[s7];
    [13:v]scale=1080:1920[s8];
    [14:v]scale=1080:1920[s9];
    [15:v]scale=1080:1920[s10];

    [stacked][s1]overlay=0:0:enable='between(t,S1_START,S1_END)'[v1];
    [v1][s2]overlay=0:0:enable='between(t,S2_START,S2_END)'[v2];
    [v2][s3]overlay=0:0:enable='between(t,S3_START,S3_END)'[v3];
    [v3][s4]overlay=0:0:enable='between(t,S4_START,S4_END)'[v4];
    [v4][s5]overlay=0:0:enable='between(t,S5_START,S5_END)'[v5];
    [v5][s6]overlay=0:0:enable='between(t,S6_START,S6_END)'[v6];
    [v6][s7]overlay=0:0:enable='between(t,S7_START,S7_END)'[v7];
    [v7][s8]overlay=0:0:enable='between(t,S8_START,S8_END)'[v8];
    [v8][s9]overlay=0:0:enable='between(t,S9_START,S9_END)'[v9];
    [v9][s10]overlay=0:0:enable='between(t,S10_START,S10_END)'[out]
  " \
  -map "[out]" -map "[audio_fast]" \
  -c:v libx264 -crf 20 -preset medium \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  -t $DURATION \
  "$OUTPUT"

echo "Done! Output: $OUTPUT"
ls -lh "$OUTPUT"
