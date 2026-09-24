---
name: content-video-finish
description: 'Finish a video Zalo recorded himself: add the headline, prompt/template cards, karaoke captions and hook-variant splits, then gate it against the locked safe-zone and caption laws. Use when he hands over self-recorded footage and describes overlays, captions, a headline or hook variants. This is the AD-HOC rail; daily-reels-machine covers the nightly batch and course-lesson-video covers CMAA lessons, and neither fires here.'
---

Turn raw self-recorded phone footage into finished vertical content, built from the locked specs rather than from scratch, and prove it with a gate before delivering.

## When to invoke

- He drops footage in `~/Downloads` (or names a file) and describes what should be on screen
- "Add the prompts / the headline / the overlay text / the captions"
- "Make me N hooks so we can split test" then "attach them"
- Any re-cut of a video already delivered through this rail

Skip for: the nightly batch (`daily-reels-machine`), CMAA lesson videos
(`course-lesson-video`), branded motion-graphics slides (`machine-editorial-broll`),
AI-generated footage (`seedance`), and YouTube long-form packaging (`ship-yt-video`).

## Step 1 — Read the specs. Do not hand-write a brief.

**This is the whole point of the skill.** The answers already exist in these
files; a brief written from scratch misses them.

| File | What it governs |
| --- | --- |
| `~/Documents/Zalo Content/Daily Machine/safe-zones.md` | **LAW.** Critical content box is **x 60-950, y 250-1560** on 1080x1920. Above 250 the IG handle/audio row and TikTok tabs cover it; below 1560 the caption/CTA/comment bar does; right of 950 the action rail does. |
| `~/Documents/Zalo Content/Daily Machine/signature-system.md` | Caption law. Futura. Chrome/bevel/emboss **banned**. Bouncing stroke-outlined captions **banned**. |
| `~/Documents/Zalo Content/Daily Machine/pipeline.md`, `caption-font-test/` | Existing treatments. Reuse, do not reinvent. |

If a request contradicts a spec, say so and ask. Do not silently override a law
file. When he DOES override a spec, record the date and his exact wording.

## Step 2 — The locked layout

- **Headline:** inside the safe box (top edge >= 250), **big**, and it
  **disappears after about 5 seconds**. It is NOT a persistent bar.
  (Zalo 2026-08-17: "the headline needs to be lower and disappear after 5
  seconds. Needs to be in a safe zone and be bigger.")
- **Karaoke captions (his spoken words): DEAD CENTRE of the frame.** Cap-centre
  **y = 960** (1920 / 2), horizontally centred at x = 540. **Nothing dark behind
  them** — no bar, no plate, no band; the soft blur shadow is the only dark
  element allowed, and if it reads as a horizontal smear at 1:1 it gets tightened
  until it does not. 1 to 2 words per chip, **locked silver** v4.1 treatment from
  `signature-system.md`, never recoloured. (Zalo 2026-08-17: "Kareoke captions
  need to be centered in the video vertically and horizontally and no black line
  behind it" · earlier the same day: "the silver ones are fine for the captions
  themselves when I'm talking.")
- **Prompt / template / overlay cards: ABOVE and TO THE SIDE of the captions** —
  the upper-left block on his living-room footage: x 60 to his silhouette edge,
  top y 310, **bottom derived per card from its own window profile** (shipped
  bottoms ranged 533 to 847 — a blanket 870 is unusable, see the shoulder note
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

## Step 3 — Timing comes from the audio, never from whisper segments

Derive every overlay in/out with a **50ms RMS scan** for the nearest inter-word
silence. Whisper segment boundaries are coarse blocks 1 to 2 seconds off true
word positions, and on a clip with three near-identical takes they drifted
**1.4 seconds**, which would have cut a hook mid-sentence.

**If he references something on screen, it must be visible at that moment.**
"This prompt right here", "this is what you get", "look at this" — a
referenced-but-unshown asset is a defect, not a nice-to-have. Check every
deictic phrase in the transcript against the overlay schedule.

## Step 4 — Hook variants

Render the body **ONCE** with the shared overlays, then attach each hook to a
copy. Never render N full versions: it wastes compute and the variants drift
apart. Keep everything after the hook identical or the split test measures
nothing.

Trim each hook with an RMS scan at both edges. Multi-take clips: isolate the
good take, do not trust the whisper timestamps.

## Step 5 — THE GATE. Mandatory, every deliverable.

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

- **THE SEAM-BAND TRAP.** The shared chip renderer carries a *seam-cover band* —
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

- **He asks for something a law file forbids** — surface the conflict, get his call, and if he overrides, record the date and his wording in this file.
- **A hook take is unusable** — say so and use the next best, do not silently pad the count.
- **Video runs long** (his measured target is ~63s, median winner 50s) — flag it, do not trim his spoken content without asking.

## Pair with

- `daily-reels-machine` — the nightly batch rail; shares these specs and this gate
- `~/.claude/scripts/check-reel-safe-zones.py` — the gate itself, shared across both rails
- `telegram` — send a review proxy; the bot cannot send over 50MB, so hand over a path or a downscaled proxy
