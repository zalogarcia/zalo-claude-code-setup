# Frontend Workflow (Opt-In) — on-demand reference

Demoted from always-loaded CLAUDE.md 2026-07-19 (zero invocations across a 37-session audit week). Read this when the work is genuinely UI-design-heavy: a new page, a component-library piece, a visual redesign. Skip for trivial copy/style tweaks or one-line CSS fixes.

## The pipeline

1. **Design** — Apply the `frontend-design` skill's principles (bold direction, anti-slop aesthetics, concrete palette and font pairing) while writing the code.
2. **Build** — For non-trivial implementation, use the `frontend-specialist` agent. It has scoped MCP servers for Aceternity UI and shadcn/ui. Apply Apple HIG-quality design principles (bold direction, anti-slop aesthetics, generous whitespace, clear hierarchy, no decoration without function).
3. **Verify** — Launch the `live-test` agent to screenshot and confirm it looks right in the browser.

This chain has been historically underused — don't force it for small changes. For full-page or component-library work, the full chain is high-value.
