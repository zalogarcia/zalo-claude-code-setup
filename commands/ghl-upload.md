# GHL Media Upload

Upload files to GoHighLevel's media library via API.

## Usage
`/ghl-upload <file_or_directory_path> [--name-prefix <prefix>]`

## Instructions

Upload images/files to GHL media library and return CDN URLs.

### Configuration

Secrets are stored in environment variables (configured in `~/.claude/settings.local.json`):

- **Location ID**: `$GHL_LOCATION_ID`
- **API Key**: `$GHL_API_KEY`
- **API Endpoint**: `https://services.leadconnectorhq.com/medias/upload-file`
- **API Version**: 2021-07-28

### Steps

1. Determine what to upload:
   - If a directory path is given, find all image files (png, jpg, jpeg, webp, gif, svg) in it
   - If a single file path is given, upload just that file
   - If no path given via argument, ask the user what to upload

2. For each file, run:
```bash
curl -s -X POST "https://services.leadconnectorhq.com/medias/upload-file" \
  -H "Authorization: Bearer ${GHL_API_KEY}" \
  -H "Version: 2021-07-28" \
  -F "file=@<FILE_PATH>" \
  -F "name=<PREFIX>-<FILENAME>" \
  -F "locationId=${GHL_LOCATION_ID}"
```

3. Collect all returned URLs from the JSON response (`url` field)

4. Present results to the user as a markdown table with columns: #, Filename, URL

5. Optionally save URLs to a `.md` file in the same directory if the user requests it

### Notes
- The API returns JSON with `fileId`, `url`, and `traceId`
- CDN URLs follow pattern: `https://assets.cdn.filesafe.space/${GHL_LOCATION_ID}/media/<uuid>.<ext>`
- Upload sequentially to avoid rate limiting
- If `--name-prefix` is not provided, use the original filename
