---
name: telegram
description: Send messages, files, images, or documents to the user via their Telegram bot. Use when the user asks to send something to Telegram, notify them, or share content via Telegram.
---

Send content to the user's Telegram bot using the Telegram Bot API.

## Configuration

Secrets are stored in environment variables (configured in `~/.claude/settings.local.json`):

- **Bot Token:** `$TELEGRAM_BOT_TOKEN`
- **Chat ID:** `$TELEGRAM_CHAT_ID`
- **Bot Username:** @zalocc9191_bot

## How to Send

### Text Messages

Use `curl` to send messages via the Telegram Bot API:

```bash
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${TELEGRAM_CHAT_ID}\", \"text\": \"YOUR_MESSAGE_HERE\", \"parse_mode\": \"Markdown\"}"
```

### Send Files/Documents

```bash
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
  -F "chat_id=${TELEGRAM_CHAT_ID}" \
  -F "document=@/path/to/file"
```

### Send Photos

```bash
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto" \
  -F "chat_id=${TELEGRAM_CHAT_ID}" \
  -F "photo=@/path/to/image.png" \
  -F "caption=Optional caption here"
```

## Before you send: honour the shared cooldown

The bridge daemon (M), mail-watch, devi-watch and every worker's curl all write to the ONE
owner chat with the ONE bot token, so they share Telegram's per-chat budget (about one message
per second, bursts tolerated, then `429 Too Many Requests` with a `retry_after` that on
2026-09-19 was 8687 seconds). The bridge publishes every 429 it sees to
`~/dev/claude-telegram-bridge/tg-throttle.json` as `{"until": <ms since epoch>, ...}`. Check it
first, and if the deadline is in the future do NOT send: say in your reply that Telegram is
throttling the bot until that time and leave the file where the owner can find it.

```bash
node -e 'const j=JSON.parse(require("fs").readFileSync(process.env.HOME+"/dev/claude-telegram-bridge/tg-throttle.json","utf8"));const left=(j.until-Date.now())/1000;if(left>0){console.log("THROTTLED until "+new Date(j.until).toLocaleTimeString()+" ("+Math.ceil(left/60)+"m left)");process.exit(3)}' 2>/dev/null || echo "clear to send"
```

If your own `curl` gets `"error_code":429`, publish it the same way so the others hold fire:
write `{"until": now_ms + (retry_after + 1) * 1000, "retryAfter": <n>, "method": "sendMessage",
"at": now_ms, "source": "worker"}` to that path (only if its `until` is later than what is
already there). Never retry into a 429, and never send more than one message per second.

## Guidelines

- Use `parse_mode: "Markdown"` for formatted text messages
- For long messages (>4096 chars), split into multiple messages
- When sending code snippets, wrap them in triple backticks in the message
- Tell the user the message was sent only after the API response shows `"ok":true`; otherwise report the `description` it returned
- If sending a file, verify the file exists before attempting to send
