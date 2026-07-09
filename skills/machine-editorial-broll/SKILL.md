---
name: machine-editorial-broll
description: Generate branded motion-graphics "slides b-roll" for Zalo's videos (VSLs, YouTube, teleprompter scripts) using the Machine Editorial design system in the Remotion studio at /Users/zalo/dev/operator-broll. Use when the user says "slides b-roll", "b-roll for this script", "motion graphics for my video", "VSL-style slides", "machine editorial", or hands over a script/teleprompter text and wants the graphics cut. NOT for AI-generated footage — that's the seedance skill; this one is for the branded typographic slide system (dark navy + electric blue + gold ignite, matching the Operator Base VSL slides). Keeps every video's b-roll in one consistent, ownable visual language instead of re-deriving the style per video.
---

Turn a video script into branded Machine Editorial b-roll segments — typed labels, red strikes, gold ignites, drawn traces — rendered with Remotion from the studio project.

## When to invoke

- User hands over a pre-written video script / teleprompter text and wants the "slides b-roll" segments built
- User says "make b-roll slides for X", "motion graphics in our style", "VSL-style slides for this section"
- User wants a new segment added to an existing video's b-roll set
- User asks for a theme variant of existing segments ("same but for the YouTube series")

Skip for: AI-generated _footage_ (people, scenes, camera moves → `seedance` skill), static slide images (use the VSL slide pipeline), and one-off image assets (→ `nano-banana`).

## The design system (Machine Editorial)

The b-roll behaves like an intelligent system composing a document in real time — the opposite of influencer kinetic-type. Full implementation lives in `/Users/zalo/dev/operator-broll/src/system/` (tokens.ts, anim.ts, Stage.tsx, moves.tsx). Non-negotiable laws:

1. **Two speeds only.** Machine-time (linear: typing, line draws, counters) and settle-time (expoOut entrances). Nothing bounces, nothing overshoots. No spring wobble, ever.
2. **Process, not effect.** Text never "flies in" — it is typed, ruled, drawn, stamped, ignited, struck, counted, or installed.
3. **Semantic color, never decorative.** White = the message · blue `#3782FF` = the machine · gold = money/payoff · red = the old way (only used to destroy) · green = confirmation only.
4. **Machine chrome fingerprint.** Every segment carries the mono metadata layer: kicker (`— THE SHIFT`), segment ID (`OB-BR-01 / COLLISION`), live timecode, optional bottom meta line. This is the ownable watermark language — never omit it.
5. **The stage.** Layer order back→front: void gradient → blueprint grid → orb (optional) → content → chrome → grain → vignette. All provided by `<Stage>`.

### The eight signature moves (`src/system/moves.tsx`)

| Move    | Component                                      | Use for                                             |
| ------- | ---------------------------------------------- | --------------------------------------------------- |
| STAMP   | `<Stamp at>`                                   | Headlines landing — one hard settle                 |
| RISE    | `<Rise at>`                                    | Sentence/line reveals (masked)                      |
| TYPE    | `<TypeOn text at>`                             | Mono labels, machine annotations                    |
| IGNITE  | `<Ignite at>`                                  | THE payoff word turns gold (gradient sweep + bloom) |
| STRIKE  | `<Strike at>`                                  | Killing the old way (red rule, dims to 35%)         |
| TRACE   | `<TraceArrow at x y length>`                   | Connecting A→B (line draws, arrowhead rides tip)    |
| COUNT   | `<RollUp at to prefix>` inside `<GoldPill at>` | Money — always rolls, never appears                 |
| INSTALL | `<CheckBadge>` / `<ProgressCircle>`            | Confirmation, step states (FIND/DEMO/INSTALL)       |

### Comp archetypes (`src/comps/`)

Map each script beat to one archetype; copy the closest existing comp as the starting point:

- **COLLISION** (`CostCollision.tsx`) — old way vs new way: stamp old → strike parts → trace across → ignite new → roll money
- **SYSTEM STATE** (`ThreeSteps.tsx`) — where we are in the machine: done/active/idle progress nodes + headline with ignited payoff
- **PROOF** (`ProofCard.tsx`) — a receipt assembling itself: card border draws → identity types → quote rises → payoff ignites → old tool struck
- New archetypes (STAT rollup, LIST build, CTA end-card) follow the same skeleton: `<Stage kicker segmentId meta>` + moves on a 12-frame base grid @30fps, staggers of 6–12 frames

## How to use

1. **Read the script**, split into beats (one idea per 5–9 s segment). For each beat pick: archetype, the ONE ignite-worthy payoff phrase, what (if anything) gets struck in red, any numbers to roll.
2. **Create/edit comps** in `/Users/zalo/dev/operator-broll/src/comps/`, register in `src/Root.tsx` (1920×1080 @30fps; 150–270 frames per segment). Comp IDs: PascalCase, no spaces.
3. **Verify cheaply first** — typecheck, then a still at a late frame, view it, then commit to the full render:

```bash
cd /Users/zalo/dev/operator-broll
npx tsc --noEmit
npx remotion still <CompId> out/preview.png --frame=<lateFrame>   # inspect with Read
npx remotion render <CompId> out/<CompId>.mp4                      # final 1080p H.264
```

4. **Delivery formats:**

```bash
# 4K upscale for YouTube masters
npx remotion render <CompId> out/<CompId>-4k.mp4 --scale=2
# Transparent overlay (play graphics OVER the talking head):
# pass transparent:true (Stage drops void/grid/orb/grain/vignette) and force PNG frames.
npx remotion render <CompId> out/<CompId>.mov --codec=prores --prores-profile=4444 --image-format=png --pixel-format=yuva444p10le --props='{"transparent":true}'
# Verify alpha landed: ffprobe shows pix_fmt=yuva444p… (the "a" = alpha).
# Never set Config.setProResProfile in remotion.config.ts — it is global and breaks all h264 renders.
```

5. **Theme variants** — pass a theme via `defaultProps` in Root.tsx (`VIOLET`, `TEAL`, or a new one in `tokens.ts`). Change only: accent hue, grid density/size, bg tint, orb on/off. Gold, red, green are brand constants — never re-map them.

## Output shape

Report per segment: `✓ <CompId> — <duration>s → out/<CompId>.mp4` plus one inspected still per new comp. On render failure: the failing comp ID + the last 15 lines of the render log, never the full log.

## Anti-patterns

- ❌ Bouncy/elastic easing, overshoot, pop-in scale >1.06 — that's the generic influencer look this system exists to avoid
- ❌ Decorative color (gold for a non-payoff word, red for emphasis) — color is semantic or it's noise
- ❌ More than one IGNITE per segment — if everything glows, nothing pays off
- ❌ Omitting the machine chrome (kicker/segment ID/timecode) — it's the brand fingerprint, not clutter
- ❌ Filling the frame — 60%+ stays void; restraint IS the differentiation
- ❌ Rendering the full MP4 before inspecting a still — wastes minutes per iteration
- ❌ TypeScript 7 in the studio project — Remotion's bundler breaks; stay on typescript@5.x

## Edge cases

- **Vertical (9:16) needed** — comps use absolute 1920×1080 positions; build a dedicated vertical comp (1080×1920) rather than letterboxing. Reel visual kit conventions are in memory (`project_black_umbrella_reels`).
- **Long holds for voiceover** — extend `durationInFrames`; the Stage grid drift and orb breathing keep the hold alive.
- **New client/brand** — clone a theme in `tokens.ts`; the system re-skins with accent + grid + bg only.

## Pair with

- `seedance` — AI footage clips to intercut with these graphic segments
- `view-video` — frame-extract a rendered MP4 to visually verify motion
- `transcribe` — pull timing from a recorded teleprompter take to size segment durations
- `commit-with-heredoc` — commit studio changes after renders verify
