# Apple HIG Design Standards

> Actionable design standards for frontend developer agents. Each entry: **Outcome** (the UX goal), **Why** (the cognitive reason), **What** (the concrete rule with implementation specs). Synthesized from 27 Apple HIG pages.

---

## Accessibility & Inclusivity

**Never rely on a single channel to convey meaning**

- Outcome: Everyone perceives status and function regardless of ability.
- Why: ~8% of men are color blind; screen readers ignore visual-only cues; audio is unavailable in many contexts.
- What: Pair every color indicator with a shape, icon, or label. Pair every audio cue with a visual indicator. Provide captions/transcripts for all media.

**Meet contrast minimums — then exceed them**

- Outcome: Text and icons remain legible in all conditions.
- Why: Insufficient contrast is the most common accessibility failure; it compounds with glare and vision conditions.
- What: 4.5:1 minimum for text under 18px; 3:1 for 18px+ or bold. Aim for 7:1 on small text. Check in both light/dark modes and increased-contrast settings.

**Make tap targets generous and well-spaced**

- Outcome: People with limited dexterity reliably hit controls.
- Why: Small or crowded targets increase error rate for everyone.
- What: Minimum 44x44px. 12px padding between bordered elements, 24px between borderless. 60px minimum center-to-center.

**Support keyboard-only navigation**

- Outcome: The entire app is usable without a mouse or touch.
- Why: Motor disabilities, power users, and screen reader users rely on keyboard navigation.
- What: Every interactive element must be focusable and operable via keyboard. Never override standard shortcuts. Provide visible focus indicators.

**Provide a non-gesture alternative for every gesture action**

- Outcome: People who cannot swipe or pinch can still access all features.
- Why: Gesture-only interactions are invisible to switch control and keyboard users.
- What: Every swipe-to-delete, pinch-to-zoom, or long-press action must also have a button or menu alternative.

**Support user-controlled text scaling**

- Outcome: People can enlarge text to 200% without breaking layout.
- Why: Low vision is extremely common; people adjust text for comfort and context.
- What: Use rem/em, not fixed px. Test at largest text size. Switch horizontal layouts to vertical stacks when text grows. Allow multi-line labels — minimize truncation at large sizes.

**Avoid time-dependent dismissals**

- Outcome: Everyone has enough time to read, understand, and act.
- Why: Cognitive processing speed varies widely; assistive tech users need extra time.
- What: Prefer explicit dismiss actions over auto-dismiss timers. If a timer is necessary, let users extend or disable it.

**Respect "reduce motion" preferences**

- Outcome: People prone to vestibular disorders can use the app safely.
- Why: Rapid, large-scale, or bouncing animations can cause dizziness or seizures.
- What: When OS prefers reduced motion: replace slide/zoom/bounce with fades, remove parallax. Never flash faster than 3 per second.

**Simplify flows for cognitive accessibility**

- Outcome: Complex workflows are usable by people with cognitive disabilities.
- Why: Multi-step, multi-choice screens overwhelm users with limited working memory.
- What: Break multi-step flows into one action per screen when possible. Identify core functionality and strip non-critical UI for simplified modes.

---

## Color & Theming

**One color, one meaning**

- Outcome: Color communicates consistently and people learn your visual language fast.
- Why: Reusing the same color for different purposes creates ambiguity.
- What: Reserve accent/brand color for interactive elements. Define a semantic color system (interactive, success, danger, muted) and apply it consistently.

**Every custom color needs four variants**

- Outcome: The interface looks correct in all appearance modes.
- Why: Colors that work in one mode often fail in another.
- What: For each custom color: light default, dark default, light increased-contrast, dark increased-contrast. Use semantic tokens that adapt automatically.

**Color meaning varies by culture**

- Outcome: Your app communicates the intended message globally.
- Why: Red means danger in Western cultures but prosperity in Chinese culture.
- What: Verify color associations for target locales. Consider letting users customize signal colors.

**Inherit system appearance and preferences**

- Outcome: The app matches the user's chosen theme and never duplicates OS-level controls.
- Why: Users expect every app to follow system settings; app-specific overrides feel broken and create confusion.
- What: Use adaptive color tokens that respond to the system setting. Test both modes. Never offer an app-level dark/light toggle or recreate OS preferences (font size, accessibility) inside your app.

**Dark mode is not color inversion**

- Outcome: The dark palette is intentionally designed.
- Why: Simple inversion produces wrong contrast, saturation, and brightness relationships.
- What: Dim backgrounds (not pure black unless OLED). Brighter but slightly desaturated foregrounds. Elevated background tones for depth/layering.

**White backgrounds in content glow in dark mode**

- Outcome: Images with white backgrounds don't create harsh bright spots.
- Why: A white rectangle on a dark canvas creates jarring contrast.
- What: Darken or tint white-background images in dark mode. Subtle border or rounded mask for user-generated content.

**Avoid overlapping colors between content and control layers**

- Outcome: Controls remain legible over colorful content.
- Why: Colorful content scrolling beneath monochromatic controls (or vice versa) creates illegibility.
- What: Ensure sufficient contrast separation between content-layer colors and control-layer labels/icons. On translucent/glass surfaces, apply accent color to only one primary action per view.

---

## Typography & Hierarchy

**Use weight and size — not just size — to express hierarchy**

- Outcome: Users scan and instantly distinguish headings, body, and metadata.
- Why: Weight changes are perceptible at smaller increments than size changes.
- What: Define a type scale with deliberate weight progression. Match icon weight to adjacent text weight.

**Limit typefaces to maintain coherence**

- Outcome: The interface feels intentional and hierarchy is immediately readable.
- Why: Each additional typeface adds cognitive load.
- What: At most 2 typeface families. Differentiate via size, weight, and color — not font changes.

**Increase leading for long-form; tighten for constrained heights**

- Outcome: Multi-line text is easy to track without wasting space.
- Why: Wider columns need more spacing for the eye to return to the correct next line.
- What: Wide columns (>60ch): ~1.6-1.75x. Constrained UI: ~1.3-1.4x. Never tight leading for 3+ lines.

**Avoid light/thin font weights at small sizes**

- Outcome: Text remains legible across all devices and lighting.
- Why: Thin strokes render poorly on low-DPI screens and in bright light.
- What: Under 20px, prefer Regular weight or heavier.

**Prioritize primary content when scaling text**

- Outcome: Larger text sizes improve content readability without bloating chrome.
- Why: Users who increase text size want to read content, not inflate every label.
- What: Scale body text with user preference. Chrome/nav labels can stay fixed or minimally scaled. Keep primary content at top regardless of size.

---

## Icons

**Simplify to a single recognizable concept**

- Outcome: Icons communicate instantly without a label.
- Why: Detail-heavy icons become unreadable at small sizes.
- What: One visual metaphor per icon. Test recognition at 16x16px.

**Keep icon weight, size, and style consistent**

- Outcome: The icon set feels unified and professional.
- Why: Inconsistent weights/perspectives feel assembled from mismatched parts.
- What: Same stroke weight across all icons. Adjust dimensions for optical consistency.

**Use optical centering, not geometric centering**

- Outcome: Icons appear balanced even when asymmetric.
- Why: Human perception weights visual mass, not bounding boxes.
- What: Shift asymmetric icons (arrows, play) 1-2px toward the visual center of mass.

**Always provide accessible labels for icons**

- Outcome: Screen reader users understand every control.
- Why: An icon without a text alternative is invisible to assistive technology.
- What: Every icon-only button needs aria-label. Use action labels ("Delete") not descriptions ("trash can").

**Localize text in icons and support RTL**

- Outcome: Icons with embedded text work globally.
- Why: Unlocalized text in icons confuses non-English users; LTR directional icons feel wrong in RTL.
- What: If text is essential in an icon, localize it. Provide RTL-flipped variants for directional icons.

---

## Layout & Spacing

**Place important content at the top and leading edge**

- Outcome: Users find key information immediately.
- Why: People scan in reading order; primary content elsewhere gets missed.
- What: Primary actions in top-left (LTR) or top-right (RTL). Progressive disclosure for secondary info.

**Group related items; separate unrelated ones**

- Outcome: Structure is visually obvious without reading every label.
- Why: Gestalt proximity — items close together are perceived as related.
- What: Whitespace, fills, or dividers to cluster related controls. Between-group spacing clearly greater than within-group.

**Extend content to fill the viewport**

- Outcome: The interface feels immersive rather than boxed-in.
- Why: Unused screen edges feel like wasted space.
- What: Content reaches all edges. Navigation floats above content.

**Design for the largest and smallest breakpoints first**

- Outcome: Layout adapts gracefully instead of breaking at edge cases.
- Why: Testing only middle sizes misses the constraints that cause failures.
- What: Build widest and narrowest first. Narrow: single-column. Defer switching to compact layout as long as possible during resize.

**Respect safe areas and system-reserved regions**

- Outcome: Content is never obscured by hardware or system UI.
- Why: Notches, rounded corners, and system bars vary by device.
- What: Essential content within safe area insets. Only decorative backgrounds extend beyond.

**Align elements to a consistent grid**

- Outcome: The interface looks organized and is easy to scan.
- Why: Alignment creates implicit visual lines; misalignment adds noise.
- What: Base unit of 4px or 8px. All spacing, padding, and sizes as multiples.

**Avoid placing controls at the bottom of resizable windows**

- Outcome: Controls remain visible when windows are partially offscreen.
- Why: People often drag windows so the bottom is hidden below screen edge.
- What: Place essential controls in the top or middle of windows, not the bottom.

---

## Motion & Animation

**Every animation must have a purpose**

- Outcome: Motion communicates feedback, transition, or spatial relationship — not decoration.
- Why: Gratuitous animation distracts, slows users, and can cause discomfort.
- What: Identify what information the animation conveys. If "none", remove it.

**Keep feedback animations brief — skip them for frequent interactions**

- Outcome: Users get instant confirmation without waiting.
- Why: Long animations block interaction; even purposeful animation annoys when repeated constantly.
- What: Under 300ms. Let users interrupt to proceed. Omit animation entirely for frequently repeated interactions.

**Motion follows the user's mental model**

- Outcome: Transitions feel natural and reinforce spatial understanding.
- Why: If a panel slides in from the right, users expect to dismiss it rightward.
- What: Match dismiss direction to reveal direction. Consistent patterns for same navigation type.

---

## Materials, Depth & Translucency

**Glass/translucent materials belong in the control layer only**

- Outcome: Users understand foreground vs. background; hierarchy is clear.
- Why: Translucent materials connect floating elements to content beneath; using them in the content layer confuses hierarchy.
- What: Apply glass to navigation/control layers (toolbars, sidebars, popovers). Keep content layers opaque. Limit glass to the primary navigation shell — overuse creates visual noise. Exception: transient interactive elements like sliders.

**Choose material thickness based on content complexity**

- Outcome: Text over materials is legible; context through materials is visible when useful.
- Why: Thicker materials suit text-heavy overlays; thinner materials maintain background awareness.
- What: Thicker for alerts, popovers, text-heavy sidebars. Thinner for transient overlays.

**Vibrant/adaptive foreground colors on translucent surfaces**

- Outcome: Text on translucent surfaces stays readable regardless of background.
- Why: Static foreground colors lose contrast when background content changes.
- What: Use adaptive colors that maintain contrast. Apply label vibrancy hierarchy (primary > secondary > tertiary).

---

## Focus & Flow

**Use modals only for critical or narrowly scoped tasks**

- Outcome: Users stay in their task without losing context.
- Why: Context-switching destroys working memory and flow state.
- What: Keep modal tasks short and single-path. Never nest modals. Title every modal to help users keep their place. Never stack — close one before showing another.

**Modals always have an obvious, safe exit**

- Outcome: Users can always escape without losing work or feeling trapped.
- Why: A modal with only "Done" feels coercive; accidental data loss creates distrust.
- What: Every modal has a visible dismiss action. Cancel on leading edge, Done on trailing. If closing could discard user content, confirm with explicit save/discard options. Support swipe-to-dismiss on touch.

---

## First Impressions & State Restoration

**Show usable content instantly**

- Outcome: Users reach usable content with zero delay.
- Why: Every second before interaction increases abandonment.
- What: Show the primary interface immediately. Skeleton placeholders matching the final layout — never a branded splash screen. Do not advertise or brand on launch screens. Preload critical assets so large downloads never block first use.

**Resume exactly where users left off**

- Outcome: Users don't re-navigate on return.
- Why: Forcing re-navigation signals the app doesn't respect their time.
- What: Persist and restore: scroll position, active view, open panels, form progress.

---

## Onboarding & Learning

**Users learn by doing, not reading**

- Outcome: Knowledge is acquired through interaction, not instruction screens.
- Why: Interactive learning has higher retention; walls of text get skipped.
- What: Contextual tips near relevant UI. If a flow is needed, keep it brief and skippable. Make skipped tutorials re-accessible from help or settings — never show again on launch, but keep findable.

**Start immediately with zero configuration**

- Outcome: Users get value before investing effort.
- Why: Setup friction before value delivery causes drop-off.
- What: Sensible defaults. Postpone non-essential setup until the user encounters the feature that needs it.

**Permission requests feel justified, not invasive**

- Outcome: Users grant permissions because they understand the benefit.
- Why: Cold prompts without context get denied and can't be re-asked easily.
- What: Request at the moment the user tries the feature. Explain the benefit in context. Never batch during onboarding unless the app can't function without them.

---

## Search

**One search, everywhere**

- Outcome: Users find anything from one place.
- Why: Multiple search entry points create confusion about what's searchable where.
- What: Single, prominent search location. Clearly display the current scope of the search. Offer scoped filtering within views but always a global option.

**Search feels fast and forgiving**

- Outcome: Users get results despite imprecise queries.
- Why: Typing is costly; imprecise queries are normal.
- What: Recent searches, suggestions, and completions as the user types. Provide a way to clear search history (privacy).

---

## Settings & Configuration

**Settings exist but rarely need visiting**

- Outcome: The app works well out of the box.
- Why: Every trip to settings is a task interruption; most users never change defaults.
- What: Optimize defaults for the majority. Place task-specific options inline where they take effect. Only app-wide, infrequently changed options go in a dedicated settings area. Make settings accessible via standard shortcuts (Cmd+Comma).

---

## Drag & Drop

**Support drag everywhere users expect it**

- Outcome: Direct manipulation works naturally.
- Why: Users will attempt it — failure feels broken, not unsupported.
- What: Always provide a non-drag alternative. Same container: drag = move. Across containers: drag = copy.

**Continuous feedback during drag**

- Outcome: Users feel in control during drag operations.
- Why: Without feedback, users can't predict what happens on drop.
- What: Translucent preview on ~3px of movement. Highlight valid targets. "Not allowed" on invalid ones. Auto-scroll containers. Animate failed drops back to source.

**Dropped content transfers cleanly**

- Outcome: Fidelity is preserved after drop.
- Why: Style corruption breaks trust.
- What: Accept the richest format supported. Offer multiple fidelity versions (e.g., rich text, plain text) so destinations pick the best. Apply destination styling. Keep dropped content selected. Show progress for slow transfers.

---

## Undo & Redo

**Multi-level undo with no arbitrary limits**

- Outcome: Users explore and experiment without fear.
- Why: Reversibility makes interfaces feel safe to learn.
- What: Support Ctrl/Cmd+Z and Shift+Ctrl/Cmd+Z. Make drag-and-drop undoable. Support batch undo for related incremental adjustments (e.g., a series of slider tweaks).

**Label what undo will do**

- Outcome: Users know the effect before triggering undo.
- Why: Blind undo causes accidental changes and frantic repeated undoing.
- What: "Undo Delete", not "Undo". After undo, scroll to and highlight affected content.

---

## Interaction Targets & Feedback

**Every interactive element has a visible response**

- Outcome: People know the app registered their input.
- Why: Uncertain feedback makes people doubt their action worked.
- What: Press/active state on every button. Hover states on pointer devices. Inline activity indicator for async actions (e.g., button becomes spinner).

---

## Visual Hierarchy of Actions

**One prominent action per view**

- Outcome: People instantly identify the most important action.
- Why: Too many prominent elements increase decision time.
- What: 1-2 filled/accent buttons per view max. Use visual weight (fill, color) — not size — to distinguish primary from secondary. Primary on trailing side. Use style, not size, to differentiate buttons in a set.

**Destructive actions are visually cautious**

- Outcome: Destructive actions are not accidentally triggered.
- Why: People sometimes click the most prominent button without reading.
- What: Never make destructive button primary/default. Red styling only when destruction was NOT the user's intent. Always pair with Cancel. Confirm on trailing side, cancel on leading.

---

## Button & Control Labels

**Specific verb labels, not generic**

- Outcome: People understand consequences before acting.
- Why: Vague labels ("OK", "Submit") force re-reading context.
- What: Specific verbs ("Erase", "Add to Cart"). Title-case. Start with a verb. "OK" only for informational alerts. Prefer "Duplicate" over "Save As" to clarify original/copy relationship.

**Icon-only controls must be unambiguous**

- Outcome: Controls are understood without experimentation.
- Why: Novel icons require trial-and-error; familiar ones are faster than text.
- What: Established icons for standard actions. Tooltips on hover. If no standard icon exists, prefer text. In toolbars, bare icons without circular borders.

**Ellipsis signals a follow-up dialog**

- Outcome: People know when a control opens additional input.
- Why: Unexpected modals feel disorienting.
- What: Append "..." to any label that requires more input before executing.

---

## Navigation Structure

**Tab bars navigate; toolbars act**

- Outcome: People always know where they are and how to get back.
- Why: Mixing navigation and actions in one component causes disorientation.
- What: Tab bars/sidebars for section navigation. Toolbars for actions on current content. Never mix. Keep tab bars visible (except under modals). Never disable or hide tabs — show empty states instead.

**Navigation scales with complexity**

- Outcome: Navigation grows gracefully without overwhelming.
- Why: Overloaded navigation forces hunting; too little hides features.
- What: Tab bar for up to ~5 sections. Sidebar for more. Limit sidebar depth to 2 levels. Let users customize navigation items.

**Tab labels are single words with icons**

- Outcome: Tabs are scannable and predictable.
- Why: Multi-word labels compete for space.
- What: Single-word labels. Both icon and text. Filled icons for selected state. Badges sparingly, only for critical new info.

---

## Toolbars & Action Bars

**Three-section toolbar layout**

- Outcome: Items are discoverable without clutter.
- Why: Crowded toolbars make items hard to distinguish.
- What: Leading: navigation. Center: common actions. Trailing: primary/search/overflow. Overflow into "More" as width shrinks. Visually separate text-labeled items from icon items with fixed space to avoid them looking like a combined control.

**Consistent placement across contexts**

- Outcome: People find the same action in the same place.
- Why: Inconsistent placement forces re-learning per screen.
- What: Back/close always leading. Done/Save always trailing. Identical groupings across breakpoints.

**Every toolbar action is reachable another way**

- Outcome: No action is lost when toolbars hide or overflow.
- Why: Toolbars can be hidden, customized, or overflow.
- What: Mirror every action in a menu, shortcut, or contextual menu.

---

## Sheets & Modal Dialogs

**Proportionate modality**

- Outcome: Interruptions match their importance.
- Why: Unnecessary modals break flow and teach people to dismiss without reading.
- What: Sheets for scoped subtasks. Full-screen modals for complex multi-step tasks. Never stack sheets. Non-modal panels for repeated input-and-observe cycles.

**Always pair Done with Cancel**

- Outcome: People can escape without committing.
- Why: A modal with only "Done" feels coercive.
- What: Cancel leading, Done trailing. Support swipe-to-dismiss. Confirm if dismissing loses unsaved work.

**Multi-step sheet navigation**

- Outcome: Multi-step flows feel navigable, not trapping.
- Why: Without progress signals, people don't know how many steps remain.
- What: Step 1: Cancel + disabled Done. Middle: Back replaces Cancel. Final: Done activates. Never Cancel, Back, and Done simultaneously.

**Include a visible grabber on resizable sheets**

- Outcome: People know the sheet can be resized; VoiceOver users can access the resize control.
- Why: Without a visual affordance, resize behavior is undiscoverable.
- What: Show a drag handle/grabber at the top of bottom sheets and resizable panels.

---

## Alerts & Action Sheets

**Alerts are rare and therefore taken seriously**

- Outcome: When an alert appears, people read it.
- Why: Frequent alerts train people to dismiss without reading.
- What: Only for info requiring immediate action/decision. Never for informational messages, undoable actions, or app-launch announcements. Never display more than one alert at a time.

**Alert text scannable in under 3 seconds**

- Outcome: People understand situation and options instantly.
- Why: People read alerts under stress; dense text gets skipped.
- What: Title: 1-2 lines, what happened + context. Body: only if it adds info. Buttons: 1-2 word verbs ("Erase", "Keep Editing"), not "OK"/"Yes"/"No". Never let alert text scroll.

**Use action sheets for choices; alerts for critical info**

- Outcome: The right dialog type matches the situation.
- Why: Alerts demand attention for critical info; action sheets offer choices after a deliberate user action.
- What: Alert = the system needs to tell the user something critical or get a yes/no decision. Action sheet = the user initiated an action and needs to choose between options (e.g., save/discard/cancel when closing a draft).

---

## Text Fields & Input

**Size fields to match expected input**

- Outcome: People correctly estimate how much to type.
- Why: Physical size sets implicit length expectations.
- What: Single-line for short values. Text area for long content. Stack vertically with consistent widths and labels.

**Validate early and explain clearly**

- Outcome: Errors are caught before submission.
- Why: Delayed validation wastes effort.
- What: On blur for format. Real-time for constraints. Correct input type/keyboard. Clear button in trailing edge.

**Persistent labels, not just placeholders**

- Outcome: People always know what a field is for.
- Why: Placeholder text vanishes on focus.
- What: Placeholder for format hints only. Persistent label outside the field. Tab order follows visual sequence.

---

## Progress Indicators

**Determinate when possible**

- Outcome: People can estimate wait time.
- Why: Unknown duration feels longer; indefinite waits feel broken.
- What: Determinate when you can estimate duration. Switch from indeterminate as soon as possible. Keep animation moving — frozen looks like a crash.

**Accurate, trustworthy pacing**

- Outcome: Progress feedback matches reality.
- Why: A bar that jumps to 90% then stalls feels deceptive.
- What: Smooth to roughly linear. Describe specific steps if valuable. Let users cancel; warn if cancellation loses progress.

**Consistent indicator style**

- Outcome: Visual continuity during operations.
- Why: Switching spinner to bar mid-operation is disruptive.
- What: Spinner for background/inline. Bar for foreground waits. Never switch mid-operation.

**Auto-refresh content; don't rely on manual refresh**

- Outcome: Content stays current without user effort.
- Why: Making users responsible for every update adds unnecessary friction.
- What: Perform automatic content refreshes periodically. Pull-to-refresh is supplementary, not the only mechanism.

---

## Toggles & Binary Controls

**Unambiguous state at a glance**

- Outcome: On/off is obvious without interaction.
- Why: Similar-looking states cause confusion.
- What: Multiple cues: fill + position + icon. Never color alone. Toggle buttons change background between states.

**Right control type for the interaction**

- Outcome: People understand the control model before interacting.
- Why: Wrong control types lead to trial-and-error.
- What: Switches for on/off. Checkboxes for options in a group (support mixed/indeterminate state for parent checkboxes governing children). Radio buttons for 2-5 mutually exclusive choices.

---

## Sliders & Continuous Input

**Pair sliders with text fields for precision**

- Outcome: Both coarse and precise input are possible.
- Why: Sliders alone are imprecise for wide ranges.
- What: Text field + stepper alongside slider. Tick marks for discrete steps. Label min/max. Real-time feedback.

**Slider direction matches expectations**

- Outcome: No reversed-directionality errors.
- Why: Reversed direction causes repeated mistakes.
- What: Horizontal: min leading, max trailing. Vertical: min bottom, max top. Icons at ends to reinforce.

---

## Menus & Commands

**Every function is discoverable and keyboard-accessible**

- Outcome: No hidden commands.
- Why: Hidden commands are invisible to keyboard users and hard for everyone to learn.
- What: All commands in menus, even rare ones. Disable (never hide) unavailable items. Standard shortcuts. Ellipsis for dialog-opening items.

**Standard menu order across apps**

- Outcome: Predictable structure reduces scanning time.
- Why: Familiar ordering builds cross-app muscle memory.
- What: App > File > Edit > Format > View > [Custom] > Window > Help. Title-case. One-word titles. Custom menus between View and Window.

**Modifier-key items enhance, never gate**

- Outcome: Power users get shortcuts; others aren't blocked.
- Why: Hidden variants are undiscoverable by default.
- What: Always provide an alternative visible path. Single modifier key per dynamic item.
