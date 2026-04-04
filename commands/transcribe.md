Transcribe audio/video files using OpenAI Whisper. Supports 99 languages with automatic detection.

## Usage
Provide the file path and optionally the model size and language:
```
/transcribe /path/to/video.mp4
/transcribe /path/to/audio.mp3 large-v3
/transcribe /path/to/video.mp4 medium es
```

## Instructions

1. First, check what we're working with using ffprobe:
```bash
ffprobe -v quiet -print_format json -show_format -show_streams "$FILE_PATH"
```
Report: duration, audio codec, sample rate, and file size.

2. Extract audio to a Whisper-friendly format (16kHz mono WAV):
```bash
AUDIO_FILE=$(mktemp /tmp/whisper_audio_XXXXXX.wav)
ffmpeg -y -i "$FILE_PATH" -ar 16000 -ac 1 -c:a pcm_s16le "$AUDIO_FILE"
```

3. Run whisper-cpp to transcribe. Default model is `small` (good speed/quality balance). If the user specifies a model, use that instead.

Available models (download on first use):
| Model | Size | Quality | Speed |
|-------|------|---------|-------|
| tiny | 39M | Low | Fastest |
| base | 74M | Medium | Fast |
| small | 244M | Good | Medium |
| medium | 769M | Better | Slow |
| large-v3 | 1550M | Best | Slowest |

```bash
MODEL=${2:-large-v3}
LANGUAGE_FLAG=""
if [ -n "$3" ]; then
  LANGUAGE_FLAG="-l $3"
fi

# Models stored in ~/.local/share/whisper-cpp/models/
# Download model if not present:
# curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL.bin" -o ~/.local/share/whisper-cpp/models/ggml-$MODEL.bin

# Transcribe (whisper-cli supports mp3, wav, flac, ogg directly)
whisper-cli \
  -m ~/.local/share/whisper-cpp/models/ggml-$MODEL.bin \
  -f "$AUDIO_FILE" \
  -l auto \
  --output-srt \
  --output-vtt \
  --output-json-full \
  --print-colors \
  $LANGUAGE_FLAG
```

If whisper-cpp is not available, fall back to Python whisper:
```bash
whisper "$AUDIO_FILE" --model $MODEL --output_format all --word_timestamps True $LANGUAGE_FLAG
```

4. Read and display the transcript to the user. Show:
   - The full text transcript
   - Note the language detected (if auto-detected)
   - Mention that SRT/VTT/JSON files were also generated

5. Clean up the temporary audio file:
```bash
rm -f "$AUDIO_FILE"
```

6. Ask the user if they want:
   - The transcript saved to a specific file
   - A summary of the content
   - Subtitles in SRT/VTT format copied somewhere
   - Translation to English (if non-English source)

## Language Codes (common)
- `en` English, `es` Spanish, `fr` French, `de` German, `it` Italian
- `pt` Portuguese, `nl` Dutch, `ru` Russian, `zh` Chinese, `ja` Japanese
- `ko` Korean, `ar` Arabic, `hi` Hindi, `tr` Turkish, `pl` Polish
- Auto-detect if no language specified (default)

## Settings
- Default model: large-v3 (best quality)
- Audio format: 16kHz mono WAV (optimal for Whisper)
- Output formats: SRT, VTT, JSON (word-level timestamps)
- Always extract audio first with ffmpeg for best results
