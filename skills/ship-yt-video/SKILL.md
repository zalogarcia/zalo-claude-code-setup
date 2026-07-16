---
name: ship-yt-video
description: End-to-end checklist for shipping a Zalo Kabche long-form YouTube video so no packaging or publish step gets skipped — edit-quality pass, a 3-TITLE split test pulled from the title-structures database, a 3-thumbnail split test (yt-thumbnail skill), a chapters-timed description, the correct upload path (Studio direct for long-form — Post for Me chokes on it), and the Claude-in-Chrome Studio setup. Use when the user says "ship the youtube video", "publish the video to youtube", "upload the long-form video", "put the video on youtube", or is finishing any video in ~/dev/zalo-kabche-brand. Replaces ad-hoc uploads that miss the title database, mistime chapters, or push a 45-min file through a pipeline that can't take it.
---

The one authority for putting a finished Zalo Kabche long-form video on YouTube. Runs the full pipeline as a gated checklist — packaging (3 titles + 3 thumbnails), description, upload, Studio setup — so we never again ship with a plain title, mistimed chapters, or a failed upload. (Born 2026-07-15 from the Master Any AI ship, which missed the title database and burned an hour on a Post for Me upload that can't handle long-form.)

## When to invoke

- User says "ship / publish / upload the YouTube video", "put it on YouTube", "finish the upload"
- The Publish stage (stage 6) of any `videos/NN-slug.md` in `~/dev/zalo-kabche-brand`
- Any time a long-form (>~15 min) video is edit-final and headed to the channel

Skip for: short-form / reels (those CAN go via Post for Me / Zalo OS — see `~/dev/zalo-os`); channel art; thumbnails alone (`yt-thumbnail`); b-roll (`machine-editorial-broll`).

## Prerequisites

- The video is **edit-final** and exported to `~/Documents/Zalo Content/<deliverable>/` (content-location rule).
- Channel: **Zalo Kabche** (`UCd-Xqhtu5vP7UCdW8p6vgmw`), 2.8K subs. Logged into YouTube Studio in Chrome (Claude-in-Chrome extension connected).
- Source docs (read at packaging time): `~/dev/zalo-kabche-brand/process/packaging/title-structures.md` (THE title database), `process/packaging/thumbnail-formats.md`, `design/visual-spec.md`.

## Phase 0 — Edit-quality pass (BEFORE anything else)

Never stitch-and-ship. Run the silence/retake pass (`feedback_video_edit_checklist`):

- Detect silences: `ffmpeg -i in.mp4 -af silencedetect=noise=-35dB:d=0.5 -f null -`.
- **Trim** leading/trailing dead air (video opens on the first word, not a beat of silence).
- **Distinguish** real dead air (trim) from intentional holds (chapter/section breathers — keep) and silent screen-recording demos (keep — cutting them breaks the lesson). Extract a frame at each long silence to tell which it is.
- Re-verify duration + a few frames after any trim.

## Phase 1 — Packaging: two split tests of three (NEVER skip)

Packaging is Zalo's declared weakest skill and the stage most likely to be shortcut. Both halves are **split tests of 3**, not one-and-done.

### 1a. THREE titles — from the database (the step missed on 2026-07-15)

**MANDATORY: run every video through `process/packaging/title-structures.md`.** Do NOT write a plain descriptive title ("X (Full Course)") — that matches no proven pattern and is exactly what the database exists to prevent.

1. Classify the video's bucket: belief-breaker/contrarian · proof & math · method & how · test & review · story/journey · wound-first.
2. Pick **3 different proven patterns** that fit, and write one title each — carry each pattern's trending proof number (e.g. "Give Me [Duration] and I'll [Outcome]" — 2.0M/mo).
3. Each title must: **complement the thumbnail text** (never repeat it), pass the **fakeness filter** (curiosity yes, manufactured drama no), and stay **evergreen** (no dated/urgency claims — runtime durations like "45 minutes" are fine).
4. Present the 3 with their pattern + proof; recommend the lead. These are the split-test set.

**Testing mechanism honesty:** YouTube has **no native title A/B** (Test & Compare is thumbnails only). So the "3-title split test" means: generate 3 DB-backed candidates → launch with the strongest → rotate manually over the first weeks if the multiplier underperforms (or use a third-party title tester). The discipline is producing 3 from the DB, never shipping the first thing typed.

### 1b. THREE thumbnails — the `yt-thumbnail` skill

Invoke **`yt-thumbnail`** for the 3-concept split-test set (4-axis diversity + wardrobe rotation + lineup test, gpt-image-2 only). These go into YouTube **Test & Compare** at Studio setup.

## Phase 2 — Description (chapters timed to the FINAL cut)

Write the YouTube description; save to the deliverable folder as `YouTube Description.txt`.

- **Hook** in the first ~2 lines (shown before "…more"); brand voice, no hype.
- **Chapters** — `0:00` first, ≥3, ≥10s apart, in order. **Compute timestamps from the FINAL cut**, not the raw edit: if an intro was prepended, every module/section offset shifts by the intro length. (Missed-adjacent risk on 2026-07-15 — got this right by measuring divider positions + intro offset.)
- **What you'll learn** bullets; **CTA** (subscribe + one comment prompt — generic/evergreen, no next-video teaser); **hashtags**.
- Verify special chars typed clean (em dash —, middot ·); avoid `@` (triggers a mention dropdown).

## Phase 3 — Upload (long-form goes DIRECT to Studio)

**Post for Me / Zalo OS CANNOT upload long-form.** Proven 2026-07-15: a 272 MB / 45-min file uploads to PFM storage complete and valid, then PFM's media processor fails it — `"All media failed to process"` — twice, deterministically. PFM is short-form only.

- **Long-form (>15 min or >~200 MB): upload DIRECTLY in YouTube Studio.** Claude opens Create → Upload videos via Chrome, but **the human drops the file** — the browser `file_upload` tool caps at 10 MB, so Claude physically cannot push the video. Hand off that one action.
- **Upload as PRIVATE.** Nothing goes public until packaging is locked and the user OKs it.
- (Short-form clips only: the Zalo OS publish rail / Post for Me is fine.)

## Phase 4 — Studio setup (Claude in Chrome)

Once the human has dropped the file and it's ingesting, Claude drives the rest (GIF-record it):

1. **Title** — the chosen lead from the 3.
2. **Description** — paste the Phase-2 text; dismiss the hashtag autocomplete (Escape).
3. **Made for kids** — "No, it's not made for kids" (required field).
4. **Thumbnail / Test & Compare** — custom thumbnails read **"Ineligible" until processing finishes**; wait for processing, then set up **Test & Compare** (A/B) with the 3 thumbnails (each 1280×720, ≤2 MB). Confirm the channel's Test & Compare eligibility (this channel has it).
5. **Visibility** — leave **Private** (or Unlisted for review). Do NOT publish.

## Phase 5 — Publish gate (explicit OK only)

Keep it Private/Unlisted until: 3 thumbnails loaded into Test & Compare, lead title set, description + chapters verified. **Publish public only on the user's explicit "publish / go live."** Never auto-publish a video to the live channel.

## Phase 6 — Post-ship (the waterfall)

- Log the ship + chosen title/thumbnail into `videos/NN-slug.md` §2 and (day-11) `process/multiplier-log.csv`.
- Run the reels waterfall (`process/reels-pipeline.md`): mine 5-8 golden moments, batch the month's reels.
- When Test & Compare concludes, log the winning thumbnail as an `OWN TEST` row in the thumbnail outliers table.

## Output shape

Report per phase with evidence: edit-pass result (silences trimmed / kept-as-demo), the 3 titles with patterns+proof and the lead, the 3 thumbnails (lineup pass), description saved (path), upload status (Studio video link + Private), Test & Compare set. Never "shipped it" without the per-phase checklist.

## Anti-patterns (every one is a real miss)

- ❌ Writing a plain descriptive title without running the 3-title split from `title-structures.md` (the 2026-07-15 miss — "Master Any AI (Full Course)" matched no pattern)
- ❌ Uploading a long-form video through Post for Me / Zalo OS — it fails on large files; Studio direct only
- ❌ Timing chapters to the raw edit instead of the final cut (intro offset ignored)
- ❌ Skipping the edit-quality silence/retake pass — stitch-and-ship
- ❌ Trimming a silent screen-recording demo thinking it's dead air (breaks the lesson)
- ❌ Publishing public before the 3 thumbnails + lead title are set and the user OKs
- ❌ One title / one thumbnail — packaging is always a split test of 3

## Pair with

- `yt-thumbnail` — the 3-thumbnail split-test set (Phase 1b)
- `machine-editorial-broll` — b-roll / intro / module dividers used in the edit
- `commit-with-heredoc` — commit the packaging artifacts to the brand repo
- Brand repo `process/youtube-pipeline.md` — the surrounding stages this skill executes (stage 6)
