---
name: seedance-video-prompt-builder
description: Generate a detailed, shot-by-shot, copy-and-paste-ready video prompt for Seedance 2.0 from a creative brief. Use this skill whenever the user wants to create a Seedance video prompt, write a shot list, plan a video sequence, or describe a video concept for AI generation, or mentions Seedance. Also trigger when the user describes a scene, ad concept, brand film, product video, or any visual sequence they want turned into a generation-ready prompt — even if they don't explicitly say "video prompt." Trigger on phrases like "write me a video prompt", "Seedance prompt", "shot list", "plan a video", "video concept", "create a sequence", "brand film prompt", "ad prompt", or any time the user describes what they want to happen in a video and needs it translated into a copy-paste-ready prompt.
---

# Seedance Video Prompt Builder

Build a cinematic, shot-by-shot video prompt from a creative brief — formatted so the user can copy-paste it directly into Seedance 2.0. Output the prompt and nothing else: no analysis, no inventory, no density map, no energy arc, no commentary.

## How this skill works

1. The user provides a **creative brief** — this can be as simple as "a runner in a stadium for a Nike-style ad" or as detailed as a full storyboard. They may also reference a video, mood, brand context, or specific effects.
2. Read `references/effects-breakdown-reference.txt` to internalise the level of detail, vocabulary, and shot-block format expected.
3. Output the shot-by-shot timeline. That's it.

## Input expectations

The user's brief can include any combination of:
- Subject/talent description
- Setting/environment
- Mood, tone, energy level
- Brand or product context
- Specific effects or camera moves they want
- Duration target
- Reference to existing ads, films, or visual styles
- Colour palette or grade preferences

If the brief is too vague to build a full prompt (e.g. "make something cool"), ask one focused clarifying question before proceeding. Don't over-interrogate — work with what you're given and make creative decisions where the user hasn't specified.

## Output — ONLY the shot-by-shot timeline

Output the prompt as a clean shot list. Each shot follows this block format:

```
SHOT [N] ([timestamp]) — [Shot Name / Description]
• EFFECT: [Primary effect name] + [secondary effects if stacked]
• [Detailed description of what's happening visually]
• [Camera behaviour — angle, movement, lens if relevant]
• [Speed/timing information]
• [How this shot connects to the next — transition type]
```

Do NOT include any of the following in the output:
- Master effects inventory
- Effects density map
- Energy arc / three-act breakdown
- Pre-amble, intro lines, or "Here's your prompt:" framing
- Post-amble, summaries, or "Let me know if you want changes" lines
- Section headers like "## SHOT-BY-SHOT EFFECTS TIMELINE" — just start with `SHOT 1`

The first line of the response is `SHOT 1 (...)`. The last line is the final shot block. Nothing else.

### Shot-writing guidelines

- Each shot is 1–4 seconds unless the brief calls for longer holds
- Name effects precisely: "speed ramp (deceleration)" not "speed ramp"; "digital zoom (scale-in)" not "zoom"
- Describe stacked effects explicitly — if 3 things happen at once, list all 3
- Include transition logic: how does this shot EXIT and how does the next shot ENTER?
- Use language Seedance can interpret — describe the visual result, not editing-software jargon. Say "the frame scales inward rapidly," not "apply a keyframed scale effect in After Effects"
- Mark the most impactful shot with a callout like "This is the SIGNATURE VISUAL EFFECT"
- Be specific about speed percentages for slow-motion (e.g. "approximately 20–25% speed")
- Describe motion blur, light behaviour, and atmospheric effects where relevant

## Creative principles

These shape the prompt even though they don't appear in the output:

1. **Contrast drives impact.** Alternate dense and clean moments. Slow-mo after a speed ramp hits harder than two ramps in a row.
2. **Signature moments matter.** Every video needs at least one "hero" effect — flag it inside the shot block with `SIGNATURE VISUAL EFFECT`.
3. **Transitions are shots.** A whip pan, bloom flash, or motion blur smear is a creative beat, not filler.
4. **Specificity over vagueness.** "Frame rotates clockwise ~15–20°" beats "camera tilts." "~20–25% speed" beats "slow motion."
5. **Energy must resolve.** However intense the opening, the final shots should feel intentional, not abandoned.

## Tone and style

- Direct, technical, director's-notes tone
- Bullets within each shot block
- Concise but complete
- No hype words ("stunning," "breathtaking") — describe what happens

## Duration calibration

- **5–10 seconds**: 4–7 shots, 1 signature effect
- **10–20 seconds**: 8–14 shots, 1–2 signature effects
- **20–30 seconds**: 12–20 shots, 2–3 signature effects
- **30+ seconds**: scale accordingly, maintain density contrast

If no duration is specified, default to 15–20 seconds.

## Example workflow

**User:** "Dramatic brand film for a trail running shoe. Mountain setting, golden hour, single runner. Epic but not over-the-top. ~15 seconds."

**You:** Read the reference file, then output the shot-by-shot timeline (8–12 shots) as the ENTIRE response. No intro, no outro, no analysis sections.
