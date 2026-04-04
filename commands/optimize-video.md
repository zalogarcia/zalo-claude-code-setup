Process and upload optimized videos to Supabase Storage with faststart + compression.

## Usage
Provide the local file path and the Supabase Storage path as arguments:
```
/optimize-video /path/to/local/video.mp4 Storage/Path/filename.mp4
```

## Instructions

1. Run ffmpeg to compress and add faststart:
```bash
ffmpeg -y -i "$LOCAL_PATH" \
  -c:v libx264 -crf 23 -preset medium \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  "/tmp/optimized_video.mp4"
```

2. Show the before/after file sizes and compression ratio.

3. Upload to Supabase Storage bucket `course-content` on project `dqzxcphqxelkfwynfljc` using the service role key (get it via `supabase projects api-keys --project-ref dqzxcphqxelkfwynfljc`). Use curl with `x-upsert: true` header to overwrite if the file already exists.

4. Verify the upload by checking the Content-Length header of the uploaded file.

5. Clean up the temp file.

If the user provides just a local path without a storage path, ask them for the Supabase Storage path (e.g., `Elite Courses/course-slug/filename.mp4` or `Copy My AI Agency - Full Course/module/lesson/filename.mp4`).

## Settings
- Codec: H.264 (libx264), CRF 23, preset medium
- Audio: AAC 128kbps
- Always enable faststart (`-movflags +faststart`)
- Bucket: `course-content`
- Supabase project: `dqzxcphqxelkfwynfljc`
