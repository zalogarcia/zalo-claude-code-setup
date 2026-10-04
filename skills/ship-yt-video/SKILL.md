---
name: ship-yt-video
description: End-to-end checklist for shipping a Zalo Kabche long-form YouTube video so no packaging or publish step gets skipped — edit-quality pass, a 3-TITLE split test pulled from the title-structures database, a 3-thumbnail split test (yt-thumbnail skill), a chapters-timed description, the correct upload path (Studio direct for long-form — Post for Me chokes on it), and the Studio upload, setup and publish through COMPUTER USE (computer-use.sh, Zalo's rule 2026-10-03). Use when the user says "ship the youtube video", "publish the video to youtube", "upload the long-form video", "put the video on youtube", or is finishing any video in ~/dev/zalo-kabche-brand. Replaces ad-hoc uploads that miss the title database, mistime chapters, or push a 45-min file through a pipeline that can't take it.
---

The one authority for putting a finished Zalo Kabche long-form video on YouTube. Runs the full pipeline as a gated checklist (packaging with 3 titles + 3 thumbnails, description, upload, Studio setup) so no video ships with a plain title, mistimed chapters, or a failed upload.

## When to invoke

- User says "ship / publish / upload the YouTube video", "put it on YouTube", "finish the upload"
- The Publish stage (stage 6) of any `videos/NN-slug.md` in `~/dev/zalo-kabche-brand`
- Any time a long-form (>~15 min) video is edit-final and headed to the channel

Skip for: short-form / reels (those CAN go via Post for Me / Zalo OS — see `~/dev/zalo-os`); channel art; thumbnails alone (`yt-thumbnail`); b-roll (`machine-editorial-broll`).

## Prerequisites

- The video is **edit-final** and exported to `~/Documents/Zalo Content/<deliverable>/` (content-location rule).
- Channel: **Zalo Kabche** (`UCd-Xqhtu5vP7UCdW8p6vgmw`), 2.8K subs. Logged into YouTube Studio in Zalo's normal Chrome (Default profile).
- **Upload rail = computer use (Zalo's rule, 2026-10-03: "when I ask you to post a youtube video you need to use the computer use").** `~/.claude/scripts/computer-use.sh "<task>"` (GPT-6.1 Sol through Codex Computer Use) drives his real Chrome: it picks the file in the macOS file dialog, so the 10 MB browser upload cap does not apply and nobody hands the file over. Google Chrome (`com.google.Chrome`) is on the computer use allow list since 2026-10-03 (only Zalo edits that list). Do not fall back to Claude-in-Chrome or ask him to drop the file unless computer use is down (exit 3) and he says so.
- Source docs (read at packaging time): `~/dev/zalo-kabche-brand/process/packaging/title-structures.md` (THE title database), `process/packaging/thumbnail-formats.md`, `design/visual-spec.md`.

## Phase 0 — Edit-quality pass (BEFORE anything else)

Never stitch-and-ship. Run the silence/retake pass (`feedback_video_edit_checklist`):

- Detect silences: `ffmpeg -i in.mp4 -af silencedetect=noise=-35dB:d=0.5 -f null -`.
- **Trim** leading/trailing dead air (video opens on the first word, not a beat of silence).
- **Distinguish** real dead air (trim) from intentional holds (chapter/section breathers — keep) and silent screen-recording demos (keep — cutting them breaks the lesson). Extract a frame at each long silence to tell which it is.
- Re-verify duration + a few frames after any trim.

## Phase 1 — Packaging: two split tests of three (NEVER skip)

Packaging is Zalo's declared weakest skill and the stage most likely to be shortcut. Both halves are **split tests of 3**, not one-and-done.

### 1a. Three titles from the database

Run every video through `process/packaging/title-structures.md`. Never ship a plain descriptive title ("X (Full Course)"): it matches no proven pattern, which is exactly what the database exists to prevent.

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
- **Chapters**: `0:00` first, ≥3, ≥10s apart, in order. **Compute timestamps from the FINAL cut**, not the raw edit: if an intro was prepended, every module/section offset shifts by the intro length. Measure the divider positions plus the intro offset.
- **What you'll learn** bullets; **CTA** (subscribe + one comment prompt — generic/evergreen, no next-video teaser); **hashtags**.
- Verify special chars typed clean (middot ·) and that the description carries no em or en dashes (none in Zalo's copy, any channel); avoid `@` (triggers a mention dropdown).

## Phase 3 — Upload (long-form goes DIRECT to Studio)

**Post for Me / Zalo OS CANNOT upload long-form.** Proven 2026-07-15: a 272 MB / 45-min file uploads to PFM storage complete and valid, then PFM's media processor fails it — `"All media failed to process"` — twice, deterministically. PFM is short-form only.

- **Long-form: upload DIRECTLY in YouTube Studio through computer use.** One small `computer-use.sh` task per call, each under 10 minutes, and a `screencapture -x` you LOOK at after each: (1) Studio open on channel `UCd-Xqhtu5vP7UCdW8p6vgmw`; (2) Create, Upload videos, macOS file dialog, Cmd+Shift+G, the full path; (3) title, description (`pbcopy` it first), not made for kids; (4) Private, Save, record the video id. Every task text says: only the Studio tab, touch no other tab or app, no sign in or out, no channel setting, never Public or Unlisted unless this is the publish step, stop on any password, keychain or 2FA prompt.
- **Trap, the Blueprint Chrome (proven 2026-10-03):** while the GHL Blueprint Chrome (`--remote-debugging-port=9222`) runs, computer use attaches to it instead of his normal Chrome and fails with `-10005 timeoutReached`. Before the upload: check `bg.mjs ps` shows no GHL job and `lsof -nP -iTCP:9222 -sTCP:ESTABLISHED` shows no client, then SIGTERM that exact pid (never by name). After the upload, ALWAYS relaunch it with the command in memory `blueprint-chrome-cdp-rail.md` and check `/json/version` on 9222. Never load a page in it.
- **Trap, the clipboard encoding (LF1, 2026-10-03):** a headless worker has no `LANG`, so `pbcopy` reads the UTF-8 description as Mac Roman and every middot "·" lands in Studio as "¬∑". A `pbpaste` round trip converts back the same wrong way and hides it. Copy with `LANG=en_US.UTF-8 pbcopy < file`, then check with `osascript -e 'get the clipboard'` that it equals the file before the paste step.
- **Small traps:** a Chrome extension bubble (for example "Devi is disabled") may sit over Studio: close it with its X only, never Accept or Remove. Computer use scrolling in Studio can fail with `-10005 windowNotFoundAtPosition`; clicks and typing still work, so read state from your own screenshot instead.
- **Upload as PRIVATE.** Nothing goes public until packaging is locked and the user OKs it.
- (Short-form clips only: the Zalo OS publish rail / Post for Me is fine.)

## Phase 4: Studio setup (computer use)

Once the file is ingesting, computer use drives the rest in the same Studio tab (screenshot each step):

1. **Title** — the chosen lead from the 3.
2. **Description** — paste the Phase-2 text; dismiss the hashtag autocomplete (Escape).
3. **Made for kids** — "No, it's not made for kids" (required field).
4. **Thumbnail / Test & Compare** — custom thumbnails read **"Ineligible" until processing finishes**; wait for processing, then set up **Test & Compare** (A/B) with the 3 thumbnails (each 1280×720, ≤2 MB). Confirm the channel's Test & Compare eligibility (this channel has it).
5. **Visibility** — leave **Private** (or Unlisted for review). Do NOT publish.

## Phase 5 — Publish gate (explicit OK only)

Keep it Private/Unlisted until: 3 thumbnails loaded into Test & Compare, lead title set, description + chapters verified. **Publish public only on the user's explicit "publish / go live."** Never auto-publish a video to the live channel. On his word, computer use sets Visibility to Public in the same Studio tab (the Blueprint Chrome trap above applies again), then prove it from outside: `curl -s -o /dev/null -w '%{http_code}' 'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=<id>&format=json'` gives 200 when public (401 or 404 while private). First run on this rail: LF1, video `4XfCNwmYeiw`, 2026-10-03.

## Phase 6 — Post-ship (the waterfall)

- Log the ship + chosen title/thumbnail into `videos/NN-slug.md` §2 and (day-11) `process/multiplier-log.csv`.
- Land the final in `~/dev/videos`: `~/.claude/scripts/video-library-add.sh zalo-kabche youtube "YYYY-MM-DD slug" <final> --cover <thumb 1> --cover <thumb 2> --cover <thumb 3> --text "description.txt=<deliverable>/YouTube Description.txt" --status posted:youtube:<date>` (APFS clones, no extra disk; the deliverable folder stays the working copy).
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
