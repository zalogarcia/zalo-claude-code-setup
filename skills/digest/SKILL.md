---
name: digest
description: Make an explanation easy for Zalo to digest. Text always comes first, in STE-lite (80% of ASD-STE100, checked by ste-lint.py). At most ONE extra goes with it, chosen by pick-format.py and never by asking him. The extra is an exact boxes-and-arrows diagram PNG (flow, sequence, compare, map) or a self-contained interactive HTML page. Use when you explain a system, a report, a plan or a result to Zalo, or he asks to "break this down", "make this easier to digest", "diagram this" or "show it as a page". Not for concept art or infographics (infographics), charts from data (dataviz) or explainer videos (not used).
---

Turn anything Zalo has to understand into text he reads in one pass. When the shape of the content earns it, add ONE extra (a diagram or a page) that saves him reading time.

Source: Karpathy, 2026-10-02: "ask for large, custom, discardable artifacts". Zalo's steer (2026-10-02, about 15:10 ET): "Main is always gonna be text as is the fastest". Pick the extras by usefulness and complexity. No videos.

## When to invoke

- Zalo asks you to explain, break down, summarize or "ELI5" a system, a flow, a report, an audit or a plan.
- He asks for a diagram, "as a page", "in HTML", or says something is hard to follow.
- A worker or a report hands back something long that you must relay to him. The relay text follows the card, with or without an extra.

Skip for: a one-line status, a yes or no, or a quick reply in chat. Those still follow the writing card, but they need no script.

## Step 1: the text (always, first)

1. Write it with the rules card: `~/.claude/skills/digest/ste-card.md`.
   Lead with the answer, and use short sentences, the active voice and numbered steps.
   Write ids exactly, and use no em or en dashes.
2. Lint it: `python3 ~/.claude/skills/digest/scripts/ste-lint.py draft.txt`. Exit 0 is clean. Exit 1 prints `L<line> <rule> <message>`. Fix the findings or accept one on purpose (the card's "80% part").
3. The text stands alone. The extra adds a shape; the text never says "see the diagram" for a fact.

## Step 2: pick the extra (you decide, never ask)

```bash
python3 ~/.claude/skills/digest/scripts/pick-format.py --lines 13 --parts 7 --links 6 --findings 1
# -> text+diagram: 7 parts with 6 links
```

Count the content, not the formatting:

- `--parts`: the things that connect. `--links`: the arrows you would draw.
- `--steps`: plan steps. With `--timeline`, events in time order.
- `--rows`: table rows. `--findings`: audit items.
- `--revisit`: he will come back to it. `--kind status|yesno|fact`: text only.

| The content | Verdict |
| --- | --- |
| a status, a yes or no, one fact, or a text under 6 lines | text only |
| 3+ parts with 2+ links (a flow, a pipeline, a system, a root cause chain), a before and after, a timeline of 3+ steps | text + diagram |
| 6+ findings, a plan of 8+ steps, a table over 6 rows, a report of 40+ lines, or a reference he will come back to | text + page |
| both shapes at once | one extra only: the page, with the diagram inside it |
| the extra would only repeat the text (`--repeats-text`) | text only |

Report the verdict line in your reply to the orchestrator. Zalo sees the result, not the rule.

## Step 3a: the diagram

```bash
node ~/.claude/skills/digest/scripts/diagram.mjs spec.json out.png
# -> diagram: out.png 1080x3247 (flow), html out.diagram.html, clean      (exit 0)
```

- Copy the closest example from `templates/examples/` (`flow`, `sequence`, `compare`, `map`) and change the content. The spec reference is `templates/README.md`.
- Headless Chrome typesets every word from the spec, so the text is exact. Each PNG is 1080 px wide with 30 px+ body text, and it reads on a phone. Dark is the default theme; `"theme": "light"` also works.
- Exit 1 means a layout defect: a label on a box, an arrow through a box, or a word broken across lines.
- Exit 2 means a bad spec, including an em or en dash.
- After exit 1 or 2, fix the spec and render again. Never send a PNG from a run that exited 1.
- Make the node numbers match the numbered steps in your text.
- Keep it under about 2560 px tall when you can. Telegram shrinks taller photos, and 3300 px still reads.

## Step 3b: the page

- Start from `templates/examples/page.html`. Replace the content and keep the kit: tokens, signal trace, tap-to-open steps, Play/Next/Back, `<details>` and the header.
- Use the `frontend-design` skill for the visual pass.
- The page must earn its place. Collapse the detail, the ids and the "how to fix" part into it. Do not repeat the text.
- Keep it to one self-contained file: inline CSS and JS, system fonts, no CDN, no network calls.
- The page travels alone, so a sibling file breaks on his phone. To show the diagram PNG inside the page, write `<img src="out.png">` in `page.src.html`. Then run `python3 ~/.claude/skills/digest/scripts/inline-assets.py page.src.html page.html`. It turns local images, stylesheets and scripts into inline data, and the source copy stays editable.
- Gate it, which also takes the phone screenshot:

```bash
node ~/.claude/skills/digest/scripts/page-check.mjs page.html page.phone.png
# -> page-check: PASS page.html (17 KB), 7 of 7 tap controls and 2 of 2 sections open, screenshot page.phone.png 1170x2532
```

  It fails on these:
  - a script, stylesheet, image or iframe that points at the web or at a sibling file, or a CSS `url()` or `@import` outside the page;
  - `fetch`, XHR or an import in a script, any network request at load or on tap, or a missing phone viewport;
  - an em or en dash in the visible text, or a page error at 390 px;
  - an `aria-expanded` control or a `<details>` section that does not open on tap.
- Do not host it. Vercel or any public URL is a deploy and needs Zalo's go. If he wants links instead of files, propose a host in your report and wait.

## Step 4: send it, text first

```bash
S=~/.claude/skills/digest/scripts
python3 $S/send.py --text draft.txt --photo out.png --caption "The flow, numbered like the text."
python3 $S/send.py --text draft.txt --document page.html --shot page.phone.png --caption "Tap a step to open it."
```

`send.py` sends the text first, then the one extra. It prints a JSON line with the `message_id` for each send; report those ids.

- It refuses two extras, dashes, and text that fails the lint (`--allow-lint-findings` overrides; say why).
- It refuses while the shared Telegram cooldown is active.
- Captions go as `--form-string`, and it never calls an edit method.
- `--dry-run` checks the plan without sending.

## Rung 4, explainer video: not used

Karpathy's top rung is a narrated "3b1b style" explainer video. We do not use it, because it costs too much usage (Zalo, 2026-10-02). Do not build one unless he asks for it by name.

## Which skill does what

- `digest` makes exact boxes and arrows, and pages, where every word is typeset from text you wrote.
- `infographics` makes illustrative concept art and educational one-pagers as gpt-image-2 images.
- `dataviz` makes charts whose numbers must be exact, from data.
- `machine-editorial-broll` makes branded motion graphics for videos.

## Anti-patterns (each one happened while this skill was built)

- ❌ Writing the diagram's working HTML as `<name>.html` next to a page called `<name>.html`. The first demo run overwrote the page. `diagram.mjs` now writes `<name>.diagram.html`.
- ❌ Trusting a render because it "looks fine" at thumbnail size. The map example had arrows through a zone title, a word split as "onboardin g-api", and two arrows on one line. Each passed a glance, and each is now a checker warning.
- ❌ Global `white-space: nowrap` on buttons in a page. It also hit the step headers, which are buttons, and clipped their text at 390 px. Look at the phone screenshot every time.
- ❌ Sending the diagram and the page together "to be safe". That doubles his reading. One extra, picked by the rule.

## Files

| Path | What it is |
| --- | --- |
| `ste-card.md` | the writing rules card (linked from both CLAUDE.md files) |
| `scripts/ste-lint.py` (+ `.test.py`) | the text lint |
| `scripts/pick-format.py` (+ `.test.py`) | the extra-format rule |
| `scripts/diagram.mjs`, `templates/diagram.css`, `templates/diagram.js` | the diagram renderer and its layout checker |
| `scripts/render.mjs` | zero-dependency Chrome screenshot (DevTools protocol, Node's built-in WebSocket) |
| `scripts/page-check.mjs` | the page gate and phone screenshot |
| `scripts/inline-assets.py` (+ `.test.py`) | pulls local images, CSS and JS into a page |
| `scripts/send.py` (+ `.test.py`) | text-first delivery to Telegram |
| `scripts/visual.test.mjs` | tests for the diagram, page and render scripts |
| `templates/examples/` | one real spec per template, plus the reference page |

Run all the tests:

```bash
cd ~/.claude/skills/digest/scripts && python3 ste-lint.test.py && python3 pick-format.test.py && python3 send.test.py && python3 inline-assets.test.py && node visual.test.mjs
```

## Pair with

- `telegram`: the cooldown and caption rules that `send.py` follows.
- `frontend-design`: the visual pass on a page.
- `infographics` and `dataviz`: see the section above on which skill does what.
