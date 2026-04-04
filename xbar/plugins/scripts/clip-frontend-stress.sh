#!/bin/bash
printf '%s' 'Front End Stress Test: Read the full implementation first.

Then systematically try to break every user-facing flow. Think like a hostile user, a confused user, and a user on 3G — all at once.

Inputs & Data:

Empty submits, null/undefined, wrong types (string where number expected, object where string expected)

Extreme lengths, special characters (<script>, '\'' OR 1=1, unicode, emoji)

Boundary values: zero, negative, one, max, max+1, decimals where integers expected
Timing & Sequence:

Rapid repeated clicks/submits (double charges, duplicate entries?)

Back button, refresh mid-flow, bookmark a state-dependent page

Skip steps, repeat steps, go backwards through a multi-step flow

Two tabs open, same action fired simultaneously

Failure & State:

API returns 500, times out, returns malformed JSON, returns empty

Auth token expires mid-session, permissions change between page load and action

Stale data — user acts on data that another process already changed

What state survives a page refresh? What shouldn'\''t survive but does?

Scale & Display:

Zero items, one item, 1,000 items — does the UI hold up?
Content 10x longer than expected, missing/broken images
Viewport extremes and slow connections
For each finding: what breaks → root cause → severity (critical/high/medium/low) → suggested fix.

This is a full on stress test

Run the full report by me before making any changes' | pbcopy
