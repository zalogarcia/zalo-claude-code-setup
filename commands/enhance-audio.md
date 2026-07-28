Enhance and clean up audio in video/audio files using FFmpeg filters. Removes noise, normalizes volume, and improves speech clarity.

## Usage
Provide the file path and optionally a preset:
```
/enhance-audio /path/to/video.mp4
/enhance-audio /path/to/audio.wav light
/enhance-audio /path/to/video.mp4 heavy
```

## Instructions

1. First, analyze the audio:
```bash
ffprobe -v quiet -print_format json -show_format -show_streams -select_streams a "$FILE_PATH"
```
Report: duration, codec, sample rate, channels, bitrate, and loudness if available.

2. Analyze audio levels to understand the noise/signal situation:
```bash
ffmpeg -i "$FILE_PATH" -af "volumedetect" -vn -f null /dev/null 2>&1
```
Report: mean volume, max volume, and dynamic range.

3. Apply the enhancement preset. Default is `podcast`. Ask the user which preset if not specified.

### Presets

**light** — Minimal cleanup, preserves natural sound:
```bash
ffmpeg -y -i "$FILE_PATH" \
  -af "highpass=f=80,lowpass=f=12000,afftdn=nf=-25" \
  -c:v copy \
  "$OUTPUT_PATH"
```

**standard** — Good all-around speech cleanup (default):
```bash
ffmpeg -y -i "$FILE_PATH" \
  -af "highpass=f=80,lowpass=f=12000,afftdn=nf=-30:nr=12:nt=w,areverse,silenceremove=start_periods=1:start_silence=0.1:start_threshold=-50dB,areverse,loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:v copy \
  "$OUTPUT_PATH"
```

**heavy** — Aggressive noise removal + compression for noisy environments:
```bash
ffmpeg -y -i "$FILE_PATH" \
  -af "highpass=f=100,lowpass=f=10000,afftdn=nf=-20:nr=20:nt=w,anlmdn=s=10:p=0.002:m=15,acompressor=threshold=-20dB:ratio=4:attack=5:release=50,loudnorm=I=-16:TP=-1.5:LRA=7" \
  -c:v copy \
  "$OUTPUT_PATH"
```

**podcast** — Optimized for voice/podcast production:
```bash
ffmpeg -y -i "$FILE_PATH" \
  -af "highpass=f=80,lowpass=f=14000,afftdn=nf=-25:nr=15:nt=w,acompressor=threshold=-18dB:ratio=3:attack=10:release=100:makeup=2,equalizer=f=3000:t=q:w=1.5:g=3,equalizer=f=150:t=q:w=1:g=-2,loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:v copy \
  "$OUTPUT_PATH"
```

### Filter Explanations
- `highpass=f=80` — Remove rumble below 80Hz
- `lowpass=f=12000` — Remove hiss above 12kHz
- `afftdn` — FFT-based noise reduction (nf=noise floor, nr=noise reduction amount, nt=noise type: w=white)
- `anlmdn` — Non-local means denoising (slower but better quality)
- `acompressor` — Dynamic range compression (evens out volume)
- `loudnorm` — EBU R128 loudness normalization (I=-16 LUFS is standard for streaming)
- `equalizer` — EQ boost/cut for speech clarity
- `silenceremove` — Trim leading/trailing silence

4. Name the output file:
   - For video files: `{original_name}_enhanced.{ext}`
   - For audio files: `{original_name}_enhanced.{ext}`
   - Place in the same directory as the original

5. Compare before/after:
```bash
# Check output levels
ffmpeg -i "$OUTPUT_PATH" -af "volumedetect" -vn -f null /dev/null 2>&1
```
Report the before/after mean volume and any improvement.

6. Show the file sizes (before/after) and let the user listen.

## Notes
- `-c:v copy` preserves the video stream untouched (no re-encoding)
- For video files, only the audio is processed
- All processing is local and free (no API needed)
- FFmpeg must be installed (`brew install ffmpeg`)
