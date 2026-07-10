---
name: machine-editorial-broll
description: Generate branded motion-graphics "slides b-roll" for Zalo's videos (VSLs, YouTube, teleprompter scripts, reels) using the Machine Editorial v3 system in the Remotion studio at /Users/zalo/dev/operator-broll. Use when the user says "slides b-roll", "b-roll for this script", "motion graphics for my video", "VSL-style slides", "machine editorial", or hands over a script/teleprompter text and wants the graphics cut. NOT for AI-generated footage — that's the seedance skill; this one is for the branded typographic beat system (dark navy + electric blue Line + gold ignite). Keeps every video's b-roll in one consistent, ownable visual language instead of re-deriving the style per video.
---

Turn a video script into branded Machine Editorial b-roll: mobile-first chains of full-screen beats with huge type, a continuous camera, The Line signature, impact physics, and a synth SFX bed — rendered with Remotion from the studio project.

## When to invoke

- User hands over a script / teleprompter text and wants the "slides b-roll" built
- User says "make b-roll slides for X", "motion graphics in our style", "cut this chunk"
- User wants a new segment added to an existing set, or a theme/vertical variant

Skip for: AI-generated _footage_ (people, scenes, camera moves → `seedance`), static slide images, one-off image assets (→ `nano-banana`).

## The design system (Machine Editorial v3)

The b-roll behaves like an intelligent system composing a document in real time — the opposite of bouncy influencer kinetic-type. Implementation lives in `/Users/zalo/dev/operator-broll/src/system/`. Non-negotiable laws:

0. **DEPICTION LAW (governs everything below).** Every animation depicts the idea being spoken at that moment — never "random stuff that looks cool." The mute test: watching the beat with no audio, a viewer should still get what this beat is ABOUT (a cost colliding, three steps assembling, a false fix being killed, a machine waking up). Motion is meaning: things that die get slashed, things that grow roll up, things that assemble fly in, the turn in a story is a literal turn in the path. Craft (gloss, camera, grain) sets the QUALITY; the script line sets the SUBJECT. If you can't name which script phrase a visual depicts, it doesn't go on screen.
1. **Mobile-first beats.** A segment is a chain of ~2s full-screen beats (`Beat`), max ~5 words on screen at once, key type 150–210px, center-weighted. Never compose a dense slide.
2. **Two speeds only.** Machine-time (linear: line draws, typing, counters) and settle-time (expoOut entrances). Nothing bounces, ever. Camera shake is a decaying mechanical kick, not a spring.
3. **Motion never stops.** One continuous `SegmentCamera` move (push + drift) across the whole segment — no per-beat resets (`Beat push={false}`); beats overlap on enter/exit; grain is live (per-frame).
4. **THE LINE is the signature.** One comp-level `LineRig` line lives through the entire segment: it underlines what matters (blue), slashes what dies (red), releases, travels, and settles under the payoff. It never dies mid-segment. Red only destroys; blue is the machine; gold = money/payoff (max one Ignite per segment); green confirms.
5. **The world reacts.** When a message lands: `ImpactFlash` (2-frame flash + shockwave ring) + the same frame in `SegmentCamera impacts` (camera kick) + SFX hit. Pain beats get no gold and softer impacts.
6. **Typographic craft.** Big words enter via `LetterStamp` (per-letter cascade, tracking tightens on settle, 5-frame chromatic split). Soft middle beats use `WordCascade`. Mono labels via `MonoTag`/`TypeOn`.
7. **Chrome:** `chrome="minimal"` (kicker + floor tag only) for ad cuts and anything mobile; `chrome="full"` (segment ID + live timecode + meta) for full-frame YouTube masters.

### System toolbox (`src/system/`)

| File          | Exports                                                                                                           | Use                                                                                            |
| ------------- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `beats.tsx`   | `Beat`, `PushIn`, `WordCascade`, `LetterStamp`, `DimAt`, `TheLine`, `MonoTag`                                     | beat chains + type craft                                                                       |
| `camera.tsx`  | `SegmentCamera`                                                                                                   | continuous move + impact shake                                                                 |
| `linerig.tsx` | `LineRig`, `LineKeyframe`                                                                                         | The Line choreography (comp-level, absolute frames)                                            |
| `impact.tsx`  | `ImpactFlash`                                                                                                     | flash + shockwave on landings                                                                  |
| `moves.tsx`   | `Stamp`, `Rise`, `TypeOn`, `Ignite`, `Strike`, `TraceArrow`, `RollUp`, `GoldPill`, `CheckBadge`, `ProgressCircle` | v1 slide-mode moves (still used inside beats: Stamp/Ignite/RollUp)                             |
| `tokens.ts`   | `OPERATOR`, `VIOLET`, `TEAL`, `Theme`                                                                             | themes — variants change accent/grid/bg only; gold/red/green are brand constants               |
| `Stage.tsx`   | `Stage`                                                                                                           | void → grid → orb → content → chrome → live grain → vignette; `transparent` for alpha overlays |
| `world.tsx`   | `World`, `WorldCam`, `Station`, `WorldPath`                                                                       | infinite-canvas mode: keyframed camera over a huge canvas; path = The Line at map scale        |
| `plates.tsx`  | `ImagePlate`, `ExhibitFrame`                                                                                      | AI-image plates (masked RGBA) + documentary exhibit framing                                    |
| `three3d.tsx` | `Scene3D`, `CameraPose`, `mulberry32`, `useGlowTexture`                                                           | Three.js layer (@remotion/three): real 3D depth/particles UNDER the 2D type system             |

### Canonical comps (`src/comps/`)

- **`Ch1FalseFixesV3`** — COLLISION flagship: LineRig slashes 3 false fixes red → turns blue → underlines the gold payoff. Copy this for anything old-way-vs-new-way.
- **`Ch1SundayNightV3`** — VERDICT: moody orb cold-open, line as a quiet clock, returns for the verdict. No red, no gold.
- **`Ch1TheMachineV3`** — SYSTEM+COUNT: line tours the step stations, settles under the `RollUp` money pill.
- **`Ch1OneChoiceV3`** — JOURNEY (infinite canvas): story ideas live as `Station`s on one huge canvas; `WorldPath` draws ahead, the camera follows, the path physically turns at the pivot line, destination ignites, zoom-out finale reveals the whole journey.
- **`ExhibitMachineV3`** — EXHIBIT (documentary + AI plate): a gpt-image-2 asset as case-file evidence — `ExhibitFrame` corner ticks, Ken Burns push, LineRig pointing at the detail, mono dossier annotations typing.
- v1 slide-mode comps (`CostCollision`, `ThreeSteps`, `ProofCard`) remain for dense desktop-only explainers (e.g. testimonial receipt cards).

### Mode selection

| Script shape                                               | Mode                | Base comp                   |
| ---------------------------------------------------------- | ------------------- | --------------------------- |
| Sequential punches (kill list, steps, money)               | Beat chain          | FalseFixesV3 / TheMachineV3 |
| Emotional hold / cold open                                 | Verdict             | SundayNightV3               |
| A story with a turn ("they did X, then Y, and it changed") | Infinite canvas     | Ch1OneChoiceV3              |
| Evidence, proof, product/object showcase, "look at this"   | Documentary exhibit | ExhibitMachineV3            |
| Dense receipt (testimonial with badges) for desktop        | v1 slide mode       | ProofCard                   |

## Infinite-canvas mode (JOURNEY)

For story-shaped passages: lay ideas out spatially, fly the camera between them, reveal the journey at the end. Rules:

- Canvas ~6000×3000; `WorldCam` keyframes = hold → hop (30–35f, cubic in/out — filmed, never springy) → hold. Everything inside `World` uses ABSOLUTE frames and CANVAS coordinates; chrome stays outside.
- `WorldPath` progress keyframes are cumulative length fractions — the head must arrive at each station ~4f BEFORE the camera does (the Line leads, the camera follows).
- Station text: ≤6 words, 105–140px; entrances via WordCascade/LetterStamp timed to camera arrival.
- End the path AS the underline of the destination station; make the path physically turn where the script turns.
- Zoom-out finale: check the whole-canvas bbox fits the viewport at finale z (text half-widths included) — clipped words are the classic bug.

## AI image plates (gpt-image-2 / nano-banana)

When a beat benefits from an object/scene (product core, mockup, metaphor), generate a masked plate and composite it:

1. Generate on chroma green (gpt-image-2 rejects `background:"transparent"`): prompt must say "COMPLETELY ISOLATED on a solid uniform pure chroma-key green background (#00FF00), no floor, no ground shadow, no reflections". Use `quality:"medium"` (high often drops the connection) via `curl https://api.openai.com/v1/images/generations` with `$OPENAI_API_KEY`, or `nano-banana -t` (needs valid `GEMINI_API_KEY`).
2. Key + trim: `ffmpeg -i in.png -vf "colorkey=0x00FF00:0.32:0.08,despill=type=green" -frames:v 1 out.png`, then PIL `getchannel('A').getbbox()` crop. Save to `public/assets/`.
3. Composite with `<ImagePlate src="assets/x.png" width at over kenBurns sweepAt/>` — entrance settle, continuous Ken Burns, ambient accent glow, optional documentary highlight sweep. Wrap in `<ExhibitFrame label="fig. 01 — ...">` for the documentary look.
4. Style guardrail: ask for dark-navy + electric-blue palette, premium 3D render, rim light — plates must sit in the Stage's world, not on top of it.

## 3D layer (Three.js under the type)

For beats that earn real depth — cold opens, data visualizations, payoff atmospheres — put a Three.js world UNDER the 2D system, never instead of it. Typography, The Line, chrome, grain stay 2D on top (3D text is always a downgrade); the scene provides parallax, particles, volume. Pilot: `TokenField3D` (4,000 instanced tokens; camera flies through; they assemble into the context-window slab as the term stamps in 2D).

Rules:

- `Scene3D` inside a normal `Stage` (`orb={false}`); scene background/fog use theme void colors so grain/vignette blend.
- DETERMINISM IS LAW: all motion pure functions of `useCurrentFrame`; `mulberry32(seed)` for any randomness — `Math.random`/`useFrame` deltas break renders.
- Camera pose = pure `(frame) => {pos, look, fov}`; impacts = the same decaying SHAKE pattern applied to the pose.
- InstancedMesh for particle counts (matrix updates in a `useLayoutEffect` keyed on frame); additive-blended `useGlowTexture` sprites for atmosphere; no post-processing dependency needed — emissive colors + 2D grain/vignette carry the look.
- Overlay text over busy 3D gets `textShadow: '0 2px 30px rgba(2,6,13,0.95), 0 0 60px rgba(2,6,13,0.8)'`.
- Render/still with `--gl=angle`. `@remotion/three` version must EXACTLY match the remotion version.
- The 3D subject must BE what the script line talks about (Depiction Law): tokens for "tokens", the orb for the machine's presence, panels for "install". 3D that's merely atmospheric while the VO makes a specific claim = decoration; cut it or make it literal.
- 3D archetype boilerplates: PARTICLE-DATA (built: TokenField3D), GLOSS (built: GlossClump3D — look-dev), ORB-SCENE (built: OrbScene3D — the production template for hero beats), TUNNEL-JOURNEY (canvas mode in true z), OBJECT-SHOWCASE (GLB turntable).
- GLOSS is a QUALITY TIER, not a subject: apply the material/lighting/negative-space recipe to BRAND-MEANINGFUL objects (the orb, the machine core, panels, steps) — never generic balls/confetti for production. OrbScene3D is the reference application: one opaque dark-clearcoat mass (`#0E2242`, roughness 0.26, clearcoat 1) + additive `useGlowTexture` halo sprite behind it + one blue rim pointLight.
- GOTCHA: `meshPhysicalMaterial transmission` (glass interiors) renders black/hollow under headless `--gl=angle` — do NOT use transmission; fake glass depth with opaque clearcoat + halo + rim light.

### GLOSS — the Apple-clean look (default 3D quality tier for hero/brand beats)

`GlossClump3D` is material/lighting look-dev ONLY (abstract spheres fail the Depiction Law — never ship its subject). Copy its recipe onto objects the script is actually about (`OrbScene3D` is the shipped example). Few LARGE objects, never confetti; premium comes from physically-based light, not motion complexity:

- `Scene3D environment="room"` — offline PMREM RoomEnvironment gives the studio window-reflections that make surfaces read expensive. `fog={null}` (fog kills gloss).
- Material recipe: `meshPhysicalMaterial` `roughness≈0.22 metalness=0 clearcoat=1 clearcoatRoughness≈0.12 envMapIntensity≈1.15`; sphereGeometry 64 segments.
- Palette by count for ~16 objects: ~6 deep navy, ~5 accent blue, ~4 white, exactly ONE gold (the payoff accent, same law as Ignite).
- Long lens (fov 30–35) + NEGATIVE SPACE: object cluster ≤ ~55% of frame height, floats in void, camera dollies slowly. Filling the frame is the failure mode.
- Clump layout: seeded scatter + fixed-iteration overlap-relaxation in `useMemo` (deterministic physics-look without a physics engine); staggered fly-ins (i\*4 frames, 40f expoOut); group rotates ~0.004 rad/frame; per-object breathe ≤0.006.
- Type stays 2D, enters soft (no stomp over serene 3D), with the standard text-shadow.

## Documentary mode (EXHIBIT)

For proof/evidence/product beats: single continuous scene (no beat swaps — documentary holds), asymmetric layout (dossier column left, evidence right), `MonoTag` exhibit numbers, `TypeOn` annotations (caps mono, faint), LineRig pointing from annotation to the detail, Ken Burns on the plate, one highlight sweep. Screenshots/photos get the same treatment as AI plates (key/crop → `public/assets/`).

## Archetype roadmap (recipes for scenarios not yet built)

When a script needs one of these, build it from the named ingredients — do NOT invent a new visual language:

| Scenario                                      | Recipe (system ingredients)                                                                                                             |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| DATA / CHART — a stat that matters            | bars/lines draw in machine-time (SVG pathLength like ProofCard border), `RollUp` values, Line becomes the trend line; one gold delta    |
| VS TABLE — us vs them                         | two columns, rows land as beats; theirs gets `Strike`, ours gets `CheckBadge`; never both visible before their beat                     |
| TIMELINE / ROADMAP — day 1 / 30 / 90          | horizontal canvas-mode variant: stations on a dated axis, WorldPath IS the timeline                                                     |
| STACK / OFFER — "everything you get"          | items stamp one per beat with gold FREE pills (v1 slide-25 style, beat-ified); ends in CTA card                                         |
| CTA END-CARD — every video's last 5s          | gold pill button + `TypeOn` URL + Line underlines the price; impact + shimmer; keep ONE variant reused everywhere                       |
| DEFINITION — introducing a term ("Operator")  | dictionary beat: word huge (LetterStamp), mono phonetics, definition types on; Line underlines the word                                 |
| HOOK / QUESTION — open loops                  | Verdict-mode variant with the question igniting nothing — withhold gold until the answer segment                                        |
| MAP / GEO — "operators in 40+ countries"      | dark dotted map plate + green `CheckBadge` pings (confirmation color)                                                                   |
| CHAPTER DIVIDER — YouTube retention structure | 2s beat: mono `01`, chapter title LetterStamp, Line sweep; chrome='full'                                                                |
| LOWER-THIRD / OVERLAY — over talking head     | `transparent:true` ProRes comps: name tag, one-liner captions, mini-Line underline; keep to bottom third                                |
| UI DEMO — product walkthrough                 | screen recording via `<OffthreadVideo>` inside a browser/phone frame (slide-13 style), LineRig pointing at features, mono labels typing |

## Voice & judgment (the taste layer)

- Every segment: ONE hero moment (an ignite, a slash, a reveal, a number). If a segment has two, split it.
- **The stomp is hero-only.** `LetterStamp aberrate` (chromatic split) + ImpactFlash + thock together = the stomp; reserve it for the segment's verdict/payoff moment — one, maybe two per segment. Supporting lines enter soft: `WordCascade`, `Rise`, or plain `LetterStamp` (aberrate defaults to false). If every line stomps, nothing does.
- Pain gets no color. Money always rolls. Red never emphasizes — it kills.
- **Run the mute test on every beat** before rendering: with the audio off, does the motion still say what the VO says? If the answer is "it looks premium but says nothing," the beat fails the Depiction Law — replace the visual with one that acts out the script phrase.
- When in doubt, remove words and enlarge what remains.

## How to use

1. **Read the script**, split into segments (one idea cluster each, 7–9s), then each segment into beats (~2s, one idea). Per beat, write the script phrase it covers and name what the visual DEPICTS from that phrase (Depiction Law — the mute test) before picking any move. Per segment decide: which archetype comp to copy, the ONE gold payoff (if any), what dies in red, what number rolls.
2. **Choreograph The Line first** — it's the spine. Write the `LineKeyframe[]` in ABSOLUTE comp frames: born → slash/underline (draw ~8–12f) → hold → release (collapse w→0 toward travel direction, `o:0`) → next station → final settle. Route travels AROUND text blocks (dive below), never through them. Beat-internal `at` values (LetterStamp/DimAt/SFX) are SEQUENCE-RELATIVE — keep a beat map comment reconciling both.
3. **Beats on a 6-frame overlap grid**: `from` = previous from + duration − 6; final beat gets `exit={0}` and ends exactly at `durationInFrames`.
4. **Impacts + SFX on landing frames**: `SegmentCamera impacts={[...]}` = `ImpactFlash at` frames = SFX hit frames. SFX placeholders live in `public/sfx/` (thock=stamp, slash=kill, riser=into payoff, shimmer=ignite) — place via `<Sequence from><Audio src={staticFile(...)} volume={0.4-0.9}/></Sequence>`.
5. **Register** in `src/Root.tsx` (1920×1080@30; 200–280 frames/segment), then verify cheaply before committing to renders:

```bash
cd /Users/zalo/dev/operator-broll
npx tsc --noEmit
npx remotion still <CompId> out/preview.png --frame=<slashOrPayoffFrame>   # inspect with Read
npx remotion render <CompId> out/<CompId>.mp4          # 1080p h264 + aac (SFX included)
# filmstrip to check motion arc:
ffmpeg -y -i out/<CompId>.mp4 -vf "select='not(mod(n,38))',scale=620:-1,tile=4x2" -frames:v 1 out/strip.png
```

6. **Delivery formats:**

```bash
# 4K upscale for YouTube masters
npx remotion render <CompId> out/<CompId>-4k.mp4 --scale=2
# Transparent overlay (graphics OVER talking head): transparent:true drops void/grid/orb/grain/vignette
npx remotion render <CompId> out/<CompId>.mov --codec=prores --prores-profile=4444 --image-format=png --pixel-format=yuva444p10le --props='{"transparent":true}'
# Verify alpha: ffprobe shows pix_fmt=yuva444p… (the "a" = alpha).
# Never set Config.setProResProfile in remotion.config.ts — it is global and breaks all h264 renders.
# Vertical 9:16: register a second Composition (1080x1920) on the same component with defaultProps={{scale: ~0.78}}
```

## Output shape

Report per segment: `✓ <CompId> — <duration>s → out/<CompId>.mp4` plus one inspected still per new comp. On render failure: comp ID + last 15 log lines, never the full log.

## Anti-patterns

- ❌ Decoration without depiction — a visual chosen because it "looks cool" rather than because it acts out the script phrase (the GlossClump lesson: 16 beautiful spheres that depicted nothing). Fails the mute test → doesn't ship
- ❌ Bouncy/elastic easing, overshoot, springs — the look this system exists against
- ❌ Slide-density in a beat: >5 words simultaneously, lists, side-by-side columns on mobile cuts
- ❌ The Line crossing through a text block while traveling — route below/around
- ❌ Mixing frame spaces: LineRig/ImpactFlash/camera impacts are ABSOLUTE; LetterStamp/DimAt/SFX-in-beat are RELATIVE to their Sequence
- ❌ More than one Ignite per segment; gold on non-payoff words; red for emphasis (red only destroys)
- ❌ Impact without reaction — every flash frame must also appear in `SegmentCamera impacts` and carry an SFX hit
- ❌ Rendering the full MP4 before inspecting a still
- ❌ TypeScript 7 in the studio — Remotion's bundler breaks; stay on typescript@5.x

## Edge cases

- **Long holds for VO** — extend the final beat; camera drift + live grain + orb breathing keep it alive.
- **New brand/series** — clone a theme in `tokens.ts` (accent/grid/bg only).
- **Music-synced cuts** — quantize beat `from` frames to the track BPM (frames-per-beat = 1800/BPM at 30fps); not yet a system helper.
- **Real SFX** — swap the ffmpeg-synthesized placeholders in `public/sfx/` for licensed hits; keep filenames.

## Pair with

- `seedance` — AI footage clips to intercut with these graphic segments
- `view-video` — frame-extract a rendered MP4 to verify motion
- `transcribe` — pull timing from a recorded teleprompter take to size segments
- `commit-with-heredoc` — commit studio changes after renders verify
