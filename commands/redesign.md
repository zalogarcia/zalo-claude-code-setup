Redesign an existing UI through collaborative brainstorming, mockup generation, implementation, and visual verification.

## Instructions

### Step 1: Gather Context (USER CHECKPOINT)

Ask the user:

- What page/component needs redesigning?
- What's wrong with the current design? (pain points, outdated look, UX issues)
- Any inspiration, references, or design direction in mind?
- Any constraints? (must keep certain elements, brand colors, framework, etc.)

If the user already provided this info, skip asking and proceed.

**This is the only time to gather the user's main idea. After this, execute autonomously — only pausing to show generated images.**

### Step 2: Brainstorm with Frontend Agent (2+ Loops, Autonomous)

**Before brainstorming, capture the current state:** Launch a `live-test` subagent to take screenshots of the current page/component as it exists now. Save these screenshots to a known path (e.g., `/tmp/redesign-current-state/`). These screenshots will be passed to the frontend agent as visual reference so it understands what it's redesigning.

Run at least 2 rounds of brainstorming with the `frontend-specialist` subagent — do NOT loop the user between rounds. The agent handles this internally:

**Loop 1 — Exploration:**

- Review the current-state screenshots from `/tmp/redesign-current-state/` — read them as image files so you can see the actual UI
- Propose 2-3 distinct redesign directions with different aesthetic approaches
- For each direction: describe the visual concept, layout changes, typography, color palette, key interactions
- Evaluate trade-offs between the directions

**Loop 2 — Refinement:**

- Launch the `frontend-specialist` agent again, passing it the proposals from Loop 1
- The agent picks the strongest direction (or combines the best elements) based on the user's original brief
- Refines it into a concrete design spec: exact layout, component hierarchy, spacing, colors, fonts, animations
- Identifies technical challenges or component needs
- Produces a final design brief

The output of this step is a complete design spec. Proceed directly to Step 3.

### Step 3: Generate Draft Mockup Images (USER CHECKPOINT)

Generate **3 distinct design options**, each rendered on **both** image generators (6 images total). The 3 options MUST come from the brainstorming phase and each MUST be a genuinely different design proposal with its own aesthetic philosophy, layout approach, color palette, and style — NOT just color variations or minor tweaks of the same design.

For each of the 3 options, launch **two `image-craft-expert` subagents in parallel** (6 agents total, all in parallel):

1. **Option A — Gemini Pro**: `nano-banana "Option A prompt" --model pro -s 2K -o draft-optionA-gemini`
2. **Option A — ChatGPT**: OpenAI `gpt-image-1.5`, size `1536x1024`, save to `draft-optionA-chatgpt.png`
3. **Option B — Gemini Pro**: `nano-banana "Option B prompt" --model pro -s 2K -o draft-optionB-gemini`
4. **Option B — ChatGPT**: OpenAI `gpt-image-1.5`, size `1536x1024`, save to `draft-optionB-chatgpt.png`
5. **Option C — Gemini Pro**: `nano-banana "Option C prompt" --model pro -s 2K -o draft-optionC-gemini`
6. **Option C — ChatGPT**: OpenAI `gpt-image-1.5`, size `1536x1024`, save to `draft-optionC-chatgpt.png`

Each option's prompt should:

- Describe that specific design direction's exact layout, colors, typography, spacing, and key UI elements
- Specify the viewport/resolution (desktop, mobile, or both)
- Request a realistic UI mockup, not an abstract illustration

**Show ALL SIX generated mockup images to the user**, organized as 3 pairs (Option A: Gemini vs ChatGPT, Option B: Gemini vs ChatGPT, Option C: Gemini vs ChatGPT). Ask the user which option they prefer and which rendering (Gemini or ChatGPT) better captures the direction. They can also combine elements across options. Wait for user approval before proceeding.

### Step 4: Implement the Redesign (Autonomous)

Launch the `frontend-specialist` subagent for implementation:

- Provide the approved design spec from Step 2
- Provide the mockup image from Step 3 as visual reference
- Include paths to all existing files that need modification
- Instruct the agent to match the mockup as closely as possible
- The agent must read `~/.claude/projects/-Users-zalo/memory/apple_hig_design_principles.md` before writing code
- Apply `/frontend-design` skill principles (anti-slop, bold direction)

The agent implements the code changes. Proceed directly to Step 5.

### Step 5: Generate Final Mockup Image (USER CHECKPOINT)

After implementation, generate a polished final mockup of the **chosen option only** using the **same image generator the user chose in Step 3**. If the user picked a ChatGPT rendering, use ChatGPT here. If they picked Gemini, use Gemini here. Do NOT generate on both — use only the one that matches the user's Step 3 choice, since the verification target must be consistent with the original reference.

- Generate a polished final mockup that represents what the redesign SHOULD look like at pixel-perfect quality
- Use the refined design spec and any adjustments made during implementation
- This image serves as the verification target for Step 6

**Show the generated final mockup image to the user.** Wait for user approval before proceeding.

### Step 6: Visual Verification Against Mockup (Autonomous)

Launch the `live-test` subagent to verify the implementation:

- Take a screenshot of the actual rendered page/component
- Compare the screenshot against the final mockup image from Step 5
- Identify any visual discrepancies: spacing, colors, fonts, alignment, missing elements, animation states
- Report specific differences with file paths and CSS properties to fix

If discrepancies are found, launch the `frontend-specialist` agent to fix them, providing:

- The mockup image
- The screenshot of current state
- Specific list of differences to fix

After fixes, re-run the `live-test` agent to verify again. Repeat until the implementation matches the mockup.

### Step 7: Report

Summarize to the user:

- **Redesign concept**: the chosen direction and why
- **Key changes**: what was redesigned (layout, colors, typography, interactions)
- **Files modified**: list of changed files
- **Verification result**: match quality against mockup, any remaining minor differences
- **How to verify**: URL or steps to see the redesign live

### User Checkpoints (Summary)

Only pause for user input at these moments:

1. **Step 1** — gather the redesign idea and constraints
2. **Step 3** — show draft mockup image, wait for approval
3. **Step 5** — show final mockup image, wait for approval

Everything else runs autonomously.

### Guardrails

- **Never skip the brainstorming phase** — minimum 2 loops with the frontend agent
- **Always generate a mockup image** before implementation — don't go straight to code
- **Always verify against the mockup** after implementation — don't skip visual QA
- **Stay scoped to the redesign** — don't refactor unrelated code or add new features
- **Preserve existing functionality** — the redesign is visual, not functional (unless the user requests functional changes)
- **If the dev server isn't running**, ask the user to start it before Step 6
- **Do NOT ask the user for feedback between brainstorming loops** — handle that autonomously
