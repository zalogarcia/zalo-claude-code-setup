---
name: telegram
description: Send messages, files, images, or documents to the user via their Telegram bot. Use when the user asks to send something to Telegram, notify them, or share content via Telegram.
---

Send content to the user's Telegram bot using the Telegram Bot API.

## Configuration

Secrets are stored in environment variables (configured in `~/.claude/settings.local.json`):

- **Bot Token:** `$TELEGRAM_BOT_TOKEN`
- **Chat ID:** `$TELEGRAM_CHAT_ID`
- **Bot Username:** @YOUR_BOT_USERNAME (set this to your bot's username)

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

## Guidelines

- Use `parse_mode: "Markdown"` for formatted text messages
- For long messages (>4096 chars), split into multiple messages
- When sending code snippets, wrap them in triple backticks in the message
- Always confirm to the user that the message was sent successfully
- If sending a file, verify the file exists before attempting to send
