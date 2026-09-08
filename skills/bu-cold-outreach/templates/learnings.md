# Learnings and Variant Scoreboard

Astra updates this file at the end of every session. It is the compounding asset: the
messages get better every week because of what is written here, and nowhere else.

## Variant scoreboard

The split test is the TIER OPENER crossed with the CHANNEL, plus the phrasing of the
"what we do" line (P1 or P2 from `templates/messages.md`). A variant id is
`<tier>-<channel>-<phrasing>`, for example `A-li-P1` or `D-ig-P2`.

Where each column comes from. **Sends** are counted from `sent-log.csv`, excluding rows
whose `stage` is `CONNECT`, because a connection request is not a message. **Replies**,
**positive** and **agreed to demo** come from the `pipeline.csv` stages, since a reply never
appears in the sent log: replies are rows that reached `REPLIED` or beyond, positive is
Astra's read of the recorded reply text, agreed to demo is a row Zalo advanced to
`DEMO_SENT`. A drafted message is not a send, and counting one corrupts every rate below
it.

| Variant | Sends | Replies | Positive | Agreed to demo | Reply rate |
| --- | --- | --- | --- | --- | --- |
| A-li-P1 | 0 | 0 | 0 | 0 | |
| A-li-P2 | 0 | 0 | 0 | 0 | |
| A-fb-P1 | 0 | 0 | 0 | 0 | |
| A-fb-P2 | 0 | 0 | 0 | 0 | |
| A-ig-P1 | 0 | 0 | 0 | 0 | |
| A-ig-P2 | 0 | 0 | 0 | 0 | |
| B-li-P1 | 0 | 0 | 0 | 0 | |
| B-li-P2 | 0 | 0 | 0 | 0 | |
| B-fb-P1 | 0 | 0 | 0 | 0 | |
| B-fb-P2 | 0 | 0 | 0 | 0 | |
| B-ig-P1 | 0 | 0 | 0 | 0 | |
| B-ig-P2 | 0 | 0 | 0 | 0 | |
| C-li-P1 | 0 | 0 | 0 | 0 | |
| C-li-P2 | 0 | 0 | 0 | 0 | |
| C-fb-P1 | 0 | 0 | 0 | 0 | |
| C-fb-P2 | 0 | 0 | 0 | 0 | |
| C-ig-P1 | 0 | 0 | 0 | 0 | |
| C-ig-P2 | 0 | 0 | 0 | 0 | |
| D-li-P1 | 0 | 0 | 0 | 0 | |
| D-li-P2 | 0 | 0 | 0 | 0 | |
| D-fb-P1 | 0 | 0 | 0 | 0 | |
| D-fb-P2 | 0 | 0 | 0 | 0 | |
| D-ig-P1 | 0 | 0 | 0 | 0 | |
| D-ig-P2 | 0 | 0 | 0 | 0 | |

Judgment rules:

1. No verdict on a variant under 20 sends. Under 20, report the count, never the rate,
   and say the sample is too small out loud.
2. Tier openers are not interchangeable. A tier A opener cannot be run on a tier D
   prospect, because the fact it opens with does not exist for them. So the tier rows
   compare tiers, not copy: the copy comparison is P1 against P2 inside a tier.
3. Phrasing split: alternate P1 and P2 within each tier and channel so the two stay
   within a few sends of each other. When one phrasing wins by a clear margin over at
   least 20 sends each, retire the loser on that channel and write ONE new challenger as
   P3 in the working copy of `messages.md`, changing one element only.
4. Positive replies break ties. Demos agreed beats both.

## Source performance

Which rails and signals actually produce repliers. Shift hunting time toward what converts.

| Source or signal | Sends | Replies | Reply rate | Note |
| --- | --- | --- | --- | --- |
| Tier A (hiring a CSR or front desk) | 0 | 0 | | |
| Tier B (paying an answering service) | 0 | 0 | | |
| Tier C (active Meta ads) | 0 | 0 | | |
| Tier D (no signal, side note only) | 0 | 0 | | |
| maps rail | 0 | 0 | | |
| linkedin rail | 0 | 0 | | |
| Phoenix | 0 | 0 | | |
| Dallas-Fort Worth | 0 | 0 | | |
| Tampa | 0 | 0 | | |

## Learnings log

One dated line whenever something is actually learned. Winning hooks, dead angles, which
metro bites, which owner titles reply, what an objection revealed, what a platform did.

- YYYY-MM-DD, example shape: "Tier A LinkedIn replies at roughly 3x tier D on the same
  day's batch; the job post opener is doing the work, not the phrasing."

## Warning and platform events

Mirror of the warning lines in `config.md`, with what Astra did about it.

- YYYY-MM-DD HH:MM ET, channel, what the screen said, action taken, ramp state after.

## Objections heard, verbatim

Owner language is the raw material for the ads phase. Log the words, not a summary.

- YYYY-MM-DD, tier, channel: "their exact words"
