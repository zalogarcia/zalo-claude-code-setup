---
name: cf-crawl
description: Crawl websites using Cloudflare Browser Rendering API. Use when the user wants to scrape, crawl, or extract content from a website (single page or multi-page). Returns HTML, Markdown, or structured JSON.
---

Scrape and crawl websites using the Cloudflare Browser Rendering REST API.

## Configuration

Secrets are stored in environment variables (configured in `~/.claude/settings.local.json`):

- **Account ID:** `$CF_ACCOUNT_ID`
- **API Token:** `$CLOUDFLARE_API_TOKEN` or `$CF_API_TOKEN`

```bash
ACCOUNT_ID="${CF_ACCOUNT_ID}"
API_TOKEN="${CLOUDFLARE_API_TOKEN:-${CF_API_TOKEN}}"
BASE="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/browser-rendering"
```

## Endpoint Selection

| Need | Endpoint | Method |
|------|----------|--------|
| Single page → HTML | `/content` | Synchronous POST |
| Single page → Markdown | `/markdown` | Synchronous POST |
| Multi-page crawl | `/crawl` | Async POST + poll GET |

**IMPORTANT:** For single-page scraping, prefer `/content` or `/markdown` — they are synchronous and return results immediately. Only use `/crawl` for multi-page jobs.

---

## Single Page: `/markdown` (preferred for most tasks)

Returns a page as clean markdown. Synchronous — result comes back in the response.

```bash
curl -s -X POST "${BASE}/markdown" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Response:**
```json
{
  "success": true,
  "result": "# Example Domain\n\nThis domain is for use in..."
}
```

### With JS rendering for SPAs

```bash
curl -s -X POST "${BASE}/markdown" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "gotoOptions": {"waitUntil": "networkidle0"}
  }'
```

### Skip unnecessary resources (faster)

```bash
curl -s -X POST "${BASE}/markdown" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "rejectResourceTypes": ["image", "media", "font", "stylesheet"]
  }'
```

---

## Single Page: `/content` (full rendered HTML)

Returns fully rendered HTML including head section, after JavaScript execution.

```bash
curl -s -X POST "${BASE}/content" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Response:**
```json
{
  "success": true,
  "result": "<!DOCTYPE html><html>..."
}
```

### From raw HTML input (no URL needed)

```bash
curl -s -X POST "${BASE}/content" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"html": "<html><body><script>document.body.innerHTML = \"Hello\"</script></body></html>"}'
```

---

## Multi-Page: `/crawl` (async)

Crawls an entire site by following links and sitemaps. Async: POST to start, GET to poll.

> **Note:** The /crawl endpoint launched 2026-03-10 and may still be rolling out. If polling returns "Crawl job not found", fall back to sequential `/markdown` calls for each URL.

### Start a crawl job

```bash
JOB_ID=$(curl -s -X POST "${BASE}/crawl" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "limit": 10,
    "formats": ["markdown"],
    "render": true
  }' | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))")
echo "Job ID: $JOB_ID"
```

### Poll for results

```bash
curl -s "${BASE}/crawl/${JOB_ID}" \
  -H "Authorization: Bearer ${API_TOKEN}"
```

Poll every 5-10 seconds until `result.status` is not `"running"`.

**Response:**
```json
{
  "success": true,
  "result": {
    "id": "job-id",
    "status": "completed",
    "browserSecondsUsed": 12.5,
    "total": 10,
    "finished": 10,
    "records": [
      {
        "url": "https://example.com/page",
        "status": "completed",
        "markdown": "# Page Title\n...",
        "html": "<html>...</html>",
        "json": {},
        "metadata": { "status": 200, "title": "Page Title", "url": "https://example.com/page" }
      }
    ],
    "cursor": null
  }
}
```

### Cancel a job

```bash
curl -s -X DELETE "${BASE}/crawl/${JOB_ID}" \
  -H "Authorization: Bearer ${API_TOKEN}"
```

---

## /crawl Parameters Reference

### Core

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | String | **required** | Starting URL |
| `limit` | Number | 10 | Max pages (max 100,000) |
| `depth` | Number | 100,000 | Max link depth |
| `source` | String | "all" | Discovery: `all`, `sitemaps`, `links` |
| `formats` | Array | ["html"] | Output: `html`, `markdown`, `json` |
| `render` | Boolean | true | JS rendering (false = fast static mode) |
| `maxAge` | Number | 86400 | Cache TTL in seconds |
| `modifiedSince` | Number | — | Unix timestamp; skip older pages |

### URL Filtering (`options` object)

| Parameter | Type | Description |
|-----------|------|-------------|
| `options.includeExternalLinks` | Boolean | Follow external links (default: false) |
| `options.includeSubdomains` | Boolean | Follow subdomain links |
| `options.includePatterns` | Array | Wildcard include (e.g. `"/blog/**"`) |
| `options.excludePatterns` | Array | Wildcard exclude (higher priority) |

Pattern syntax: `*` = any chars except `/`, `**` = any chars including `/`.

### JSON Extraction (formats includes "json")

```json
{
  "formats": ["json"],
  "jsonOptions": {
    "prompt": "Extract product name, price, and description",
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "product",
        "schema": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "price": { "type": "number" },
            "description": { "type": "string" }
          }
        }
      }
    }
  }
}
```

Note: Uses Workers AI — incurs additional usage costs.

### GET Query Parameters (polling)

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | String | Pagination (when response > 10 MB) |
| `limit` | Number | Max records per response |
| `status` | String | Filter: `queued`, `completed`, `disallowed`, `skipped`, `errored`, `cancelled` |

---

## Shared Parameters (all endpoints)

### Authentication & Headers

| Parameter | Type | Description |
|-----------|------|-------------|
| `authenticate` | Object | `{ "username": "...", "password": "..." }` |
| `setExtraHTTPHeaders` | Object | Custom headers |
| `cookies` | Array | Session cookies |

### Browser Control

| Parameter | Type | Description |
|-----------|------|-------------|
| `gotoOptions` | Object | `{ "waitUntil": "networkidle0", "timeout": 30000 }` |
| `waitForSelector` | Object | `{ "selector": ".content", "timeout": 5000, "visible": true }` |
| `rejectResourceTypes` | Array | Block: `image`, `media`, `font`, `stylesheet` |
| `userAgent` | String | Custom UA (does NOT bypass bot detection) |

---

## Fallback Strategy for Multi-Page Scraping

If `/crawl` is unavailable, scrape multiple pages sequentially with `/markdown`:

```bash
URLS=("https://example.com/page1" "https://example.com/page2" "https://example.com/page3")
for URL in "${URLS[@]}"; do
  echo "--- Scraping: $URL ---"
  curl -s -X POST "${BASE}/markdown" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"$URL\", \"rejectResourceTypes\": [\"image\", \"media\", \"font\"]}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('result','ERROR'))"
  echo ""
done
```

---

## Workflow Guidelines

1. **Single page? Use `/markdown` or `/content`** — synchronous, instant results.
2. **Multi-page? Try `/crawl` first**, fall back to sequential `/markdown` if it fails.
3. **Save results to a file** — output can be large. Pipe to a file, not stdout.
4. **Use `rejectResourceTypes`** to skip images/fonts/media for faster scraping.
5. **Use `gotoOptions.waitUntil: "networkidle0"`** for JS-heavy SPAs.
6. **For `/crawl`: poll with backoff** — 5s intervals, check `finished` vs `total` for progress.
7. **Handle pagination** — if `cursor` is non-null, fetch the next page.

## Behavior Notes

- Respects `robots.txt` and crawl-delay directives
- Cannot bypass bot protection or CAPTCHAs — always identified as a bot
- `excludePatterns` has higher priority than `includePatterns`
- /crawl: job max runtime 7 days, results retained 14 days
- Free + Paid Workers plans supported (open beta)
