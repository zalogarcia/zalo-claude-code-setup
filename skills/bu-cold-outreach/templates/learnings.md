# Learnings and Variant Scoreboard

Astra updates this file at the end of every session. It is the compounding asset: the
messages get better every week because of what is written here, and nowhere else.

## Variant scoreboard

The split test is the TIER OPENER crossed with the CHANNEL, plus the phrasing of the
"what we do" line (P1 or P2 from `templates/messages.md`). A variant id is
`<tier>-<channel>-<phrasing>`, for example `A-li-P1` or `D-ig-P2`. Since 2026-09-12 the
phrasing slot also carries the Facebook trade joke opener, `J1` / `J2`, with its two asks.
`N1` (the LinkedIn note with no pitch) was retired on 2026-09-22 when connection requests
stopped carrying notes; its rows stay as history.

**One message per prospect since 2026-09-22.** Every row after that date is one prospect,
one message, and the J arm is one bubble. Report the J rows sent as three bubbles
(2026-09-13 to 2026-09-22) as their own cohort, `D-fb-J1 (3 bubbles)` and `D-fb-J2 (3
bubbles)`, and never pool them with the one message rows: the shape changed, so the rate
did too.

Where each column comes from. **Sends** are counted from `sent-log.csv`, counting ONLY rows
whose `stage` is `SENT`. A `CONNECT` row is an invitation, not a delivered message. A
historical `SENT_CONT` row is the second or third part of a pre 2026-09-22 multi part first
touch, and a historical `BUMP1` or `BUMP2` row is a retired bump; counting either would
count one prospect twice. **Replies**, **positive** and **agreed to demo** come from
the `pipeline.csv` stages, since a reply never appears in the sent log: replies are rows
that reached `REPLIED` or beyond, positive is Astra's read of the recorded reply text,
agreed to demo is a row Zalo advanced to `DEMO_SENT`. A drafted message is not a send, and
counting one corrupts every rate below it.

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

The joke arm ids, added 2026-09-12, one message each since 2026-09-22. `D-fb-J1` and
`D-fb-J2` are live on tier D. `D-li-N1` and `C-li-N1` are retired (2026-09-22) and the lint
refuses them.

| Variant | Sends | Replies | Positive | Agreed to demo | Reply rate |
| --- | --- | --- | --- | --- | --- |
| D-fb-J1 | 0 | 0 | 0 | 0 | |
| D-fb-J2 | 0 | 0 | 0 | 0 | |

On LinkedIn the connection request has an ACCEPTANCE table of its own. Since 2026-09-22 the
request carries no note, so acceptance measures the profile and the channel, not the copy,
and the one message after the accept is scored in the reply columns.

| LinkedIn variant | CONNECT rows aged 14 days | Accepted | Acceptance rate | One messages sent after the accept | Human replies |
| --- | --- | --- | --- | --- | --- |
| D-li-P1 | 0 | 0 | | 0 | 0 |
| D-li-P2 | 0 | 0 | | 0 | 0 |

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
5. **The kill rule (Zalo, 2026-09-09).** A variant that reaches 20 sends on a channel
   with 0 replies is retired on that channel the same day, and its replacement changes
   ONE element (the opener type, the "what we do" line, or the dare) and gets its own id.
   1 reply in 20 is not a kill: report it and keep going to 40. On LinkedIn the two gates
   are judged separately, each against its own denominator, per rule 7.
6. **The second axis is the opener type.** `sent-log.csv` records `opener_type` and the
   full `message_text` for every send. The permitted values, revised 2026-09-12 to split
   the review quote bucket in two because the two halves argue in opposite directions, and
   to add the joke arm: `reachability failure`, `after hours praise`, `duties line`,
   `ad plus hours`, `hours gap`, `self made`, `trade joke`. Once any opener type reaches 20
   sends, report replies by opener type next to the variant table; the opener is expected
   to move replies more than the phrasing does.

   Rows logged before 2026-09-12 used `review quote` for both halves. Leave them as
   written; the audit trail is append only. The memo at
   `research/dylan-gigz-2026-09-12.md` records the split for those 25 rows: 23 after hours
   praise, 2 reachability failure.
7. **On LinkedIn the scoreboard has two tables, not one**, per the two gate rule in
   `SKILL.md`. An acceptance table (denominator: CONNECT rows aged 14 days or more) and a
   reply table (denominator: one messages actually sent after an accept, plus open profile
   messages and InMails). The kill rule in rule 5
   applies to each gate separately, against its own denominator. A variant with 20
   invitations still pending has NOT reached 20 sends for kill rule purposes, and a zero on
   the acceptance gate is never reported as a copy failure while the reply gate has no
   traffic: nothing was delivered, so nothing was read.
8. **One prospect is one send.** Since 2026-09-22 every prospect gets one message, so a
   prospect is one `SENT` row. The historical multi part rows (the J arm's `SENT_CONT` rows
   of 09-13 to 09-22, the 2026-09-08 Geo entry) and the `BUMP1` and `BUMP2` rows count
   nowhere; counting the parts is how the Geo entry briefly read as two prospects.

### Facebook group posts (channel NOT STARTED)

The one number this channel produces is **calls to the demo number per post**, which is not
a reply rate and does not belong in the variant scoreboard above. One row per post.

| Date | Group | Metro | Variant | Calls to the demo number | Booked by the agent | Removed by admin |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

No verdict under 20 posts: report counts, not rates. The creator numbers behind this play
(77 calls and about 15 closes from one post) are a CLAIM from a video that ends in a done
for you pitch, and they are not the target this table is read against.

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
| (one row per metro present in prospects.csv, added on first send) | 0 | 0 | | |

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
