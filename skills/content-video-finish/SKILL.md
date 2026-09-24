---
name: content-video-finish
description: 'Finish a video Zalo recorded himself: rough cut the raw take first (fillers, dead air, false starts and superseded retakes out, cut on Scribe word boundaries and self checked at every cut), then add the headline, prompt/template cards, karaoke captions and hook-variant splits, then gate it against the locked safe-zone and caption laws. Use when he hands over self-recorded footage and describes overlays, captions, a headline or hook variants, or asks to cut the ums, the pauses or the retakes. This is the AD-HOC rail; daily-reels-machine covers the nightly batch and course-lesson-video covers CMAA lessons, and neither fires here.'
---

Turn raw self-recorded phone footage into finished vertical content, built from the locked specs rather than from scratch, and prove it with a gate before delivering.

## When to invoke

- He drops footage in `~/Downloads` (or names a file) and describes what should be on screen
- "Add the prompts / the headline / the overlay text / the captions"
- "Make me N hooks so we can split test" then "attach them"
- Any re-cut of a video already delivered through this rail
- "Cut the ums / the pauses / the dead air / the retakes", or any raw take that has not been cut yet (Step 0)

Skip for: the nightly batch (`daily-reels-machine`), CMAA lesson videos
(`course-lesson-video`), branded motion-graphics slides (`machine-editorial-broll`),
AI-generated footage (`seedance`), and YouTube long-form packaging (`ship-yt-video`).

## Step 0: Rough cut the raw take. Before everything else.

Skip it only when the footage is already an edited export or he says it is cut. Otherwise
every raw take goes through it, and Steps 1 to 5 then run on `rough_cut.mp4`, never on the
raw file. The rough cut only removes material. It adds nothing on screen and never touches
the locked layout below.

- **Work folder** (the edit dir): `~/Documents/Zalo Content/<deliverable>/rough-cut/`.
  Never the skill folder, never next to the footage in `~/Downloads`.
- **Helpers:** `~/.claude/skills/content-video-finish/scripts/`, ported from
  browser-use/video-use (MIT) at commit `9575612`. Run every one with `arch -arm64 python3`.
  No numpy and no venv: the waveform is ffmpeg PCM plus PIL, because the system numpy on
  this Mac is an x86_64 build that will not import.

1. **Transcribe, cached.**
   `transcribe.py --edit-dir <dir> --language en --num-speakers 1 <take.mov> [<take2.mov> ...]`.
   `<take.mov>` is the file path; `<take>` alone, in the steps below, is that file's name
   without the extension, which is how the tools name the take. ElevenLabs Scribe, word
   level and verbatim (fillers kept), with speaker labels and audio events. Cached per
   source in `<dir>/transcripts/` with a size and mtime fingerprint: a rerun on the same
   file costs nothing, a changed file is re-transcribed, and two different files with the
   same name are refused before anything uploads. The key is `ELEVENLABS_API_KEY` (set
   in `~/.zshenv`), sent from a 0600 header file and never printed.
2. **Read the packed view.** `pack_transcripts.py --edit-dir <dir>` writes
   `takes_packed.md`: one phrase per line with its source `[start-end]`, then hints per take
   (fillers, cut-off words such as `has--` that mark a false start, word runs said twice
   within 20 s that mark a retake). Read it whole. For exact word times on a stretch:
   `rough_cut.py words <dir> <take> <start> <end>`.
3. **Decide what goes.** Standalone fillers (um, uh), audio events other than laughs, and
   dead air (a gap of 0.4 s or more) go automatically. False starts, slips, filler phrases
   ("you know") and superseded retakes are your call: pass each as
   `--drop '<take>:<start>-<end>:<why>'` in source seconds. A word goes when its midpoint
   falls inside the range, so the range does not have to be exact.
   - **Retakes:** when he repeats a line, keep the best delivery (every word clean, full
     energy, no stumble). When two are equal keep the LAST one, since he restarts until it
     lands. Name the take you kept and why in the report.
   - **Never drop a line he said once.** The rough cut removes fillers, dead air, false
     starts and superseded retakes, nothing else. Cutting content for length stays under
     the "Video runs long" edge case below: ask first.
   - **Most "repeated runs" hints are his parallel phrasing**, not retakes ("prompt right
     here" three times on IMG_4446 is the structure of the tip). Judge each one.
   - **Only drop where he paused.** If the words around a drop run together, the cut clips
     the next word (see the machine facts below). Keep the line instead.
4. **Plan.** `rough_cut.py plan --edit-dir <dir> --source <take.mov> [--source <take2.mov> ...] [--drop ...]`
   writes `edl.json` and prints what goes, the pauses it kept, the edges flagged for a
   drill-down, any loud stretch the transcript does not account for, and Scribe vs RMS
   timing on this take. Every range is snapped to whole frames of the rate render will use
   (the first take's, or `--fps`; pass the same `--fps` to both). Nothing renders. Look at
   every flagged edge with
   `timeline_view.py <take.mov> <start> <end> --transcript <dir>/transcripts/<take>.json --mark <t> -o <dir>/verify/<name>.png`.
5. **Render.** `rough_cut.py render --edit-dir <dir>` writes `rough_cut.mp4` (1080x1920,
   CRF 16, source frame rate), `cut_words.json` (every kept word on the OUTPUT timeline),
   `cuts.json`, and `render_report.json` (durations, frame count, A/V difference, loudness
   and true peak before and after). About 2 minutes for a 107 s 4K take.
6. **Self check the RENDER, not the source.** `rough_cut.py verify --edit-dir <dir>` draws a
   `timeline_view` PNG at every cut boundary of the rendered file (1.5 s either side) plus
   the head and the tail, and checks each boundary by number: a word across the cut,
   speech inside a fade, a dark or flash frame. Exit 1 means something flagged. Then LOOK
   at every PNG: each cut line must sit in a flat stretch of waveform with no word bar
   crossing it. Fix, re-plan, re-render: **3 re-renders at most**. Anything still failing
   after the third goes to Zalo by name; it is never shipped quietly.
7. **Report:** source vs cut duration, number of cuts, what went (fillers, dead air gaps,
   each drop and why), the retakes kept and why, any flag left, loudness and true peak.
   Review copy to Telegram as a document, per the `telegram` skill.

### Rough cut hard rules (from video-use; correctness, not taste)

1. **Never cut inside a word.** Every edge snaps to a Scribe word boundary, and `render`
   refuses an `edl.json` edge that lands inside a word.
2. **Pad every edge 30 to 200 ms** from its word: by default 50 ms before the first kept
   word and 80 ms after the last. Scribe drifts, so the padding absorbs it and the 10 ms RMS
   envelope decides where in that window the edge lands. The audio still wins, as in Step 3.
3. **A 30 ms audio fade at every segment edge**, in and out, or every cut pops.
4. **Extract each segment on its own, then concat losslessly with `-c copy`.** Never one big
   filtergraph. Segments are whole frames long and carry PCM audio, so sound and picture
   stay aligned across any number of cuts and the only AAC encode is the last one.
5. **Cut from word level verbatim ASR only.** Whisper segments and normalized fillers hide
   exactly what the rough cut has to remove.
6. **Cache transcripts per source.** Never re-transcribe an unchanged file.
7. **Time anything after the cut on the output timeline:**
   `output = word.start - segment.start + segment.offset`. `cut_words.json` already holds
   it. Source times are wrong after the first cut.
8. **The caption layer is composited LAST**, after the headline and every card, so no
   overlay can ever hide a caption.
9. **A video overlay (a screen recording, an animation) starts at its own frame 0:**
   `setpts=PTS-STARTPTS+T/TB`, with T the output time it appears.
10. **Nothing from a rough cut is written inside the skill folder.** Transcripts, renders and
    PNGs live in the deliverable's folder.

### Rough cut machine facts (measured on IMG_4446, 2026-09-24)

- **Trial:** 107.13 s raw body take to 87.21 s, 31 cuts, 28 dead air gaps, 3 drops (the
  false start "that has", the slip "to" in "and to create", the filler phrase "you know"),
  no retakes in that take. 2093 of 2093 frames, A/V difference 0.3 ms, 0 of 31 boundaries
  flagged on the third re-render. The QA pass after it then tightened `verify` to the full
  30 ms pad rule, which flags 1 of those 31 (cut 30: 20 ms before a trailing, quiet "the").
- **When he ran straight into a dropped word, the old fallback picked the quietest point
  from the word's own edge**, 0 to 20 ms away, inside the fade. The fallback now searches
  only the 30 to 200 ms window, and flags "pad rule cannot hold" when that window does not
  exist. On IMG_4446 the replayed plan moves the three such edges to 33, 32 and 40 ms after
  snapping to whole frames (0 of 64 edges outside the window).
- **A Scribe gap overstates the silence.** A drawn-out "work" left 0.13 s of real quiet
  inside a 0.42 s Scribe gap, so the first plan bought 130 ms with a jump cut. `plan` now
  keeps any gap the audio says is shorter than dead air (4 kept on that take).
- **A lone word between two cuts reads as a double jump cut** ("in", "at,"). `plan` keeps
  the pause on one side of any fragment shorter than 0.6 s (`--min-seg`).
- **Dropping words he ran together clips the next word.** "that's the one that's where"
  has no pause anywhere; dropping "that's the one" put speech inside the fade-in, `verify`
  flagged it, and the line was kept.
- **Scribe returned no "um" on this take** (scribe_v1 and scribe_v2 alike). `plan` lists
  every loud stretch with no transcript token, so a filler Scribe smoothed away cannot hide.
- **Scribe vs RMS on 45 clear word edges:** onsets median 50 ms late, p90 130 ms, max
  190 ms; offsets p90 130 ms, max 240 ms. Far closer than whisper's 1 to 2 s segment drift,
  but not a silence finder, so Step 3's RMS scan stays the arbiter for overlay timing.
- **The cut leaves loudness alone** (raw -23.0 LUFS and -1.8 dBTP, cut -22.9 and -1.9).
  Mastering is a later step; leave AAC headroom there.
- **HDR (HLG or PQ) takes are refused:** this ffmpeg has no zscale to tone map them.
- Timing on this Mac: transcription about 5 s, plan under 1 s, render about 2 min, verify
  about 1.5 min for a 107 s 4K HEVC take.

## Step 1: Read the specs. Do not hand-write a brief.

**This is the whole point of the skill.** The answers already exist in these
files; a brief written from scratch misses them.

| File | What it governs |
| --- | --- |
| `~/Documents/Zalo Content/Daily Machine/safe-zones.md` | **LAW.** Critical content box is **x 60-950, y 250-1560** on 1080x1920. Above 250 the IG handle/audio row and TikTok tabs cover it; below 1560 the caption/CTA/comment bar does; right of 950 the action rail does. |
| `~/Documents/Zalo Content/Daily Machine/signature-system.md` | Caption law. Futura. Chrome/bevel/emboss **banned**. Bouncing stroke-outlined captions **banned**. |
| `~/Documents/Zalo Content/Daily Machine/pipeline.md`, `caption-font-test/` | Existing treatments. Reuse, do not reinvent. |

If a request contradicts a spec, say so and ask. Do not silently override a law
file. When he DOES override a spec, record the date and his exact wording.

## Step 2: The locked layout

- **Headline:** inside the safe box (top edge >= 250), **big**, and it
  **disappears after about 5 seconds**. It is NOT a persistent bar.
  (Zalo 2026-08-17: "the headline needs to be lower and disappear after 5
  seconds. Needs to be in a safe zone and be bigger.")
- **Karaoke captions (his spoken words): DEAD CENTRE of the frame.** Cap-centre
  **y = 960** (1920 / 2), horizontally centred at x = 540. **Nothing dark behind
  them**: no bar, no plate, no band; the soft blur shadow is the only dark
  element allowed, and if it reads as a horizontal smear at 1:1 it gets tightened
  until it does not. 1 to 2 words per chip, **locked silver** v4.1 treatment from
  `signature-system.md`, never recoloured. (Zalo 2026-08-17: "Kareoke captions
  need to be centered in the video vertically and horizontally and no black line
  behind it" · earlier the same day: "the silver ones are fine for the captions
  themselves when I'm talking.")
- **Prompt / template / overlay cards: ABOVE and TO THE SIDE of the captions**:
  the upper-left block on his living-room footage: x 60 to his silhouette edge,
  top y 310, **bottom derived per card from its own window profile** (shipped
  bottoms ranged 533 to 847: a blanket 870 is unusable, see the shoulder note
  below). **Measure the silhouette per window**
  (`card_right = min(silhouette_left - 30, 950)`); never assume. **There is no
  usable top-band fallback** -- see the measurement below; fit long cards by
  growing the side block DOWN (its own window's shoulder line, not a global
  bottom) and letting the line count run past 6. (Zalo 2026-08-17: "the
  other overlay texts need to be above to the side of it like where my finger
  points at times.") Centre belongs to the captions.
- **Burgundy is for the ATTENTION FURNITURE, not the captions:** the headline
  and any overlay/callout text. (Zalo 2026-08-17: "the burgundy background it's
  for the headline and like stuff we're gonna put like overlay text... that
  could be to call the attention.") Two distinct roles, do not merge them:
  silver = what he is saying, burgundy = what you want them to look at.
- Cards must not cover his face. Sample real frames to place them; never assume.

## Step 3: Timing comes from the audio, never from whisper segments

Derive every overlay in/out with a **50ms RMS scan** for the nearest inter-word
silence. Whisper segment boundaries are coarse blocks 1 to 2 seconds off true
word positions, and on a clip with three near-identical takes they drifted
**1.4 seconds**, which would have cut a hook mid-sentence.

**If he references something on screen, it must be visible at that moment.**
"This prompt right here", "this is what you get", "look at this": a
referenced-but-unshown asset is a defect, not a nice-to-have. Check every
deictic phrase in the transcript against the overlay schedule.

## Step 4: Hook variants

Render the body **ONCE** with the shared overlays, then attach each hook to a
copy. Never render N full versions: it wastes compute and the variants drift
apart. Keep everything after the hook identical or the split test measures
nothing.

Trim each hook with an RMS scan at both edges. Multi-take clips: isolate the
good take, do not trust the whisper timestamps.

## Step 5: THE GATE. Mandatory, every deliverable.

```bash
arch -arm64 python3 ~/.claude/scripts/check-reel-safe-zones.py <file> --frames 12
```

Exit 0 required. It samples frames, finds hard overlay edges, and fails anything
critical outside y 250-1560.

**Never weaken the script to make a video pass.** If it fires, move the overlay.

Then the **read-back text audit**: sample a frame inside every overlay window,
read the rendered text, compare character by character against the source
strings. On-screen text is user-visible text. **No em dashes, any channel.**

## Output shape

One line per variant: path, duration, dimensions, gate result. Then the overlay
schedule (what appears when, and the spoken line it lands on). Report any spec
conflict you hit. Never paste full ffmpeg logs.

## Anti-patterns

- ❌ **Writing the brief from scratch.** The specs exist. This is the failure the skill was created to stop.
- ❌ **A persistent headline bar.** It disappears at ~5s.
- ❌ **Any dark bar/plate/band behind the captions.** See the seam-band trap below.
- ❌ **Captions anywhere but dead centre**, and ❌ **cards in the centre or the lower third.** Cards go above and to the side.
- ❌ **Shipping without captions** because the request did not mention them. They are the standing law.
- ❌ **Burgundy captions.** Burgundy is headline and overlay furniture only; his spoken captions stay silver.
- ❌ **Overlay timing from whisper segments.** RMS scan or it drifts.
- ❌ **Editing the gate script** so a bad render passes.
- ❌ **Overwriting source footage.** A prior project lost a master this way. Write new files only.
- ❌ **Rendering each variant end to end.** Body once, then attach hooks.

## Machine facts (measured, save the rediscovery)

- **THE SEAM-BAND TRAP.** The shared chip renderer carries a *seam-cover band*:
  a ~20px black rounded bar at 75% opacity, drawn the full text width plus 28px
  each side, right through the caption's cap centre
  (`BAND_PAD_X, BAND_HALF_H, BAND_R, BAND_BLUR, BAND_ALPHA = 28, 10, 10, 6, 191`).
  It is **correct in the batch split layout**, where the comp pane and avatar
  pane meet at y=958 and the band hides the seam. **On full-bleed talking-head
  footage there is no seam, so it is pure cruft and renders as the "black line
  behind the captions" Zalo rejected on 2026-08-17.** Strip it on this rail;
  never delete it globally or you break `daily-reels-machine`.
- **THE TOP-BAND FALLBACK DOES NOT EXIST.** The obvious rescue for a card too
  long for the side block -- "put it in the full-width band x 130-950, y 250-470"
  -- is geometrically impossible and must not be planned around. That band is
  220px tall; measured at cap 30 (the legibility floor) the AI-slop card needs
  **281px** and the GAP prompt needs **238px**. It cannot be made taller either:
  its bottom is pinned by his hair-top (~470-490 on this footage). Long cards go
  in the SIDE block, grown downward. (2026-08-17: the v3 brief specified this
  fallback for two cards; both were measured impossible before rendering.)
- **The side block's right edge VANISHES for short cards.** `min(silhouette_x)`
  over only the rows the card actually spans returns "no constraint" once the
  box clears his hair-top (~470), so a 2-line card silently widens into a
  full-width top banner. Probe the silhouette down to at least `head_top + 120`
  regardless of how short the card is, or it stops being a side card.
- **His shoulder, not his head, is the binding constraint below y~800.** Head
  left edge sits ~484-568; the shoulder cuts in to **x 304**. A card bottom of
  870 costs ~200px of width versus a bottom of 780. Derive the bottom per card
  from that card's own window profile.
- **`-c:a aac` alone does NOT make an audio-only file.** Writing `.m4a` from a
  4K source without `-vn -map 0:a:0` makes the mp4-family muxer pick up the
  video stream too and re-encode it: measured **202MB and climbing** for what
  should be a 2.5MB audio file, and it is the reason a 5-variant assemble ran
  past 10 minutes. The `filter_complex` branches escaped this because they
  carried `-map [a]`.
- **A shared segment is only byte-identical if it is a SEPARATE encode.** Any
  per-variant overlay at the head of a segment (the headline tail) perturbs
  x264 state for that whole segment: measured 250 of 348 frames differing while
  visually identical. Split it -- `A_v + Bh_v (the tail window) + Br (shared) +
  C (shared)` -- and the shared part concatenates byte-for-byte. On the
  2026-08-17 cut that took the identical body from 87.0s to **99.5s of 105s**.
- **Do not pass `-shortest` when the streams already match by construction.**
  With `-c copy` and B-frames it silently dropped the last 3 video frames on 2
  of 5 variants.
- **PIL needs `arch -arm64 python3`.** The shell reports x86_64 under Rosetta but the wheel is arm64-only; `/usr/bin/python3` has no PIL.
- **iPhone footage is 3840x2160 with `rotation=90`** in metadata, so it displays vertical. Do not "fix" the dimensions.
- **Black bars in a Telegram screenshot are the viewer, not the file.** Probe the actual file before treating them as letterbox.
- **This ffmpeg has no `drawtext` filter.** Text is PIL-rendered and composited.
- `format=yuv420p` alone RELABELS full range; the correct filter is `scale=in_range=full:out_range=limited,format=yuv420p`, and only when the source is actually full range.

## Edge cases

- **He asks for something a law file forbids**: surface the conflict, get his call, and if he overrides, record the date and his wording in this file.
- **A hook take is unusable**: say so and use the next best, do not silently pad the count.
- **Video runs long** (his measured target is ~63s, median winner 50s): flag it, do not trim his spoken content without asking.

## Pair with

- `daily-reels-machine`: the nightly batch rail; shares these specs and this gate
- `~/.claude/scripts/check-reel-safe-zones.py`: the gate itself, shared across both rails
- `telegram`: send a review proxy; the bot cannot send over 50MB, so hand over a path or a downscaled proxy
