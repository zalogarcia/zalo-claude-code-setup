Extract frames from a video using ffmpeg so Claude can visually analyze the content.

## Usage
Provide the local video file path and optionally the number of frames:
```
/view-video /path/to/video.mp4
/view-video /path/to/video.mp4 10
```

## Instructions

1. First, get video metadata using ffprobe:
```bash
ffprobe -v quiet -print_format json -show_format -show_streams "$VIDEO_PATH"
```
Report: duration, resolution, codec, fps, and file size.

2. Extract frames to a temp directory. Default is 6 frames evenly spaced across the video. If the user provides a number, use that instead.
```bash
FRAMES_DIR=$(mktemp -d)
DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO_PATH")
NUM_FRAMES=${2:-6}
INTERVAL=$(echo "$DURATION / ($NUM_FRAMES + 1)" | bc -l)

for i in $(seq 1 $NUM_FRAMES); do
  TIMESTAMP=$(echo "$INTERVAL * $i" | bc -l)
  ffmpeg -y -ss "$TIMESTAMP" -i "$VIDEO_PATH" -frames:v 1 -q:v 2 "$FRAMES_DIR/frame_$(printf '%03d' $i).jpg" 2>/dev/null
done
```

3. Use the Read tool to view each extracted frame image. Describe what you see in each frame, including:
   - What's happening visually
   - Any text or graphics on screen
   - Scene transitions or changes between frames
   - Overall video content summary

4. After analysis, clean up the temp directory:
```bash
rm -rf "$FRAMES_DIR"
```

5. Provide a summary of the video content based on the frames.

## Settings
- Default frames: 6 (evenly spaced)
- Frame format: JPEG (quality 2)
- Always show video metadata first
- Always clean up temp files after viewing
