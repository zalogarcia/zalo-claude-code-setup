---
name: yt-thumbnail
description: Generate Zalo Kabche YouTube thumbnails (1280×720) from the locked Shop Manual '74 spec using real reference photos of Zalo, via the image-craft-expert agent on the gpt-image-2 `images.edit` rail (OpenAI — the standing preference, NOT nano-banana), with a mandatory text + face-identity audit and the 120px squint test. Use when the user says "make the thumbnail", "thumbnail comps for video N", "thumbnail options", or at the packaging stage of any video in ~/dev/zalo-kabche-brand. Encodes the photo-real vs manual-page precedence rule, the ≤4-word / one-orange-word text budget, and the stamp-never-lies guardrail. Replaces one-line "make a thumbnail" prompts that garble text, drift the face, and violate the brand spec.
---

Turn a video's packaging (title direction + pattern) into a **3-concept split-test set** with Zalo's real face — format decision → 3 concept-diverse prompts with spec tokens → parallel gpt-image-2 dispatches via `image-craft-expert` → text + identity audit → crop to 1280×720 → YouTube Test & Compare → winner logged back into the database.

**Rail: gpt-image-2 (OpenAI) ONLY.** Zalo's standing preference (2026-07-15) — always gpt-image-2 `images.edit`, never nano-banana. The Gemini/nano-banana rail is retired for this workflow; do not dispatch it, do not fall back to it, do not ask about it.

## When to invoke

- Packaging stage (stage 2/3) of any video in `~/dev/zalo-kabche-brand/videos/`
- User says "thumbnail(s) for video N", "thumbnail comps", "make the thumbnail"
- Refreshing a thumbnail after day-11 multiplier data (20% iteration tests)

Skip for: reel cover frames (reel template in `design/visual-spec.md` §6, different geometry), b-roll slides (`machine-editorial-broll`), infographics (`infographics` skill), channel art (one-off, template in spec §6).

## Prerequisites

- `OPENAI_API_KEY` set (gpt-image-2 rail — the ONLY rail). Missing → `checkpoint:human-action`. `GEMINI_API_KEY` / nano-banana is NOT used (Zalo's standing preference) — never require, test, or dispatch it.
- Authoritative source docs (read before assembling prompts if not already in context):
  - `~/dev/zalo-kabche-brand/design/visual-spec.md` — §1 tokens, §5 hard rules, §6 thumbnail template
  - `~/dev/zalo-kabche-brand/process/packaging/thumbnail-formats.md` — house rules, precedence rule, pattern menu

## Reference photo registry (real photos of Zalo — NEVER regenerate from imagination)

| Path                                      | What it is                                                            | Use for                                               |
| ----------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------- |
| `/Users/zalo/Documents/Zalo Photo.JPG`    | Master: high-res 3/4 body, arms crossed, denim jacket, grey studio bg | Default — body language reads "operator at the bench" |
| `/Users/zalo/Documents/Zalo Photo HS.png` | Square headshot crop of the same session                              | Tight-face comps, avatar-adjacent crops               |
| `/Users/zalo/Documents/Zalo Blue.png`     | 2048² headshot, blue gradient bg, black denim                         | When the comp bg is dark/cool                         |
| `/Users/zalo/Documents/zalo gold.JPG`     | 1024² headshot, gold bg                                               | Warm-bg comps (closest to paper tones)                |

**AI character sheets (secondary refs — wardrobe/pose consistency, NEVER the identity input).** Repo-tracked copies in `~/dev/zalo-kabche-brand/design/reference-photos/` (registry README there; the Zalo OS Brand Card renders the pack):

| Path (brand repo `design/reference-photos/`) | What it is                                                      | Use for                                                         |
| -------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------- |
| `character-sheet-identity.png`               | 4 views + head front/profile + color & feature notes, black tee | Wardrobe/pose ref for black-tee comps; feature-notes crib sheet |
| `character-sheet-black-hoodie.png`           | Full-body 5-view, black hoodie + joggers                        | Wardrobe/pose ref, casual register                              |
| `character-sheet-blue-blazer.png`            | Full-body 5-view, light blue blazer                             | NOT for thumbnails (no-suits rule) — other brand assets only    |

Rail rule: the identity image passed to gpt-image-2 `images.edit` is ALWAYS a real photo from the first table; a sheet may join the multi-image `image=[...]` list as a wardrobe/pose reference (like a swipe composition ref). Identity audits compare against the REAL photo, never a sheet.

Every film block batches new clean stills (2-3 setups) — **append them here as they land**; fresher real stills beat AI renders for the final ship. **Registry gap (narrowed 2026-07-15):** the real photos still share ONE wardrobe (denim over hoodie); the AI sheets add black-tee / hoodie / blazer variety for restyle prompts, but film-block stills in 2-3 outfits remain the real fix.

## Wardrobe rotation (Zalo, 2026-07-15 — "not the same jacket always")

Identity = **face, hair, beard, earring ONLY** — clothing is a free variable. The prompt's face-preservation clause silently drags the reference outfit along unless you restyle it explicitly, so every comp states a wardrobe: e.g. "dress him in a plain black crew-neck tee" / "olive work shirt, sleeves rolled" / "charcoal flannel overshirt" / "plain grey crewneck sweatshirt". Stay in his real register — workwear and plain basics, no suits, no costumes, no visible logos. Across a split-test set, no two comps wear the same outfit unless the scene demands it. Audit check: outfit changed AND face still matches the reference.

## Step 0 — Format decision (the precedence rule, locked 2026-07-14)

- **Story / proof video** (origin, scars, receipts, case study) → **photo-real**: Honest Face or The Receipt against a real-feeling background, shop74 **typography only** (section bar + display type + mono sub-line). No paper page.
- **Concept / architecture video** (frameworks, system deep-dives) → **manual-page**: full buff-paper treatment with diagram fragment.
- Paper-vs-photo is a designated 20%-iteration test once baseline data exists — when in doubt, generate one of each and let Zalo pick.

Pattern menu (from `thumbnail-formats.md`): Honest Face · Big Number + Face · The Receipt · Before/After Split · Machine-at-Work · Object Story · Two-Thing Versus. **The Receipt uses REAL screenshots composited in post — never AI-generate a dashboard, graph, or metric. An invented receipt is fabricated proof.**

Also scan the database's **"Collected outliers"** table (bottom of `thumbnail-formats.md`) each run — it grows via the weekly library hour, and proven outlier patterns beat seed patterns. Empty table → seed patterns only (state that in the report).

## The 3-concept split-test rule (default output per video)

Every video gets **exactly 3 comps, each a COMPLETELY DIFFERENT CONCEPT** — built for YouTube's Test & Compare (3-slot thumbnail A/B test), where watch-share picks the winner, not taste.

- **Diversity gate (tightened 2026-07-15 after Zalo rejected a "3-concept" set as near-identical):** different pattern families are NOT enough — three dark-workshop scenes with different props read as ONE concept at feed distance. The three must differ on **ALL FOUR** axes:
  1. **Layout skeleton** (e.g. type-left/face-right vs giant-center-element vs full-page grid)
  2. **Dominant visual** (big face vs giant number/type vs diagram/object/paper plate)
  3. **Background field** (at least one must break value: dark photo vs buff paper vs light/flat)
  4. **Display text** (at least two different lines across the set — copy is part of the concept)
     Canonical maximal spread: photo-real Honest Face (dark) · Big Number typographic (dark, number dominates, face small) · manual-page (light paper, diagram + photo plate).
- **Lineup test (mandatory before showing/shipping):** montage the three 120px squints side by side and look — if any two could be confused at a glance, the set fails; regenerate the offender. The brand anchor keeps them on-brand; this test keeps them different.
- Display text MAY differ per concept (each still ≤4 words, one orange word, complements-never-echoes the title) — thumbnail text is part of the creative under test.
- Dispatch the 3 in parallel (one agent each, full v2 architecture, different composition refs).
- Naming: `<NN-slug>-c1-<mechanic>.png` / `-c2-` / `-c3-` (+ `-720` finals). All three ship to Test & Compare; the platform's winner becomes `<NN-slug>-thumb.png`.
- **Close the loop:** when the test concludes, log the winner + watch-share delta as a row in the Collected outliers table marked `OWN TEST` (own-channel results outrank every third-party swipe row), and record the result in the video workspace §2. A concept that wins twice across videos becomes the default c1 for its video type.
- Craft iterations (lighting, crop, margin fixes) happen WITHIN a concept before the test ships — they never consume one of the 3 test slots.

## Text budget (hard rules)

| Element       | Limit                                                                                                    |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| Display title | **≤4 words**, ALL CAPS, **exactly one orange word**, COMPLEMENTS the video title — never repeats it      |
| Section bar   | `SERVICE MANUAL · SEC NN` (furniture, small, paper-on-ink)                                               |
| Mono sub-line | ≤5 short tokens, numbers as digits (`5 YRS · 139 BUSINESSES`)                                            |
| Stamp         | `TESTED` / `PASSED` / `VERIFIED` — ONLY on claims verified in the numbers bank; max one; omit by default |

Every string that must render verbatim goes in **"double quotes"** in the prompt.

## Prompt architecture

Palette goes in VERBALLY (models approximate hex poorly): "aged buff manila paper", "warm near-black ink (never pure black)", "one word in hot safety orange", "deep brick-red rubber stamp", "muted steel blue". Type: "huge ultra-bold condensed grotesque capitals, tight leading" (display) and "small typewriter-style monospace" (labels).

```
A YouTube thumbnail, 16:9, photo-real. The man from the reference photo [placement,
crop, pose]. PRESERVE HIS FACE EXACTLY — same identity, real skin texture, natural
light; do not stylize, repaint, smooth, or color-grade the face.

BACKGROUND: [real-feeling environment or flat tone — photo-real format]
            [OR: aged buff manila paper with a subtle halftone dot grain — manual-page format]

SECTION BAR (top left, solid warm-black bar, condensed caps reversed out in buff paper):
"SERVICE MANUAL · SEC 01"

DISPLAY TITLE ([zone], huge ultra-bold condensed grotesque caps, warm near-black,
tight leading): "..." with the single word "..." in hot safety orange.

MONO SUB-LINE (small typewriter monospace under the title): "..."

[Optional, verified claims only — STAMP: double-ring rounded-rect rubber stamp in deep
brick red, rotated slightly: "VERIFIED"]

Render all quoted text EXACTLY as written, spelled correctly. One focal point, high
contrast, readable at thumbnail size. No other text, no watermarks, no arrows, no
shocked expression, no money imagery.
```

Keep the assembled prompt ≤ ~200 words. Front-load the face-preservation clause.

Composition constraints proven 2026-07-14:

- **Safe-margin clause (REQUIRED — soft phrasing fails ~2 of 3 renders; this phrasing landed the bar at 16%):** include near-verbatim: "CRITICAL SAFE-MARGIN RULE: reserve a generous empty band across the WHOLE top 14 percent and the WHOLE bottom 12 percent of the frame — NO text, no letters, no bars may enter those bands. The topmost text element must begin no higher than 15 percent down from the top edge." (Covers the 3:2→16:9 crop loss.) Still verify per-image and pick a crop offset when furniture rides high.
- **Multi-part callouts:** phrase as "ONE single contiguous monospace caption line reading exactly '…' — do NOT split into separate leader-line labels" or the model scatters the strings across the diagram.
- **No glyph substitution (dispatch rule):** agents must never "helpfully" swap characters in quoted strings (e.g. hyphen for the `·` middot — the middot rendered correctly in 10+ comps on 2026-07-14; one agent swapped it anyway). A quoted string renders verbatim or it's a DEFECT to regenerate/report — never a spec edit.
- **Diagrams must be real (spec hard rule #2):** a generic gear assembly with real part callouts is still an illustrative-only diagram — a shipping manual-page comp needs the REAL architecture drawn, or a small `SCHEMATIC` label.

## Style reference (default since 2026-07-14 — proven to carry the brand system)

Pass a SECOND image to the generator: a finished Zalo Kabche thumbnail as the style anchor. gpt-image-2 `images.edit` accepts a list — `image=[<identity photo>, <style anchor>]` (proven working). The prompt must name the roles explicitly: "FIRST image = the man, preserve his face exactly; SECOND image = a finished thumbnail from the same brand, MATCH ITS VISUAL STYLE EXACTLY — do NOT copy its words." Anchors (update as better ones ship):

- Photo-real formats → the latest PICKED thumbnail (`design/thumbnails/<latest>/<slug>-thumb.png`)
- Manual-page formats → `design/thumbnails/01-introduction/01-introduction-C-gpt.png`
- Swipe images (`process/packaging/swipe/`) may ride along as a THIRD input — composition reference ONLY (Zalo sanctioned 2026-07-14): `image=[identity, brand anchor, swipe winner]`, with the prompt assigning roles explicitly — "THIRD image = compositional reference: borrow its layout mechanics (subject scale, action energy, evidence-card geometry), do NOT copy its colors, fonts, logos, objects, expressions, or words; the brand system comes from the SECOND image." Never let a swipe image be the brand-style anchor, and never inherit its guru register (shocked faces, fake arrows).

## Dispatch (Agent → `image-craft-expert`, one dispatch per variant, parallel)

```
Generate a YouTube thumbnail comp with gpt-image-2 (OpenAI), using the reference photo —
the face must be THIS man, not an invented one. Use ONLY gpt-image-2; nano-banana is not
used for this brand.

Reference photo: <absolute path>

## Prompt (refine with your craft; keep every quoted string verbatim and the
face-preservation clause first)
<assembled prompt>

## Rail — gpt-image-2 (images.EDIT — the generate endpoint cannot take the photo)
# Downscale every reference to a ≤1280px JPEG copy first (sips -Z 1280 … --setProperty format jpeg):
# full-size PNG refs drop the connection mid-stream on multi-image requests (proven 2026-07-14).
# Wrap the call in a 2-3x backoff retry for transient APIConnectionError/RemoteProtocolError.
import base64
from openai import OpenAI
client = OpenAI(timeout=600.0, max_retries=0)
stream = client.images.edit(
    model="gpt-image-2",
    image=open("<photo path>", "rb"),
    prompt="<prompt>",
    size="1536x1024",
    # NO input_fidelity param — gpt-image-2 rejects it ("does not support"), proven 2026-07-14;
    # face preservation comes from the edit endpoint + the preservation clause in the prompt
    n=1,
    stream=True, partial_images=2,   # non-streaming drops the connection on dense prompts
)
final_b64 = None
for event in stream:
    if getattr(event, "type", "").endswith(".completed"):
        final_b64 = event.b64_json
open("<outdir>/<slug>-<variant>-gpt.png","wb").write(base64.b64decode(final_b64))

## Audit loop (mandatory, max 3 attempts)
Read each PNG and check: (1) every quoted string verbatim; (2) display title ≤4 words;
(3) EXACTLY one orange word; (4) the face matches the reference photo — Read the
reference too and compare; a stranger must recognize the same man; (5) the face carries
NO paper grain / sepia / illustration style; (6) no invented extra text, arrows, or fake
metrics. Any failure → regenerate with the failing element strengthened in the prompt.
Return: file paths, attempt counts, audit table per image (check → PASS/DEFECT).
```

Variants are independent → dispatch in parallel (one Agent call each, single message).

## Post-process (main thread, after audit passes)

```bash
# gpt-image-2 masters are 1536×1024 (3:2) → center-crop to 16:9, then resize
sips -c 864 1536 "<file>.png" --out "<file>-crop.png" && sips -z 720 1280 "<file>-crop.png" --out "<file>-720.png"
# Squint test — MANDATORY before showing Zalo
sips -Z 120 "<file>-720.png" --out "<file>-squint.png"   # then Read it: one focal point? title readable?
```

## Output shape & locations

- Comps → `~/dev/zalo-kabche-brand/design/thumbnails/<NN-slug>/` as `<NN-slug>-c{1,2,3}-<mechanic>.png` (+ `-720` finals); the Test & Compare winner (or Zalo's pick pre-test) becomes `<NN-slug>-thumb.png`.
- Log comp paths + the pick into the video workspace (`videos/NN-slug.md` §2 Packaging).
- Report with denominators: "c1: 3/3 strings exact, identity PASS; c2: identity DRIFT (attempt 2/3)…" — never "thumbnails look good" without the counted audit + squint result.
- **Spot-check yourself**: Read the PNGs before relaying the agent's DONE (existence ≠ implementation).

## Anti-patterns

- ❌ Generating Zalo's face from imagination (using `images.generate` instead of `images.edit` with the photo) — always the reference-photo edit rail
- ❌ Dispatching nano-banana / Gemini, or asking whether to use it — gpt-image-2 (OpenAI) is the only rail for this brand (Zalo, 2026-07-15)
- ❌ Shocked-face gurning, money imagery, red arrows to nothing — guru register; the anti-guru contrast IS the differentiation
- ❌ Thumbnail text repeating the video title — it must complement
- ❌ More than one orange word, or orange used as a background wash — orange is scarce or it's nothing
- ❌ AI-generating dashboards/graphs/receipts as "proof" — fabricated proof kills the brand; real screenshots only, composited in post
- ❌ Stamping `VERIFIED`/`TESTED` on anything not in the verified numbers bank
- ❌ Styling the face (sepia, halftone on skin, illustration) — the manual frames the human, never costumes him
- ❌ Hex codes in prompts — verbal color descriptions only
- ❌ A 4th regen on the same defect — restructure (different photo, simpler layout) per the 3+ Fixes Rule
- ❌ Copying the reference photos into the PUBLIC claude-setup repo — this skill and the photo paths stay on the private personal branch

## Edge cases

- **Identity drift persists after 3 attempts** → stop rerolling; composite the REAL photo in post as a photo plate (rectangular crop, thin ink border — very shop-manual) over an AI/flat background, or wait for film-block stills.
- **Text garbles persistently** → generate the comp with NO text ("leave the left two-thirds empty") and overlay type deterministically (HTML/Playwright or ImageMagick with Barlow Condensed) — the brand fonts are installed locally.
- **Final ship**: AI-rendered face is fine for COMPS; for the published thumbnail prefer a real still, and an AI face ships only if Zalo explicitly approves it after seeing it at full size.
- **New verified numbers** → refresh from the Credibility Bank before stamping; numbers only grow, cite fresh.

## Pair with

- **`image-craft-expert`** — the executor (gpt-image-2 rail + audit loop)
- **`infographics`** — educational one-pagers, not thumbnails; **`machine-editorial-broll`** — motion slides
- **`daily` / packaging stage** in the brand repo — this skill is stage 2/3's thumbnail step
