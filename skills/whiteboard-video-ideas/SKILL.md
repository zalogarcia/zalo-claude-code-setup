---
name: whiteboard-video-ideas
description: Produce new whiteboard YouTube video ideas for Zalo Kabche's channel in two stages. Stage 1 picks topics from the owner question research and his demo data (skipping anything filmed or planned on Linear) and sends them as ONE Telegram text with Linear Idea cards. Stage 2, only for the ones he picks, writes beats.md, renders a gpt-image-2 board per pick on the photo of his real whiteboard, builds the filming plan PDF ("like last time"), sends it with the boards and moves the cards to Boards ready. Use when Zalo asks for more whiteboard video ideas, picks ideas to shoot, or wants the board or filming plan for a shoot. Not for editing footage (yt-video-edit), thumbnails (yt-thumbnail) or publishing (ship-yt-video).
---

Turns "send me N more video ideas" into a text he can pick from on his phone, then turns his picks into boards he can copy onto his real whiteboard and a filming plan PDF.

**Boards, beats folders, contact sheets and the PDF are never made for ideas he has not picked** (Zalo, 2026-10-02: "next time for the ideas, just send me the text of the 6 ideas here on telegram no need to create the whiteboard, once I pick the 3 ideas then you create the actual pdf with all stuf"). Stage 1 is text only, so do not render boards for all the ideas, however cheap it looks.

## Locked rules (Zalo's decisions, do not re-ask)

- **Audience:** seven figure plus business owners (home services, trades, clinics, legal) with no AI knowledge. Each video leaves them thinking "now I get it", because they want enough to decide and trust, not to build.
- **Goodwill first.** No pitch in the body. Every video ends with the AI demo CTA ("try our demo, link below"); the reel ends with "link in bio to try it".
- **Format:** he teaches at a physical whiteboard. Never propose screen share tutorials; that genre is saturated and deliberately not his.
- **Boards:** one image per board, on the photo of HIS board, numbered in draw order with small circled numbers, very visual, about 6 words max, outlines only. **Color key (locked 2026-09-24):** black = the business and structure, blue = the customer and the call, red = the problem or money lost, green = the fix or booked. An AI box is black because it is the business.
- **gpt-image-2 only** (`images.edit`), never nano-banana or Gemini.
- **No em or en dashes** in anything he reads: Telegram text, captions, beats, PDF. Check with `bash ~/.claude/scripts/dash-check.sh <files>`.
- **The PDF "like last time":** Letter pages, a cover (kicker, date, the shoot order with each reel after its long form, color key swatches, filming guide), then one page per video: kicker, title, hook, beats with circled step markers, close, the board cropped to the writing surface and printed large, a "Board:" caption, the draw order line and a boxed reel line. `scripts/build-pdf.py` renders exactly this; do not hand-build another layout.
- **Stats:** every number carries its source on the evidence line, and seller or vendor numbers are flagged as such. Counts of demo tests are not pass rates.

## Where things live (point at them, do not copy)

- Content root: `~/Documents/Zalo Content/Whiteboard YouTube/` (one `video-NN-<slug>/` folder per picked video).
- Research: `research-2026-09-24.md` there: 30 ranked owner questions with evidence, board idea, board words, a title and the demo bridge each, plus "Already covered to death" and "The gaps nobody explains simply".
- Board photo: `~/dev/claude-telegram-bridge/inbox/1790268071550_photo_18080.jpg` (the default in `gen-board.py`).
- Titles: `~/dev/zalo-kabche-brand/process/packaging/title-structures.md` (a proven pattern on the Formula line, 2 alt titles for the 3 title split test).
- Linear: `bash ~/.claude/scripts/linear.sh list whiteboard | status | comment | create` (ids in memory `linear-content-board.md`).
- Telegram: token `jq -r '.env.TELEGRAM_BOT_TOKEN // .TELEGRAM_BOT_TOKEN' ~/.claude/settings.local.json`, chat `$TELEGRAM_CHAT_ID` (else `jq -r '.env.TELEGRAM_CHAT_ID' ~/.claude/settings.local.json`). Pass text with `--data-urlencode "text@file"` and captions with `-F "caption=<file"`, because shell quoting mangles `$` and apostrophes. Parse each response with `printf '%s' "$r" | jq` and report the message ids.
- History and measured traps: memory `whiteboard-youtube-direction.md`. Scripts: `S=~/.claude/skills/whiteboard-video-ideas/scripts`.

## Stage 1: ideas, text only (the default when he asks for ideas)

1. **Inventory.** `bash ~/.claude/scripts/linear.sh list whiteboard` and `ls` the content root: every topic already filmed or planned, and the next free LF number. Read the research's ranked list and gaps section.
2. **Pick N topics** (6 unless he says otherwise) with variety, not N receptionist pricing videos. Favor his own demo and sales data, then the biggest search clusters. Per idea: title (proven pattern), hook (first 5 seconds), a one line why with counts and sources, and a reel headline.
3. **Spec.** Write `ideas-YYYY-MM-DD.json` in the content root with `kind`, `kicker`, `date_label`, `intro` and per video at least `num, code, title, hook, why` (or `why_short`, one line), `reel_headline`. Stage 2 fills in the rest for the picks only.
4. **Send ONE text message**, no images:
   ```bash
   python3 $S/ideas-message.py ideas-YYYY-MM-DD.json /tmp/ideas.txt --desc-dir /tmp/ideas-desc
   bash ~/.claude/scripts/dash-check.sh /tmp/ideas.txt
   ```
   It ends "Reply with 3 numbers to shoot."; add a line for any boards already waiting. It refuses a text over Telegram's 4096 character cap (exit 2): give the ideas a one line `why_short`.
5. **Linear Idea cards:** `linear.sh create whiteboard "LF7: <title>" /tmp/ideas-desc/LF7.md Idea` per idea.

## Stage 2: after he picks (only the picked ideas)

1. **Linear comment:** `linear.sh comment ABC-N "Picked by Zalo YYYY-MM-DD, shooting today"` for each pick. The rest stay in Idea.
2. **Complete the picks in the spec:** `folder, short, formula, alt_titles, research, beats[{t, s}], close, reel_idea, length, board_words, draw[{step, what, marker, during}], notes`, and later `board_note`. Optional `board` overrides `<folder>/board.png` (a path relative to the spec dir).
3. **Board prompts.** Copy `board-prompt-template.txt` per pick to `<folder>/board-prompt-attempt-1.txt` and `-2.txt`, filling LAYOUT, TEXT, COLORS and the FIT block's lowest element. Quote every word exactly and spell it letter by letter.
4. **Generate 2 attempts per board in parallel** in ONE foreground command (12 calls took 102 s on 2026-10-02):
   ```bash
   cd ~/Documents/Zalo\ Content/Whiteboard\ YouTube
   for d in video-07-x video-11-y; do for n in 1 2; do
     python3 $S/gen-board.py "$d/board-prompt-attempt-$n.txt" "$d/board-attempt-$n.png" > "/tmp/gb-$d-$n.log" 2>&1 &
   done; done; wait
   ```
5. **Audit every attempt.** Crop to the writing surface (`92,170,1152,890`), put the two attempts on one image and look. Every word must read exactly as quoted, with no extra text or glyph anywhere (icons included: a `$` once hid in a phone dial). Every circled number must be present, the bottom frame bar must be one unbroken bar with nothing on or below it, and the colors must follow the key. Copy the pass to `<folder>/board.png` and record the pick and the reject reasons in `board_note`. If both fail, regenerate at most twice, then simplify the layout or fix the prompt.
6. **Plan spec and build.** Write `filming-plan-YYYY-MM-DD.json` with `"kind": "plan"`, `kicker` "WHITEBOARD FILMING PLAN", the picks in the order he gave them:
   ```bash
   python3 $S/write-beats.py filming-plan-YYYY-MM-DD.json
   python3 $S/build-pdf.py filming-plan-YYYY-MM-DD.json filming-plan-YYYY-MM-DD.pdf
   mkdir -p /tmp/pdfcheck && pdftoppm -r 60 -png filming-plan-YYYY-MM-DD.pdf /tmp/pdfcheck/p   # look at EVERY page
   pdftotext filming-plan-YYYY-MM-DD.pdf /tmp/pdfcheck/t.txt && bash ~/.claude/scripts/dash-check.sh /tmp/pdfcheck/t.txt */beats.md
   ```
   Expect one page per pick plus the cover; a pick spilling onto 2 pages means its beats are too long.
7. **Telegram:** the PDF via sendDocument (caption like "Today's 3: #7, #11, #8. Filming plan with boards."), then each board as a photo captioned "#N Title".
8. **Linear status:** `linear.sh status ABC-N "Boards ready"` for each pick, only once its board passed the audit and was sent.

`contact-sheet.py <spec> <out.png> [--cols N]` exists for when he asks to see several boards at once; it is not part of either stage by default.

## Anti-patterns (each one happened)

- ❌ Rendering boards, a contact sheet and a PDF for all 6 ideas before he picked (2026-10-02). He wanted the text only, and 3 of the 6 boards were never used.
- ❌ Writing on or erasing the bottom frame bar, the most common board defect (4 of 8 in the first run, 3 of 12 on 2026-10-02). The template's FIT block exists for this; never drop it.
- ❌ Asking a fix pass to move several elements. Whole rows shift; for more than one element, re-run from the photo.
- ❌ A list of words without "aligned columns, the same left edge" in the prompt. The words drift out of column.
- ❌ Padding the photo to 2:3. The board frame broke. Use `size=1152x1536`.
- ❌ A vendor study told as proof, or correlation told as cause, in a beat. An outcomes-grader caught both; source every stat.
- ❌ A non streaming `images.edit`. The connection is cut at 60 s; `gen-board.py` streams.
- ❌ Waiting on headless Chrome to exit after `--print-to-pdf`. It writes the PDF and hangs; `build-pdf.py` kills it once the file size is stable. BSD `pkill` reads a pattern starting with `--` as an option, so match `user-data-dir=...` without the dashes.

## Pair with

- `yt-video-edit` to edit the footage (until that skill lands, `content-video-finish` is the editing rail), `yt-thumbnail` for the 3 thumbnails, `ship-yt-video` to publish.
- `telegram` skill for the send mechanics.
