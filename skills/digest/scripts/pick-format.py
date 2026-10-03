#!/usr/bin/env python3
"""pick-format: choose the ONE extra (if any) that goes with the text answer.

Text is always the main output and goes first. This script decides whether an
extra goes with it: a diagram, an HTML page, or nothing. The agent decides
by itself with this rule and never asks Zalo which format he wants.

Usage:
  pick-format.py --lines N [--parts N --links N] [--steps N] [--timeline]
                 [--before-after] [--rows N] [--findings N] [--revisit]
                 [--kind KIND] [--repeats-text] [--json]

Counts describe the content, not the formatting:
  --lines      lines in the text answer you are about to send
  --parts      distinct things that connect (systems, stages, causes)
  --links      connections between those parts (arrows you would draw)
  --steps      ordered steps (a plan or a procedure; with --timeline, events in time order)
  --rows       rows of a comparison table
  --findings   separate findings or items (an audit, a review)
  --revisit    he will come back to it (a reference, a runbook, a plan to follow)
  --kind       status | yesno | fact | explain | report | plan | audit | compare
  --repeats-text   the extra would only repeat the text (vetoes any extra)

The rule (the same one SKILL.md states):
  text only      a status, a yes or no, one fact, or a text under 6 lines
  + diagram      3+ parts with 2+ links, a before and after, or a timeline of 3+ steps
  + html page    6+ findings, 8+ plan steps, a table over 6 rows, a 40+ line report,
                 or something he will come back to
  both shapes    one extra only: the page, with the diagram inside it
  any extra that only repeats the text is rejected

Prints the verdict (text | text+diagram | text+html) and the reason. Exit 0, or 2 on bad usage.
"""
import argparse
import json
import sys

TEXT_ONLY_KINDS = {"status", "yesno", "fact"}
KINDS = sorted(TEXT_ONLY_KINDS | {"explain", "report", "plan", "audit", "compare"})
MIN_LINES = 6


def pick(lines, parts=0, links=0, steps=0, timeline=False, before_after=False, rows=0,
         findings=0, revisit=False, kind="explain", repeats_text=False):
    out = {"verdict": "text", "reasons": [], "diagram_reasons": [], "html_reasons": [],
           "embed_diagram": False}
    if kind in TEXT_ONLY_KINDS:
        out["reasons"].append("a %s answer is text only" % kind)
        return out
    if lines < MIN_LINES:
        out["reasons"].append("the text is %d lines (under %d): text only" % (lines, MIN_LINES))
        return out
    if repeats_text:
        out["reasons"].append("the extra would only repeat the text: rejected")
        return out

    d, h = out["diagram_reasons"], out["html_reasons"]
    if parts >= 3 and links >= 2:
        d.append("%d parts with %d links" % (parts, links))
    if before_after:
        d.append("a before and after")
    if timeline and steps >= 3:
        d.append("a timeline of %d steps" % steps)
    if findings >= 6:
        h.append("%d findings to collapse" % findings)
    if steps >= 8 and not timeline:
        h.append("a plan of %d steps" % steps)
    if rows > 6:
        h.append("a table of %d rows" % rows)
    if lines >= 40:
        h.append("a long report (%d lines)" % lines)
    if revisit:
        h.append("a reference he will come back to")

    if d and h:
        out["verdict"] = "text+html"
        out["embed_diagram"] = True
        out["reasons"] = ["both shapes (%s; %s): one extra, the page with the diagram inside it"
                          % ("; ".join(d), "; ".join(h))]
    elif d:
        out["verdict"] = "text+diagram"
        out["reasons"] = d[:]
    elif h:
        out["verdict"] = "text+html"
        out["reasons"] = h[:]
    else:
        out["reasons"].append("no connected parts, no before and after, no long report: text only")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pick the extra format that goes with the text answer.")
    ap.add_argument("--lines", type=int, required=True)
    ap.add_argument("--parts", type=int, default=0)
    ap.add_argument("--links", type=int, default=0)
    ap.add_argument("--steps", type=int, default=0)
    ap.add_argument("--timeline", action="store_true")
    ap.add_argument("--before-after", action="store_true")
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--findings", type=int, default=0)
    ap.add_argument("--revisit", action="store_true")
    ap.add_argument("--kind", choices=KINDS, default="explain")
    ap.add_argument("--repeats-text", action="store_true")
    ap.add_argument("--json", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if min(a.lines, a.parts, a.links, a.steps, a.rows, a.findings) < 0:
        print("pick-format: counts cannot be negative", file=sys.stderr)
        return 2
    r = pick(a.lines, a.parts, a.links, a.steps, a.timeline, a.before_after, a.rows,
             a.findings, a.revisit, a.kind, a.repeats_text)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print("%s: %s" % (r["verdict"], "; ".join(r["reasons"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
