---
name: infographics
description: Generate dense, text-heavy educational infographics via AI text-to-image — gpt-image-2, executed through the image-craft-expert agent. Encodes the 6 layout archetypes, 3 style presets, the quoted-string text-budget prompt architecture, and a mandatory read-back text audit. Use when the user says "make an infographic", "turn this into an infographic", "visualize this concept/framework", "visual cheat sheet", "diagram this idea", or hands over educational/marketing content to be turned into a shareable image. NOT for precise data charts (use the dataviz skill + real chart code) and NOT for video motion graphics (that's machine-editorial-broll). Replaces one-line "make an infographic about X" prompts that produce garbled text and generic layouts.
---

Turn a concept, script, or document into a dense, legible, correctly-spelled infographic image — distill → spec → styled prompt → gpt-image-2 via `image-craft-expert` → read-back text audit.

## When to invoke

- User says "make an infographic", "turn this into an infographic/visual", "infographic version of this"
- User hands over a framework, protocol, comparison, or lesson and wants a shareable image (course content, ad education, social posts, slide inserts)
- A `/brainstorm` or content session produces a concept worth a visual one-pager

Skip for: precise data charts (numbers/axes must be exact → `dataviz` skill + real chart code; AI-rendered charts are decorative fiction), motion-graphics slides for video (`machine-editorial-broll`), AI footage (`seedance`), single icons/assets (plain `image-craft-expert` dispatch, no infographic architecture needed).

## Prerequisites

- `OPENAI_API_KEY` set in the environment (the agent's gpt-image-2 call uses it via `OpenAI()`). If missing → `checkpoint:human-action` to set it; do not fall back to another model silently.

## The pipeline

1. **Distill** the source content into an infographic spec (main thread — this is the judgment step; see Text Budget).
2. **Pick an archetype** from the library below — it dictates the layout skeleton.
3. **Pick a style preset** — default `neon-tech` unless the content is a do/don't morality tale (`cartoon-editorial`) or destined for LinkedIn/slides (`clean-light`).
4. **Assemble the prompt** with the Prompt Architecture, then **dispatch `image-craft-expert`** with the dispatch template below. The agent refines the prompt with its generic craft, generates with **gpt-image-2 only**, and runs the audit loop itself.
5. **Spot-check**: Read the returned PNG yourself and verify the audit table against the spec before reporting done. Existence ≠ implementation — never relay the agent's DONE unseen.

## Text Budget (the #1 failure mode is too much text)

| Element         | Limit                                         |
| --------------- | --------------------------------------------- |
| Title           | ≤ 12 words, ALL CAPS, one color-keyed keyword |
| Panel header    | ≤ 8 words                                     |
| Label           | ≤ 6 words                                     |
| Caption         | ≤ 14 words                                    |
| Takeaway banner | ≤ 20 words                                    |
| **Whole image** | **≤ ~120 words, ≤ ~25 distinct strings**      |

- Over budget → **split into a series** (2–4 images sharing one style preset), never cram.
- Every string that must render verbatim goes in **"double quotes"** in the prompt. Unquoted text is treated as art direction and will be paraphrased or dropped.
- ALL-CAPS headers render more faithfully than mixed case. Short numerals and simple math render well (`"$30 CPA x 50 ÷ 7 = $214/day"`). Avoid semicolons and long clauses inside strings.

## Archetype library

| Archetype            | Use when                                            | Layout skeleton                                                                                                                                                                                                   |
| -------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `before-after-split` | Old way vs new way, paradigm shift                  | Two vertical half-panels (left muted/desaturated = before, right vibrant/glowing = after), center arrow badge with the shift label, per-side header in the title banner                                           |
| `process-flow`       | Pipeline or sequence (input → process → output)     | 3–4 numbered rounded panels left→right, glowing arrows connecting, optional full-width summary box at bottom, optional feedback-loop arrow returning to start                                                     |
| `trap-vs-solution`   | Mistake vs correct behavior, do/don't lesson        | Two panels: left = character acting out the mistake (warm chaotic palette, oversized red ✗), right = character doing it right (cool composed palette, green ✓), bottom white takeaway banner                      |
| `phased-timeline`    | Phases/zones over time (protocols, learning curves) | N color-coded zone panels (red→blue→green) each with a mini line-chart showing that phase's shape, a small reaction character with speech bubble, and a verdict line; full-width protocol/summary panel at bottom |
| `quadrant-grid`      | 4 related sub-principles of one topic               | 2×2 numbered panels, each: short header + one metaphor illustration + one-line caption below                                                                                                                      |
| `central-metaphor`   | One big idea                                        | Single dominant metaphor illustration (funnel, pipeline, iceberg, valve) center, orbiting labeled callouts, title top, takeaway bottom                                                                            |

## Style presets (copy verbatim into the prompt)

**`neon-tech`** (default — educational tech/marketing content):

> Digital infographic illustration style: deep navy-to-dark-purple gradient background with faint glowing circuit-board traces and a subtle perspective grid. Content organized in rounded-rectangle panels with thin glowing borders — electric cyan and violet, or semantic red/blue/green when a panel means danger/neutral/success. Bold condensed ALL-CAPS sans-serif title in white with key words color-keyed in cyan or green. Small clean white labels; positive terms highlighted teal/green, negative terms red/orange. Glossy semi-3D cartoon icons and small expressive characters, glowing arrows showing flow, tiny sparkle accents. High information density with crisp panel hierarchy; professional educational tech aesthetic.

**`cartoon-editorial`** (do/don't lessons, emotional contrast):

> Vibrant flat cartoon editorial illustration: thick clean outlines, saturated colors, exaggerated expressive characters showing clear emotion. Split-temperature composition — warm chaotic oranges/reds on the wrong side, cool composed blues on the right side. Big symbolic props act as metaphors for abstract concepts. Oversized red X and green checkmark stamps. Black title banner at top with bold condensed white ALL-CAPS type, one key phrase highlighted in accent color. White bottom banner with the takeaway lesson in bold dark text.

**`clean-light`** (LinkedIn, decks, docs):

> Minimal flat vector infographic on a white background: modern geometric sans-serif type in near-black, one accent color plus at most two supporting hues, thin-line icons, generous whitespace, soft card shadows, strict grid alignment. Calm corporate-editorial aesthetic.

For a **brand palette**, replace the preset's colors with verbal descriptions ("deep navy background, electric blue accents") — never hex codes; image models approximate hex poorly.

## Prompt architecture

```
A landscape educational infographic. [STYLE PRESET BLOCK]

TITLE BANNER (top, full width): "THE OBJECTIVE TRAP: OPTIMIZING FOR STEPS vs OUTCOMES"

LAYOUT: two vertical panels side by side with a bottom takeaway banner. [archetype skeleton]

LEFT PANEL — header "THE TRAP (Feeding Junk Signals)":
A stressed man shovels junk food into a chaotic overweight robot labeled "SILOED AI MODEL".
Floating labels: "CLICKS", "ADDS TO CART", "VIEWS". A conveyor outputs gray figures
captioned "LOW QUALITY USERS (Window Shoppers)". Oversized red X stamp.

RIGHT PANEL — header "THE SOLUTION (Feeding Value)": [...]

BOTTOM BANNER: "DON'T OPTIMIZE FOR INTERMEDIATE STEPS. OPTIMIZE FOR THE FINAL OUTCOME."

Render all quoted text EXACTLY as written, spelled correctly, high contrast and legible.
No extra words, no filler text, no lorem ipsum, no watermarks.
```

Rules: regions in reading order (title → panels → bottom); one metaphor per panel described in one or two sentences; the fidelity clause is always the last line. Keep the full assembled prompt ≤ ~250 words — over-long prompts stretch render time and trip the API gateway (502) even when streaming (proven 2026-07-13); compress the style block before cutting content strings.

## Dispatch template (Agent → `image-craft-expert`)

```
Generate an infographic with gpt-image-2 only. Skip your dual-model default and do not run nano-banana.

## Prompt (refine with your craft, but keep every quoted string verbatim and keep the layout regions)
<assembled prompt>

## Settings
- model: gpt-image-2, size: 1536x1024 (landscape; use 1024x1536 only if a vertical was requested), n=1
- the API call MUST stream: `stream=True, partial_images=2`, client `timeout=600.0` — non-streaming
  images.generate drops the connection on dense infographic prompts (APIConnectionError; proven 2026-07-13)
- output: <dir>/<slug>-v<N>.png

## Audit loop (mandatory)
After generating, Read the PNG and audit EVERY quoted string against this list: <numbered list of all quoted strings>.
If any string is garbled, misspelled, or missing: regenerate (max 3 attempts total). Between attempts,
shorten the failing string and/or reduce label count near it — do not just reroll.
Return: file path(s), attempt count, audit table (string → EXACT / DEFECT: what rendered), remaining defects.
```

The agent ends with `## IMAGE GENERATED` / `## GENERATION FAILED` per `~/.claude/rules/agent-contracts.md`.

For a **series**, dispatch one agent per image in parallel (they share no state) — same style preset block verbatim in every prompt, same size, and name recurring motifs ("the same green-tie man character reacts in each zone").

## Output shape

Report: file path, archetype + preset used, audit result with denominator ("23/25 strings exact; defects: 'ANDROMEDA' rendered 'ANDROMDA' in panel 2"), attempts used. Never claim "text is clean" without the counted audit.

## Anti-patterns

- ❌ One-line prompt ("make an infographic about X") — produces garbled text and generic layout; always distill → archetype → architecture
- ❌ Pasting source paragraphs into the prompt — distillation is the skill; sentence walls garble
- ❌ Must-render text left unquoted — it will be paraphrased or dropped
- ❌ Cramming >~120 words into one image instead of splitting a series
- ❌ Relaying the agent's success without Reading the PNG yourself (existence ≠ implementation)
- ❌ Using this for data charts whose numbers must be exact — the model draws decorative fiction; use `dataviz`
- ❌ Real logos, real product screenshots, real people — hallucinated; composite them in post instead
- ❌ A 4th regen attempt on the same defect — restructure the text load instead (3+ Fixes Rule)

## Edge cases

- **True 16:9 needed** (YouTube thumbnail/slide): gpt-image-2 only offers 1536×1024 (3:2). Keep the top/bottom 7% of the layout free of text and crop to 1536×864 in post (`sips` or ffmpeg).
- **Non-English text**: halve the text budget and expect more audit retries.
- **On-theme extras**: despite the fidelity clause, the model may add small unrequested micro-labels (status badges, file-type tags, progress percentages). Correctly-spelled, non-misleading extras are a PASS — reroll only if one changes the meaning.
- **Series consistency drifting**: tighten by reusing not just the style block but the full title-banner treatment and panel-border description across prompts.
- **`OPENAI_API_KEY` missing**: emit `checkpoint:human-action`; don't silently swap models.

## Pair with

- **`image-craft-expert`** — the executor: prompt refinement + gpt-image-2 generation + audit loop
- **`dataviz`** — when the ask is actually a precise chart from real data
- **`machine-editorial-broll`** — branded motion-graphics slides for video; **`seedance`** — AI footage. This skill = static AI-generated images.
- **`telegram` / `ghl-upload`** — delivering the finished PNGs
