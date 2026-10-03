# Diagram specs (rung 2)

`node ~/.claude/skills/digest/scripts/diagram.mjs <spec.json> <out.png>` renders one of four
templates at 1080 px wide (phone first). A real example of each lives in `examples/`; copy the
closest one and change the content. Text fields accept `backticks` for ids and file names.

Common fields: `template` (required), `title` (required), `subtitle`, `footer` (sources),
`theme` (`dark` default, or `light`), `width` (default 1080), `legend` (`[{label, tone, dashed}]`).
Tones: `blue`, `green`, `yellow`, `red`, `grey`, `purple`.

## flow: a process, a pipeline, a root cause chain
```json
{ "template": "flow", "title": "...",
  "rows": [ [ {node} ], [ {node}, {node} ] ],
  "edges": [ { "from": "a", "to": "b", "label": "...", "tone": "yellow", "dashed": true } ] }
```
A node: `id`, `label`, `sub` (an id or a path, monospace), `detail` (one or two short sentences),
`chips` (a chain of short steps), `branches` (`[{when, then: [chips], note, tone}]` for an If/Else),
`items` (bullets), `tone`, `kind` (`gap` = dashed red, `note` = no fill, `end` = small box).
Rows go top to bottom; nodes in one row sit side by side (at most 2 or 3 on a phone). Numbers are
automatic (`"numbered": false` turns them off) and should match the numbered text you send.
Without `edges`, every node links to every node in the next row. That suits 1 to many, many to 1, and 2 by 2 rows; for bigger rows, list the `edges` you mean.

## sequence: who sends what, in time order
```json
{ "template": "sequence", "title": "...",
  "lanes": [ { "id": "a", "label": "Visitor", "sub": "phone", "tone": "purple" } ],
  "messages": [ { "from": "a", "to": "b", "label": "...", "detail": "...", "dashed": true } ] }
```
2 to 4 lanes. A message from a lane to itself is drawn as a note box.

## compare: before and after
```json
{ "template": "compare", "title": "...",
  "before": { "title": "Before", "sub": "until v6", "items": ["..."] },
  "after":  { "title": "After",  "sub": "v7, live", "items": ["..."] },
  "rowLabels": ["what row 1 compares", "..."], "verdict": "one line" }
```

## map: a system, which parts live where and what talks to what
```json
{ "template": "map", "title": "...",
  "zones": [ { "id": "ob", "label": "Operator Base", "sub": "...", "tone": "blue", "nodes": [ {node} ] } ],
  "edges": [ { "from": "cron", "to": "wf", "label": "3 events" } ] }
```
Keep zone titles short: an arrow cannot pass through a title, so a long title above the
leftmost node blocks the way in. Reorder the nodes when the checker says so.

## What the checker refuses
`diagram.mjs` exits 2 on a bad spec (missing id, unknown node, an em or en dash) and exits 1
after rendering when the layout has a defect: a label on a box or on another arrow, an arrow
through a box, two arrows on top of each other, a word broken across two lines, content wider
than the canvas, or a labelled edge that had to run down the side. Fix the spec (shorter words,
fewer nodes per row, reorder) and render again; never send a PNG from a run that exited 1.
