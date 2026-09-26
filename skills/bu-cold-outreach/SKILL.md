---
name: bu-cold-outreach
description: Run Black Umbrella's own cold DM outreach. Triggers "run today's cold outreach", "cold DM batch", "outreach replies", "bu outreach", "approve the batch and send", "outreach report". Astra executes it in the codex-bare Codex session with Computer Use, sending from Zalo's real LinkedIn, Facebook and Instagram accounts in Chrome, to HVAC and plumbing owner operators countrywide (whatever metros prospects.csv holds; tranche 1 is twelve Sun Belt metros plus a nationwide LinkedIn rail). Enforces ONE message per prospect until that prospect replies (no bumps, no multi part first touch, LinkedIn connection requests with no note, all checked by the batch lint against pipeline.csv and sent-log.csv), the message's four beats with no pitch and no link, the per channel caps, the ramp, the pacing, the stop on warning rule, and the approval mode in config.md. Not the course outreach-operator skill, which is for CMAA members sending by hand.
---

# Black Umbrella Cold Outreach

Zalo's own client acquisition rail, not a course deliverable. Astra runs it: it researches
each prospect in the browser, writes the ONE message that prospect will get, and sends it
from Zalo's real accounts. Zalo approves batches, makes the after hours mystery calls, and
owns every thread from the moment a prospect replies.

## One message per prospect, until they reply (Zalo, 2026-09-22)

**Read this before anything else in the skill. It outranks every older line below.**

Zalo's decision on 2026-09-22, after one prospect got four messages and never replied: a
single cold message per prospect. On LinkedIn he chose option A (connection requests carry no
note).

The rule:

1. **At most ONE outbound message per prospect until that prospect replies.** One message
   is one bubble. The first touch is never split into parts, never continued, never bumped.
   No bump 1, no bump 2, no takeaway, no "last one from me", no `SENT_CONT`.
2. **On any channel.** A prospect who got their message on Facebook gets nothing on
   LinkedIn or Instagram either, and a prospect whose LinkedIn connection note went out has
   had their message.
3. **LinkedIn connection requests carry NO note** (option A). After the accept, the prospect
   gets the one message, the same as every other channel. An accepted connection that never
   replies gets nothing further. A connection request that carried a note (every one sent
   before 2026-09-22) WAS that prospect's one message, so an accept on it gets nothing.
4. **A reply ends the rule for that prospect.** Any reply at all makes the row `REPLIED` and
   the thread is Zalo's, as it always was. Astra never types into it.
5. **No reply means `COLD`**, the terminal state: one message, no reply. A `COLD` row is
   never messaged again on any channel. If a reply ever lands on it, it becomes `REPLIED`.

**The mechanism is the lint, not this paragraph.** `scripts/note-lint.py` reads the batch's
`notes.json` together with `pipeline.csv` and `sent-log.csv` from the working folder and
refuses, with a non zero exit: a first touch in more than one part (two notes on one entry,
one prospect in two entries, any `part` field); a bump, takeaway or continuation by any name
(a `kind` other than `message` or `connect`, a `stage` of `BUMP1`, `BUMP2` or `SENT_CONT`,
the follow up phrases); a connection request with any note; and any message to a prospect
who already has an outbound message in `sent-log.csv`, or whose pipeline row is `SENT` or
`COLD` or has touches, or who replied, or who is `DEAD`. Only an `ALL PASS` from a run that
checked the history clears a batch to send; `--no-history` prints `COPY PASS` and exits 2.

Everything else that already worked stays inside that one message: no link, the Zalo
voice, the per channel caps, the ramp, the pacing, stop on warning, and approval mode.

The target is the owner operator of a 3 to 8 truck HVAC or plumbing company doing $1M to
$3M, anywhere in the US. He is off the tools, spends on ads or is
hiring office help, and every after hours call that hits voicemail is a service call or an
install he already paid to generate.

## The lane requirement

**This skill sends messages from Zalo's real social accounts. It requires the codex-bare
session, which runs without the macOS sandbox and has the Computer Use plugin, so it can
drive Chrome.**

Before the first tool call of a session, establish which lane you are in:

- **codex-bare**, Computer Use available, Chrome opens and shows a rendered page. Full
  session: research, draft, and send.
- **Sandboxed lane** (a `codex exec` background job, the bridge's `bg.mjs --engine codex`
  rail, workspace-write seatbelt). Chrome exits 134. **Refuse to send anything.** You may
  still read the working folder, read `prospects.csv`, write drafts from data already on
  disk, and write the batch file, but every entry stays `DRAFT`, nothing is appended to
  `sent-log.csv`, no pipeline row moves to SENT, and the report says in its first line
  that this was a draft only session in a sandboxed lane and which lane is needed.

Never work around the lane limit. Do not attempt to send through an API, a scheduler, a
platform automation feature, or any path other than typing in Chrome as Zalo.

Chrome in that profile is already logged into Zalo's LinkedIn, Facebook and Instagram. If
a channel shows a logged out state, that channel is not active for the session: say so and
work the others.

## Who does what

| Astra | Zalo |
| --- | --- |
| Reads config, pipeline, sent log, yesterday's batch and report | Sets `approval_mode`, the ramp start, the active channels |
| Runs the health checks and states the mode, ramp week and quota | Approves each batch while approval mode is on |
| Opens each inbox, reads replies, updates stages, records replies verbatim | Makes the after hours mystery calls that create tier B |
| Resolves owners and DM handles in the browser, re confirms evidence | Takes every replied thread: the demo, the link, the VSL, the call |
| Writes the batch file with finished messages, no tokens left in them | Fills `proof.md` if he wants a written record of claimable facts |
| Sends the ONE message per prospect, within the caps and the pacing, and nothing more until a reply | Fills the price fields in `call-one-pager.md` before the first call |
| Appends every send to `sent-log.csv`, updates the pipeline | |
| Writes and prints the session report | |

**Astra does not build demos, does not open the 1-Click Demo Generator, does not send demo
links, and does not answer objections.** The moment a prospect replies with anything at
all, including "it goes to voicemail", Astra stops on that thread: mark it REPLIED, record
the reply verbatim in the pipeline notes, and surface it at the top of the report under
"Replies for Zalo". He takes it from there. The one exception is a stop request, which
Astra marks DEAD immediately and permanently and also reports.

## Setup gates

Four checks at the start of the first session in a working folder, and cheaply re checked
every session after. Nothing sends until all four pass.

**Gate 1, the lane.** codex-bare with Computer Use, per the section above. Fail means
draft only, and say so.

**Gate 2, the channels.** At least one of LinkedIn, Facebook or Instagram is marked active
in `config.md` AND is logged in in this Chrome profile AND is an aged account: older than
about 6 months, real photo, a headline or bio that says what Zalo does. A brand new or
empty account sending cold DMs gets restricted fast and converts near zero. Fail on every
channel means stop and report; there is nowhere to send.

**Gate 3, `config.md` exists and states an approval mode.** Fail means the working folder
was never seeded: run the first run step below, then stop and ask Zalo to set the mode and
the ramp start date. Never assume `off`.

**Gate 4, `prospects.csv` exists and has rows not already in `pipeline.csv`.** Fail means
there is nothing to work: read replies, close out the day 7 rows, report, and say the seed
list is exhausted. Never generate prospects and never modify `prospects.csv`.

There is no demo gate, no booking gate and no VSL gate in this skill, because Astra does
not touch that half of the funnel. `proof.md` is optional context and blocks nothing.

## Working folder and files

```
~/Documents/Clients/Black Umbrella/Delta Division/AI Division/Cold Outreach/
```

| File | Owner | What it is |
| --- | --- | --- |
| `prospects.csv` | produced elsewhere | the seed list. **Astra never modifies it.** Read only, always. |
| `pipeline.csv` | Astra | one row per prospect ever touched. The working state. |
| `sent-log.csv` | Astra, append only | one row per message actually sent. The audit trail and the split test denominator. |
| `batch-YYYY-MM-DD.md` | Astra | today's send list, with the finished messages and a status line each. |
| `config.md` | Zalo | mode, channels, ramp, warning events, metros. |
| `proof.md` | Zalo | the facts he is allowed to claim. Optional. |
| `learnings.md` | Astra | variant scoreboard, source performance, learnings, objections heard. |
| `reports/YYYY-MM-DD.md` | Astra | the session report, also printed as the final message. |

**First run step.** For each of `pipeline.csv`, `sent-log.csv`, `config.md`, `proof.md` and
`learnings.md`: if it does not exist in the working folder, copy it from this skill's
`templates/`. Create `reports/` as an empty directory if it does not exist; there is no
`reports/` in `templates/` to copy. **Never overwrite a file that exists.** Say which
files were created and which were already there. `batch-YYYY-MM-DD.md` is written fresh
each session from `templates/batch.md` and is not part of the seeding step.

### `prospects.csv`, the contract

The header, exactly, in order:

```
prospect_id, source_rail, metro, city, state, business_name, category, website, domain, phone, google_maps_url, review_count, rating, size_flag, category_flag, franchise_flag, qualified, drop_reason, tier, tier_reason, meta_ads_active_count, meta_ads_offer, meta_ads_evidence, indeed_role, indeed_posted, indeed_evidence, multi_location, tech_signals, chat_widget, site_fetch, business_facebook_url, business_instagram_url, business_linkedin_url, owner_name, owner_title, owner_linkedin_url, owner_facebook_url, notes
```

Read by column NAME, after stripping surrounding whitespace from each header cell, so a
file written with or without a space after each comma both work. Never read by position.

- `source_rail` is `maps` or `linkedin`. Owner columns are filled for linkedin rail rows
  and empty for maps rail rows; Astra resolves owners for maps rows per batch in the
  browser.
- `tier` is `A` (hiring a CSR, dispatcher or front desk), `C` (active Meta ads) or `D`
  (passed the filters, no signal). **`B` never appears in this file.** Tier B means paying
  an answering service, and it is assigned only by Zalo after his after hours mystery
  call. It lives in `pipeline.csv`.
- The `*_evidence` columns are verbatim facts. Quote them, do not paraphrase them, and
  re confirm them live before using them, every time and whatever the tranche's age
  (hunting playbook, Step 1).
- `qualified` and `drop_reason` are the seed list's own filter verdict. Only work rows
  where `qualified` is true.

### `pipeline.csv`, the working state

```
prospect_id,business_name,metro,tier,channel,profile_url,owner_name,stage,last_touch,next_due,angle,side_note,demo_link,demo_views_last,touches,notes
```

`angle` is the variant id, `<tier>-<channel>-<phrasing>`, for example `A-li-P1`, or the lane
id `<tier>-li-O1` (open profile message) or `<tier>-li-I1` (InMail) for the two delivered
LinkedIn lanes added 2026-09-12. `touches` is how many messages Astra has sent to this row:
0 before the one message, 1 after it, and never more from 2026-09-22 on (rows touched before
then can read 2 or 3, which is history). `next_due` is empty on every Astra row: nothing is
ever due, because nothing is ever sent twice. `demo_link` and `demo_views_last` are Zalo's
columns; Astra reads them and never writes them. `notes` carries the reply text verbatim
once a reply lands.

**Stages.**

| Stage | Meaning | Whose |
| --- | --- | --- |
| `FOUND` | qualified, owner and channel resolved, no message sent yet (a pending friend request or a note-less connection request stays here) | Astra |
| `SENT` | the one message is out, no reply yet, fewer than 7 days ago. Nothing is ever due | Astra |
| `REPLIED` | any reply at all, including a no | Astra sets it, Zalo owns the thread |
| `DEMO_SENT` | Zalo built the demo and delivered the link | Zalo |
| `TESTED` | the prospect used the demo | Zalo |
| `VSL_SENT` | VSL handed off, no booking yet | Zalo |
| `CALL` | call booked | Zalo |
| `NO_SHOW` | booked, did not show | Zalo |
| `CALL_HELD` | call happened, no decision | Zalo |
| `CLOSED` | client won | Zalo |
| `COLD` | one message, no reply: 7 days passed, or the row was stopped by the 2026-09-22 rule. Terminal for Astra: never messaged again on any channel. A late reply makes it `REPLIED` | Astra |
| `DEAD` | said stop, not interested, or blocked | Astra sets it on sight, forever |
| `NO_CHANNEL` | qualified, no open DM path on any active channel | Astra |

`CONNECT` and `FRIEND` are not pipeline stages. They are values that appear only in the
`stage` column of `sent-log.csv`: `CONNECT` marks a LinkedIn connection request and `FRIEND`
a Facebook friend request (added 2026-09-12). Neither is a message, provided the connection
request carries no note, which since 2026-09-22 it never does. A prospect whose request is
pending stays at `FOUND` in the pipeline. A prospect whose connection request went out WITH
a note before 2026-09-22 already had their one message and is `COLD`.

**What is due, by stage.** Astra's only row is the first one, and it sends nothing.
Everything from `REPLIED` down belongs to Zalo, after a reply, and Astra never sends into it,
though it tracks the dates so the report can tell him what is due. The nudges and takeaways
in Zalo's rows are his conversation with a prospect who DID reply; the one message rule
governs prospects who have not, and it is the only rule Astra's rows follow.

| Stage | Due when | Action | If still nothing | Whose |
| --- | --- | --- | --- | --- |
| `SENT` | day 7 after the one message, no reply | move the row to `COLD`. Send NOTHING: no bump, no takeaway, no other channel | it stays `COLD` for good | Astra |
| `REPLIED` | immediately | surface in the report, do not answer | Zalo | Zalo |
| `DEMO_SENT` | 2 days, no movement | nudge | day 5, final, then `COLD` | Zalo |
| `TESTED` | as soon as he sees it | feedback opener, then the VSL | day 3, resend the VSL once | Zalo |
| `VSL_SENT` | 24 hours, no booking | did the video make sense | day 4 value, day 8 takeaway, then `COLD` | Zalo |
| `CALL` | day before and morning of | confirmation nudge | kills no shows | Zalo |
| `NO_SHOW` | same day | warm reschedule | day 2, then day 6 takeaway | Zalo |
| `CALL_HELD` | day 1 | recap with the exact offer discussed | day 4 their objection, day 10 takeaway | Zalo |

**There are no bumps (retired 2026-09-22).** A prospect who does not answer the one message
goes `COLD` and hears nothing else.

- Any stop request at any stage means `DEAD`, in that session, forever, on every channel.

### `sent-log.csv`, the audit trail

Since 2026-09-09 every row also carries `variant`, `opener_type` and the full
`message_text`, so the log is the ledger that answers "which message style works":
`learnings.md` rule 5 (retire a variant at 20 sends with 0 replies, change one element)
and rule 6 (report by opener type) are computed from it.

```
timestamp_et,channel,prospect_id,profile_url,stage,message_sha1,message_head,variant,opener_type,message_text
```

Append one row immediately after each message actually leaves, before starting the pacing
gap for the next one. `timestamp_et` is US Eastern, `YYYY-MM-DD HH:MM`. `message_sha1` is
the sha1 of the exact message body as sent. `message_head` is its first 80 characters,
with newlines replaced by spaces and any comma quoted per CSV rules.

**LinkedIn connection requests get a row too**, with `stage` set to `CONNECT` and
`message_sha1`, `message_head`, `opener_type` and `message_text` EMPTY, because since
2026-09-22 the request carries no note (option A) and nothing is typed. `variant` is the id
the accepted thread will carry (`<tier>-li-P1` or `<tier>-li-P2`). Count the `CONNECT` rows
from the last 7 days before sending any new request; they are the denominator for the 80 per
week limit. The 41 `CONNECT` rows written before 2026-09-22 DO carry the note in
`message_text`, and the lint reads each of them as that prospect's one message.

**Facebook friend requests get a row too (added 2026-09-12 on Zalo's written yes).** A
friend request carries no message and is not a cold first touch. Its row has `stage`
`FRIEND`, `channel` `fb`, the owner's PERSONAL profile URL, `variant` set to the id the
accepted thread will carry (`D-fb-J1`, `D-fb-J2` or the control id), and `message_sha1`,
`message_head`, `opener_type` and `message_text` empty, because nothing was typed. It counts
for pacing like every action typed in these apps, against `facebook_friend_requests_per_day`
in `config.md`, and against nothing else. It has its own accept gate: denominator is
`FRIEND` rows aged 14 days, numerator is accepts. An accepted request turns the row into a
deliverable: the one message (the J arm's single message or the control DM) goes into the
accepted thread and lands in Chats, past the spam filter, and only then is it a `SENT` row
and a cold first touch against the Facebook cap, on the day it is typed. A request pending 14 days is `NO_CHANNEL` on Facebook
unless another channel is open. Stop on the friend request warning exactly like the message
warning. A `FRIEND` row is never a delivered message and is a denominator nowhere except its
own accept gate.

**Open profile messages and InMails are `SENT` rows (added 2026-09-12).** A LinkedIn message
sent to an open profile, or by InMail, is a delivered first touch: `stage` `SENT`, `variant`
`<tier>-li-O1` (open profile) or `<tier>-li-I1` (InMail), counted against the LinkedIn daily
cap of 15 and never against the 80, in health check 1b's delivered denominator and never in
1a's acceptance denominator. The one message for these rows is the control DM shape from
`templates/messages.md`, the four beats in one bubble: the specific, the bridge, the what we
do line and the dare; it carries the P1 or P2 line like every control message and the batch
entry names which. The
three LinkedIn lanes share the one cap of 15: `CONNECT` rows plus `O1` rows plus `I1` rows on
a day never exceed 15. InMail is further capped by `inmail_credits_per_month` in `config.md`
(2 a day and 5 in the calendar month until Zalo writes the number). An InMail also carries a
subject line, which is part of the same one message, is not one of the four beats and is
not linted: the business name or the opening fact, no pitch, no link.

The lint knows the two lane ids (closed 2026-09-12, the same day the gap was written):
`scripts/note-lint.py` maps `O1` and `I1` to the pitch family, so a note for either lane is
linted in `notes.json` under its OWN id, `<tier>-li-O1` or `<tier>-li-I1`, and every control
check runs on the exact text about to be typed. The lint holds every LinkedIn text to 420
characters (since 2026-09-22 there is no 300 character invitation note, so every LinkedIn
text is a delivered DM), and it refuses either lane id on any channel but linkedin. The
`sent-log.csv` `variant` and the pipeline `angle` carry the same lane id. The text linted and
the text sent are the same string, checked by sha1 in the batch as usual.

**LinkedIn is a two gate funnel and each gate gets its own denominator (2026-09-12).** The
rule:

- **Gate 1, acceptance.** Denominator is CONNECT rows that have reached 14 days old.
  Numerator is acceptances. This is the LinkedIn number that matters first. Since
  2026-09-22 the request carries no note, so it measures the profile and the channel, not
  copy; the 41 requests sent before then carried notes and are read as their own cohort.
- **Gate 2, reply.** Denominator is delivered LinkedIn messages: accepted invitations that
  received their one message, plus open profile messages and InMails (added 2026-09-12,
  delivered on send). Numerator is human replies. This is the only LinkedIn number
  comparable to a Facebook or Instagram reply rate.

A CONNECT row is never counted as a delivered message, and an accepted invitation with its
one message sent is; so is an open profile message or an InMail, which is delivered on send
and skips gate 1 entirely (it sits in gate 2's denominator and in check 1b, never in gate
1). Report both gates side by side, always with their denominators, and
never blend them into one "reply rate". An invitation younger than 14 days belongs in
neither denominator: it is pending, not failed.

**One prospect, one `SENT` row (2026-09-22).** The one message is one row with `stage`
`SENT`, and it is the delivered send for that prospect in every count, every rate and the
scoreboard. The `stage` values Astra writes from 2026-09-22 on are `CONNECT` (no note),
`FRIEND`, `SENT` and `GROUP_POST`, and only `SENT` is ever a denominator (a `FRIEND` row is
the denominator of its own accept gate and of nothing else, and a `GROUP_POST` row of its own
calls per post read and of nothing else).

**`SENT_CONT`, `BUMP1` and `BUMP2` are history (retired 2026-09-22).** From 2026-09-12 to
2026-09-22 the `J` arm typed its setup, punchline and ask as three bubbles, logged as one
`SENT` row plus two `SENT_CONT` rows, and unanswered rows got `BUMP1` and `BUMP2` rows. Those
rows stay in the log, which is append only, and they are counted nowhere except by the lint,
which reads every one of them as proof that the prospect already had their message. Astra
never writes one again.

**`GROUP_POST` is the Facebook groups row (added 2026-09-14, channel NOT STARTED).** A post
in a group is not a message to a person: `prospect_id` is empty, `profile_url` is the
group's URL, `channel` is `fbg`, `variant` is the `<metro>-fg-G1` id. It is never a
delivered message, never a cold first touch, and never in a reply rate. It counts for
pacing like anything else typed in the app. Full shape in `config.md`.

**Count DISTINCT prospects, not rows.** Sends on a channel or a variant are the number of
distinct `prospect_id` values among its `SENT` rows. That is what keeps the historical
multi row prospects (the 2026-09-09 Geo entry, the J rows of 09-13 to 09-22) at one send
each.

**Two rows in the working log predate all of this and are corrected here, not rewritten,
because the log is append only:**

- `a5647b073a` (Geo, facebook, 2026-09-09) has TWO `SENT` rows, 10:45 and 11:20. They are the
  two halves of one message. Under the 2026-09-22 rule the second half would never have
  been sent. One prospect, one send.
- `f4e1c0f25e` (AJ's Air, facebook, 2026-09-09 10:56) went to a business PAGE,
  `facebook.com/AJsAirAC`. A page is not a channel, so it is excluded from every send count,
  every reply rate and the scoreboard. It stays in the file as the audit record of a rule
  violation, and an auto responder answered it, which is not a reply either.

So those three rows are ONE delivered owner message, not three. Any count that says
otherwise has read rows instead of prospects.

**Nothing counts as sent unless it is here.** The report's counts and the funnel use this
file as the denominator, not the batch file's status lines and not memory. Reply counts and
demo agreement come from the `pipeline.csv` stages, since a reply never appears in this
file.

Compute the hash in the shell rather than by hand:

```bash
printf '%s' "$MESSAGE" | shasum -a 1 | cut -d' ' -f1
```

## The daily loop

**A "Research block only" session (the 03:45 run, added 2026-09-26) does not run this loop
top down.** It reads `config.md` (a Facebook hold or a tripped health check recorded there
means it researches nothing), `pipeline.csv` and the research ledgers, then runs only the
research of Step 3 in the worklist order of `hunting-playbook.md` Step 2F.0, recovery list
first, writing each verified owner at `FOUND` as it goes, and stops at 05:20 ET. It opens no
inbox, runs no Step 1, 2 or 2b beyond the recovery list, drafts nothing, writes no batch and
sends nothing. Its rules are `hunting-playbook.md` speed default 2.

### 0. Read, check, state

Read `config.md`, `pipeline.csv`, `sent-log.csv`, yesterday's `batch-*.md` and yesterday's
report. Run the health checks. Then state, in the first lines of output:

- the mode (approval on or off),
- **one line per ACTIVE channel**, because each channel has its own ramp:
  the channel, its ramp week, its ramp ceiling, its cap, any hold on it, and today's quota
  after what already went out today; on LinkedIn the three lane numbers (invitations, open
  profile messages, InMail) and on Facebook the friend request number beside the cold
  quota. Show the arithmetic, do not just show the answer:
  `LinkedIn: ramp week 1, cap 15 across three lanes, invitations held at 10, 3 invitations
  and 1 open profile message sent today: invitations 7 left, open profile and InMail 4 left
  (15 minus the 10 invitations planned minus 1 sent), InMail at most 2 today and 5 this
  month while the credit count is unknown. Invitations 22 of 80 in the last 7 days.` and
  `Facebook: ramp week 1, ceiling 10, cap 10, no hold, 0 sent today, 10 left. Friend
  requests 10 a day, 0 sent today, 10 left.`
- the day's total, as the SUM of those per channel numbers, and the inactive channels named
  as inactive so a missing rail is never silent,
- any tripped health check, and which channel it halts.

There is no single shared ceiling. A channel that is held, reset or inactive takes
nothing away from the others, and no channel is ever allowed above its own cap in the
channel table of `config.md`.

If a health check has tripped, **stop producing a new batch**. Read replies, report the
trip with its numbers and the likely cause, and end the session there.

### 1. Replies first

Open each active channel's inbox in Chrome and read every reply on threads that are in
`pipeline.csv`, `COLD` rows included: a late reply to the one message is still a reply. For
each one:

1. Set the stage to `REPLIED` (or `DEAD` if it is a stop request).
2. Paste the reply verbatim into the pipeline `notes`. Do not summarize it, do not clean
   it up, do not correct its spelling.
3. Add it to the "Replies for Zalo" section of the report with the channel, the profile
   URL, the tier, the message that was sent, and the reply.
4. Send nothing.

**An auto-responder is not a reply (2026-09-09).** "Thanks for messaging us, we'll get back
to you soon" and its cousins arrive within seconds of a Facebook page message and come
from the page's settings, not a person. The row stays `SENT` (and goes `COLD` at day 7
like any other); do not mark it REPLIED, and do not count it in the scoreboard. A reply is
a human answering. It also does not open the door to a second message: an auto responder is
not a reply, so the one message rule still holds.

Also check for anything the platform says. A captcha, a "slow down" notice, a restriction
notice or an unusual login prompt is a warning event and is handled under the sending
rules. A single message that failed to deliver is NOT a warning event: a deactivated or
blocked account is a fact about that prospect, not about the sending account. Record it in
the notes, set the row to `NO_CHANNEL` if that was the only channel, and do not count it as
a send. Only escalate it to a warning event if the platform states a reason that is about
Zalo's account.

**Open Messenger folders by address, not by menu, and budget the stalls (added
2026-09-26).** That day browser control timed out on Facebook four times: the research tab
("Debugger unattached", then a homepage load that reset the browser, ending research about
16 minutes into its 45), and the approved send twice at the same step, before and after a
full Chrome relaunch, both on clicks in Messenger's settings menu on the way to Message
requests (`DOM.resolveNode` timed out after 10000 ms; "CDP operation exceeded its deadline
before command dispatch"). Nothing was sent. So:

1. Message requests and Spam are opened by typing their address into the tab, never through
   the settings menu. The addresses to try first are
   `https://www.facebook.com/messages/requests/` and
   `https://www.facebook.com/messages/filtered/`. Neither is confirmed on this account yet:
   the first session that lands on each list writes the address that worked into
   `learnings.md`, and a session that cannot reach one records that folder as unverified
   and moves on.
2. A stall is a browser tool timing out or losing its tab (a CDP deadline, "Debugger
   unattached", a navigation that resets the browser). One stall on a row or a folder gets
   one retry in a fresh tab, then the row or folder is left and recorded. Three stalls in
   one session end that session's browser work: every verified row goes into
   `pipeline.csv` (it should already be there), the ledger and the report are written with
   the stall count and times, and the session stops. Never click the same control a third
   time.
3. A folder left unverified is a line in the report, not a gate on the send pass. The send
   pass checks each recipient's own thread before typing, and that is the check the one
   message rule needs.

### 2. Day 7 close out

Date driven from `pipeline.csv`. Walk every `SENT` row and compare `last_touch` to today.
Seven days or more with no reply: set the stage to `COLD` and keep `next_due` empty. Draft
nothing and send nothing. There is no bump, no takeaway and no second channel for a prospect
who did not answer the one message, and the lint refuses one if it is ever drafted. Report
how many rows went `COLD` today.

### 2b. Rows already in the pipeline that are waiting

Walk every row at stage `FOUND`. These are rows Astra already researched and that never
went out: an approval mode batch Zalo did not approve, a row pulled for stale evidence, a
LinkedIn owner who had to be connection requested first, or a tier B row Zalo created after
his mystery call. Without this step they sit in `pipeline.csv` forever and Step 3 skips
them, because Step 3 only takes rows that are not already in the pipeline.

**First, the recovery list (added 2026-09-26).** Before walking the `FOUND` rows, read every
research ledger under `evidence/` from the last 7 days: each `research-ledger.json`, and
any `ledger.csv` or `root-research.json` a split session left beside it. Two kinds of row
come back into today's batch from there, whatever `hunting-playbook.md` speed default 9
says about held rows:

1. **A verified owner a session lost:** outcome `draft` (any case) and a `prospect_id` that
   is not in `pipeline.csv`. On 2026-09-24 a session verified seven Facebook owners between
   06:11 and 06:33 ET, stopped with no batch and no report, and none of them reached the
   pipeline; they were found only on 2026-09-26.
2. **A row held ONLY for the seed's `size_flag`**, which is not a hold (`hunting-playbook.md`
   Step 5, 2026-09-26), when its profile and composer were already verified.

Each costs one load, not a new research pass: open the recorded personal profile, confirm
the Intro or work field still names the business and a Message button is shown (the chat
itself is opened by the send pass, `hunting-playbook.md` Step 2F.4), write the row at
`FOUND` with `recovered from evidence/<path>` in `notes`, and draft it like any first
touch. A profile that no longer names the business, or shows no Message button, is held
with that reason. A tier A or C row on the list re confirms its evidence per Step 1 of the
playbook first. These rows count against today's number like any other.

**`FOUND` rows written by today's research block** (the 03:45 run, `hunting-playbook.md`
speed default 2) are drafted straight into today's batch: their profile was seen live today,
so they cost no research load here. The send pass re opens each profile before typing, as it
does for every row.

For each `FOUND` row:

- **Connection request pending on LinkedIn.** First read that row's `CONNECT` line in
  `sent-log.csv`. **If the request carried a note** (every request before 2026-09-22 did),
  the note WAS the one message: the row is `COLD` (set it if it still reads `FOUND`), an
  accept gets nothing, and only a reply moves it (to `REPLIED`). **If it carried no note** (option A, 2026-09-22), check whether it
  was accepted. Accepted with nothing said means the ONE message goes into today's batch,
  drafted and linted like any first touch: the control shape, P1 or P2 per the row's
  variant, from the research already in `notes`, re confirmed live the day it is drafted.
  Accepted with a reply is REPLIED and goes to Zalo. Still pending after 14 days means set
  `NO_CHANNEL` unless another active channel is open, in which case that channel takes the
  one message instead (a note-less request is not a message, so this is still the first).

  **While the profile is open, record two things in `notes`, because they are what make a
  pending invitation interpretable instead of just silent:** `last_activity: YYYY-MM-DD`
  from the profile's Activity tab (the most recent post, comment or reaction, or `none
  visible`), and `viewed_us: yes|no` from "Who viewed your profile". An invitee who viewed
  Zalo's profile and did not accept saw the request and said no, which is a profile signal
  (and, for the requests sent with a note before 2026-09-22, a copy signal). An invitee who never viewed it and has no activity in six months never saw
  anything, which is a channel signal. Report the two distributions in the session report.
  Without them, a pending invitation carries no information and zero acceptances cannot be
  diagnosed.

- **Friend request pending on Facebook (added 2026-09-12).** Check whether it was accepted.
  Accepted with nothing said means the one message this row was assigned (the J arm's single
  message or the control DM) goes INTO TODAY'S BATCH under today's approval, typed into the
  accepted thread; on the day it is typed it is a `SENT` row and a cold first touch against
  the Facebook cap. Accepted with anything said, one word or one
  emoji, is REPLIED and the thread is Zalo's. Still pending after 14 days means set
  `NO_CHANNEL` unless another active channel is open, in which case switch the channel and
  redraft. Record `friend_request: pending|accepted YYYY-MM-DD` in `notes` so the accept
  gate reads by send date.

- **A Facebook `J` row that went out as three bubbles before 2026-09-22.** It already had
  its one message (more than one, which is why the rule exists). It is `COLD` unless it
  replied. Nothing is finished, continued or re sent; the continuation marker is retired
  and the lint refuses it.
- **Pulled for stale evidence.** Re confirm per the hunting playbook. Live again means
  redraft. Still dead means demote the tier and open on a side note, or set `NO_CHANNEL`.
- **Tier B created by Zalo.** Draft the tier B opener from the answering service fact in
  `side_note`. These go first in the batch.
- **Anything else at `FOUND`.** Redraft it into today's batch. The research is already done,
  so it costs nothing but a re confirmation.

These rows count against today's quota exactly like new rows do.

### 3. Today's batch

Take rows from `prospects.csv` that are `qualified` and whose `prospect_id` is not in
`pipeline.csv` at a stage other than `FOUND`. A prospect who has EVER had a message from
Astra, on any channel, is never a row here again: the lint checks `sent-log.csv` and refuses
it. **Order: tier A, then B, then C, then D**,
the same order everywhere in this skill. Within a tier, prefer rows that already have an
owner resolved (the linkedin rail), then higher `review_count`. Tier B rows exist only in
`pipeline.csv`, never in the seed file, so they enter the batch through Step 2b below.
**For the Facebook number the name comes before the tier (2026-09-26):** work the rows in
the worklist order of `hunting-playbook.md` Step 2F.0 (recovered rows, then named rows of
any tier, then rows the owner resolver never read, then `no_owner_reason` rows last). An
unnamed tier C row is not worked ahead of a named tier D row: on 2026-09-26 a tier C first
pass spent the session on eleven rows the resolver had already found empty and drafted
none.

For each row, per `hunting-playbook.md` and inside its speed defaults (4 page loads and 5
minutes per prospect, 45 minutes of research per session, accessibility text not
screenshots, one quoted owner search, Indeed never opened):

1. Load the homepage once. Kill on size, franchise, commercial only or an AI chat widget;
   otherwise take the owner name if it is there and keep the homepage facts as side note
   material for Zalo, not as the opener.
2. Re confirm the sniper evidence from the seed row live, on every row whatever the
   tranche's age (Zalo, 2026-09-23: each prospect gets one message, so a stale fact
   wastes it), and spend one load on the specific the opener needs per the specificity
   law in `templates/messages.md`: the duties and shift line on the employer's own job
   posting (tier A, the same load confirms the post is still up), what the ad says plus
   the Google hours (tier C, with one Ad Library load to confirm the ad is still active),
   a review quote about the phone or the hours gap from the Google Business Profile
   (tier D). Dead or unconfirmable evidence means demote the tier or pull the row; never
   write around a fact that stopped being true.
3. Resolve the owner with one search. Ambiguous means hold. While
   `linkedin_daily_cold_ceiling` in `config.md` is 0, that one search is the Facebook
   people search `First Last City`, never `"Company" owner linkedin`
   (`hunting-playbook.md` speed default 6, 2026-09-26).
4. Pick the channel: LinkedIn when the owner profile exists, then the owner's PERSONAL
   Facebook profile (never the business page; a page is not a channel, Zalo 2026-09-09),
   then Instagram. **While `linkedin_daily_cold_ceiling` is 0 the order is Facebook
   first** (`config.md`: Facebook takes the research budget first): a closed LinkedIn
   profile has no lane that day, so research does not open LinkedIn profiles until the
   Facebook number is filled, except as a row's last load after Facebook refused it
   (Step 2F.5). Research loaded nine LinkedIn profiles 2026-09-23 to 09-26; the eight
   whose Message button it clicked were all closed.
   **On LinkedIn, check for an open profile before defaulting to the connection request
   (added 2026-09-12).** On most profiles the Message button opens a paid Sales Navigator
   prompt and the send is a connection request with NO note (option A, 2026-09-22), and
   the one message follows the accept. But a LinkedIn Premium
   member who has turned on Open Profile can be messaged free by anyone with no connection
   request, no accept and no wait, and the message lands in their main inbox. The check is
   one click during research: open the profile while not connected and see whether the
   Message button opens a free composer or an upsell (on mobile the button reads InMail but
   charges no credit). A free composer means the row is an open profile send, variant
   `<tier>-li-O1`, which skips the accept gate entirely and gets the one message now, in
   the control shape (the sent-log section above has the counting rules). Record `open_profile: yes|no` in the pipeline `notes` for EVERY LinkedIn row
   touched, open or not, so the share of open profiles in this ICP is measured on every
   row; between 5 and 40 percent of a general B2B list are open (Evaboot live export,
   2025-11-25, 40 of 100), and for HVAC and plumbing owner operators expect the low end and
   zero on some batches. A closed profile in tier A takes the InMail lane first
   (`<tier>-li-I1`, inside the credit cap). While the ramp hold is on, an invitation goes to
   tier D only (`config.md`, the LinkedIn ramp hold): a tier A or C row with a closed
   profile takes InMail or Facebook, and if neither is open it is held in the research
   ledger with the reason `tier reserved for delivered lanes` rather than invited.
   No channel on any active platform means `NO_CHANNEL` in the pipeline and take the next
   row.
   **Facebook is a real rail from 2026-09-13, not the occasional one off it has been.** It
   has its own ramp and its own quota, so a session works BOTH channels to their own
   numbers rather than spending the day on LinkedIn and getting to Facebook if there is
   time. Every Facebook row costs an owner personal profile resolution first, because the
   seed file carries 1,481 business page URLs and zero owner personal URLs: budget it per
   Step 2F of `hunting-playbook.md`, and a row whose personal profile cannot be verified
   has no Facebook channel. A business page URL in a batch entry is a bug, not a fallback.
   A resolved Facebook owner takes ONE of the two Facebook lanes on a given day, and the
   batch entry says which: the cold DM (the one message now, a `SENT` row against the cap)
   or the friend request (a `FRIEND` row now, against `facebook_friend_requests_per_day`;
   the one message, the J arm's or the control DM, goes into the thread after the accept,
   per Step 2b). Never both, and never the DM on one day and a friend request later: a
   prospect who got the DM has had their message. Friend
   requests are listed in the batch file under Facebook with a status line each and no
   `notes.json` entry, because there is nothing to lint, and they wait for Zalo's go like
   every other action. Miami rows go first on Facebook, for the delivery reason in
   `config.md`.
5. Write the finished message per `templates/messages.md`, every token filled. On the
   control the opener passes the paste test (if it could go to another company with the
   name swapped, it does not ship), the bridge clause ties it to the phones and the dare
   closes it. On the `J` arm the paste test is deliberately waived and the lint enforces
   the approved fixed copy instead, as ONE message: the joke and the ask in the same
   bubble. Every note goes through the gate in `templates/messages.md` before the batch
   file is written: read `templates/gold-notes.md` first, then `ALL PASS` from
   `scripts/note-lint.py` on the session's `notes.json` INSIDE the working folder, so it
   checks the one message rule against `pipeline.csv` and `sent-log.csv` (a `COPY PASS`
   from `--no-history` does not clear anything to send), then the humanizer pass (the
   skill at `~/dev/zalo-kabche-brand/.claude/skills/humanizer/SKILL.md`). The lint output
   goes in the batch header. Every entry in `notes.json` carries its `prospect_id`. A
   LinkedIn connection request is an entry with `"kind": "connect"` and an EMPTY text:
   there is no note to write, and the one message is drafted in the session that sees the
   accept (Step 2b). Open profile and InMail rows carry the one message now, in the control
   shape, inside the 420 character limit the lint applies to every LinkedIn text.
6. Append the row to the research ledger: id, seconds, page loads, outcome. A verified row
   also goes into `pipeline.csv` at `FOUND` right then, not at the end of the session
   (`hunting-playbook.md` Step 6, 2026-09-26: a session that dies keeps what it verified).

Stop researching when every active channel has hit its own number, or at 45 minutes of
research, whichever comes first, and say which. One 45 minute budget covers the whole
research session, not 45 minutes per channel. Since 2026-09-12 a day may run two sessions,
a research and resolution session and a send session, each with its own 45 minutes
(`hunting-playbook.md`, Speed defaults, rule 2); the send session types and paces only, and
every row it sends was drafted, linted and, on LinkedIn, checked for an open profile in the
research session. Since 2026-09-26 a research block runs before dawn as well (fired 03:45
ET, researching until 05:20, about 85 minutes, research only, rows written at `FOUND`, same
rule 2), so the 06:00 session's
45 minutes are for the rows the block and Step 2b did not already supply. Report the real
number per channel, and how many of today's Facebook rows came from the block, from the
recovery list and from this session.

Write `batch-YYYY-MM-DD.md` from `templates/batch.md`, grouped by channel, tier order
inside each channel. There is no bump section; there are no bumps.

**In approval mode, stop here.** Report the file path, how many drafts are waiting, and
the split by channel and tier. Send nothing until Zalo says go for that batch. His go
applies to that batch only; it does not change `config.md` and it does not carry to
tomorrow.

**Re lint immediately before the send pass, in either mode.** Run `scripts/note-lint.py`
on the exact `notes.json` of the batch about to be typed, right before the first message
goes, and again before resuming if any other batch has sent anything since. The lint only
sees the log as it stands when it runs: two batches drafted the same day can each carry the
same prospect and each pass on their own, and it is the re lint after the first one's sends
are logged that refuses the second (`OPEN-GAPS.md` #6). An entry the re lint refuses is
`PULLED, already messaged`, never typed.

**The send pass types and paces; it does not sweep inboxes (2026-09-26).** The day's 06:00
session already read the inboxes (Step 1), so the send pass does not open Message
requests, Spam or the settings menu again; on 2026-09-26 that repeat sweep is where both
approved send attempts stalled before a single message was typed. Per entry it opens the
recorded personal profile, clicks Message, waits for the thread, and checks that thread
for a prior bubble, a reply or a restriction ("You can't message this account", "can't
access this chat yet"). Any of those makes the entry `PULLED` with the reason; otherwise it
types, sends, logs and paces. The stall budget in Step 1 applies to the send pass too.

**Outside approval mode**, send down the list, and after every single send:

1. Append the row to `sent-log.csv`.
2. Update the pipeline row for a MESSAGE: stage `SENT`, `last_touch` today, `next_due`
   EMPTY (nothing is ever due), `touches` 1. A `CONNECT` (no note) or `FRIEND` row is not
   a message: the pipeline row stays at `FOUND` with the pending request in `notes`, per
   Step 2b.
3. Update the batch entry's status line to `SENT YYYY-MM-DD HH:MM ET`.
4. Wait a randomized 2 to 5 minutes before the next one:

```bash
sleep $((120 + RANDOM % 181))
```

### 4. Report

Write `reports/YYYY-MM-DD.md` from `templates/report.md` and print the same content as the
final message of the session, because M relays the final message to Zalo. The efficiency
block comes from the research ledger, not from memory. Update `learnings.md` in the same
step: the variant scoreboard from `sent-log.csv`, the source
table, any learning, any objection heard verbatim.

## What the evidence says does not work (added 2026-09-14)

**Read this before proposing a channel, and do not reopen one of these without NEW
evidence.** Source: `research/ai-agents-sales-2026-09-12.md` in the working folder, built
from 62,062 words of tagged notes across 22 transcripts and 597 fetched pages. The point of
this block is that a future session, M included, should not arrive in three weeks with
"what about cold email" as though it were an untried idea. It was tried, by other people,
at volume, and measured.

**The measured failures, each labeled DATA or CLAIM in the last column.**

| What was tried | What it produced | Type |
| --- | --- | --- |
| Cold email at scale | 1,097 sends, 11 replies, 1 positive, **0 paid, 0 attributable signups**, domain matched | DATA |
| Cold email at volume | 450 emails a day, nothing | CLAIM, the sender's own report against interest |
| Instagram cold DMs to trades | hundreds of DMs, 1 to 2% reply, **0 closes over 4 to 5 weeks** | CLAIM, the sender's own measurement |
| Cold SMS to businesses | not available at all: prior express consent plus A2P 10DLC brand and campaign registration. No seller in the sweep cold texts owners | DATA, carrier policy |
| Pitching in r/HVAC, r/Plumbing, r/Roofing | openly hostile, vendors identified by post history ("You know we can see your post history right?") | DATA |
| Marketplaces (Upwork, Fiverr) | price the BUILD at $10 to $100, not the outcome. Not a client channel for this offer | DATA |

The sweep's own summary of it: **the only measured client acquisition numbers in 62,000
words of notes are failures.** Every success number in the sweep is a claim, and 18 of the
22 creator videos end in a course, community, affiliate or done for you CTA.

**What actually produced the first paid work, in the seller communities.** A referral, a
warm contact, or a subcontract from an agency that already had the client. Named
independently by three seller threads, and it is the top ranked channel for speed in the
memo's own table. The member who closed $1,500 in five days did it that way, after 450 cold
emails a day had produced nothing. For us that means Delta Agents clients, CMAA students and
past Black Umbrella clients are a faster rail than any cold channel in this skill, and the
cold rail exists because it scales past a finite network, not because it is better.

**What this block does NOT say.** It does not say cold outreach is dead: the Facebook and
LinkedIn rails in this skill are running on their own measured gates, and the sweep's own
ranking puts Facebook groups and the after hours proof call above every channel in the table
above. It says these specific channels were measured to zero, and that reopening one needs a
number, not an argument. Instagram is the one with a nuance: it stays in `config.md`'s
channel table at `Active: no`, and turning it on is Zalo's call. This block does not make
that call for him; it makes sure the 1 to 2% reply to zero closes is the first thing anyone
proposing it sees.

## Sending rules, non negotiable

These protect accounts that cannot be replaced. A restricted LinkedIn account ends this
rail; there is no second profile and no workaround.

**Per channel daily caps.** LinkedIn 15 cold first touches a day across three lanes
(invitations, open profile messages, InMail) and 80 connection requests a week (invitations
only). Instagram 10 a day. Facebook Messenger 10 a day, plus a friend request number of its
own (`facebook_friend_requests_per_day` in `config.md`, 10 in week 1) that is not a cold
first touch. **35 a day maximum** with all three live, and there is no configuration that
produces more cold first touches. Adding a channel is the only way to raise the ceiling.

**A LinkedIn connection request IS a cold first touch and consumes a daily slot**
(2026-09-12). It is also the denominator for the 80 per week limit, so it is counted twice,
against two different budgets, and BOTH bind. There is no day on which LinkedIn actions exceed
that channel's daily number.
An open profile message or an InMail is a cold first touch against the same 15 and never
against the 80; it has no accept gate, so the ramp hold, which binds invitations, does not
reduce it (`config.md`, arithmetic step 6).

**The ramp, one per channel (restructured 2026-09-12).** Each ACTIVE channel carries its
own `ramp_start_date`, `ramp_week` and `daily_cold_ceiling` in `config.md`. Week 1 is 10
cold first touches a day on that channel. Week 2 is 20, and never above that channel's own
cap. Week 3 and after is that channel's cap. A channel advances only if ITS week had zero
warnings AND it has a measured delivery number: on LinkedIn, 20 CONNECT rows aged 14 days
so there is an acceptance rate; on Facebook and Instagram, 20 delivered owner DMs aged 7
days so there is a reply rate. Zero warnings is a safety condition, not a funnel condition,
and it is not enough on its own. On LinkedIn the ramp ceiling and its hold bind
INVITATIONS; the open profile and InMail lanes run inside the channel cap of 15 minus the
day's invitations (`config.md`, arithmetic step 6).

**A start date in the FUTURE means no ramp and no sends on that channel until that date**
(added 2026-09-12). `config.md` already says a missing or placeholder
`<channel>_ramp_start_date` gives that channel no ramp and no sends; a date that has not
arrived yet is the same state, and it is the normal way a channel is opened ahead of time.
The channel's quota is zero until the date, whatever its `ramp_week` and
`daily_cold_ceiling` fields say, and the session header prints the date it is waiting for:
`<channel>: not yet started, waiting for YYYY-MM-DD, quota 0`. A channel whose Active column
says yes and whose start date is in the future is CORRECTLY configured, not a contradiction,
and it is not held back by a prose line somebody has to remember to read.

Opening Facebook costs LinkedIn nothing, and a warning that resets Facebook leaves LinkedIn
where it was. The one exception
is two warning events on two different channels inside 7 days, which resets every channel
to week 1 and 10 a day, because that pattern is about how we are sending.

**The caps still bind absolutely.** The ramp can only ever lower a channel's number, never
raise it past the cap in the channel table. Today's number per channel is: zero if that
channel's `ramp_start_date` is missing, a placeholder, or a date still in the future,
otherwise the cap, reduced by an active hold, capped again by that channel's ramp ceiling,
then on LinkedIn also capped by what is left of 80 invitations in the last 7 days, then
minus what already went out today. On LinkedIn that result is the INVITATION number; the
open profile and InMail lanes then fill to the channel cap of 15 minus that number, never
touched by the 80, per `config.md` arithmetic step 6. State that arithmetic per channel in
the session header, including the date a not yet started channel is waiting for.

**A cold first touch is one prospect and ONE message (2026-09-22).** Every first touch, the
joke included, is one message, one bubble, one cold first touch against the daily cap and one
pacing gap.

**Messenger sends on Enter (2026-09-09).** A newline passed to the Facebook composer fires
Send mid message: entry 4 of the 2026-09-08 batch went out as the opener alone. Type
paragraph one, press Shift+Return twice, type paragraph two, then Send. Never pass a
string containing a newline to the composer. The J arm's message is one line with no
paragraph break at all, and the lint refuses a line break in it. **If a stray Enter ever
sends part of a message, the rest is NOT sent as a second bubble**: what left is that
prospect's one message. Log exactly what went out and report it.

**Pacing.** One message at a time, with a randomized gap of 2 to 5 minutes between sends.
Never a burst. Connection requests and friend requests count for pacing even though they
carry no message.

**Never a platform automation feature.** No bulk send, no broadcast, no message sequence,
no saved template feature, no third party sender, no browser extension. Type it and send
it, one at a time, like a person.

**Only Zalo's own accounts.** Never create an account, never rotate identities, never
suggest a second profile to raise the ceiling.

**Stop on warning.** At any captcha, "slow down", "you are sending too fast", restriction
notice or unusual login prompt: **stop that channel for the rest of the day immediately.**
Those five are the whole trigger list, and they are the same five in `config.md` and
`templates/batch.md`. A friend request block on Facebook (Meta blocks friend requests for
"a lot" in a short time, for unanswered ones and for ones marked unwelcome, and says the
block ends within a few days) is a restriction notice inside those five, not a sixth
trigger. Then, in the same session:

1. Write the event to the warning events block in `config.md`, `YYYY-MM-DD HH:MM ET |
   channel | what the screen said`.
2. Mirror it into `learnings.md` with the action taken.
3. Reset THAT channel's `ramp_week` to 1 and its `daily_cold_ceiling` to 10, **or to that
   channel's own week 1 number if that is lower**: Facebook groups' week 1 is 5, so a flat
   reset to 10 would DOUBLE its volume as the response to a warning. The other
   channels keep their own ramps, unless this is the second warning on a second channel
   inside 7 days, in which case every channel goes back to week 1 and 10 a day (again, or
   its own lower week 1 number).
4. Continue on the other channels only if they are clean.
5. Report it, prominently, in the session report.

**Escalation beyond the same day stop, and where it is remembered.** A same day stop is
not enough on its own, because the next session reads `config.md` and would send at the
full cap. So every escalation is written into the channel holds block of `config.md`, which
Astra maintains and reads before computing any quota:

- A captcha or a "slow down" halves that channel's cap for 7 days. Write
  `<channel> | cap 7 | until YYYY-MM-DD | slow down notice`.
- A formal restriction or temporary block stops that channel entirely for 7 days. Write
  `<channel> | stopped | until YYYY-MM-DD | restriction notice`.

A hold whose `until` date has passed is removed by Astra and reported as lifted. Zalo is
the only one who lifts a hold early. **Today's quota is the per channel cap, reduced by any
active hold, then capped again by THAT CHANNEL's ramp ceiling** (on LinkedIn that is the
invitation number; the delivered lanes fill to 15 per `config.md` step 6). State that
arithmetic per channel in the session header so a halved channel is visible rather than
silently applied.

**Honor every opt out instantly and permanently.** DEAD is DEAD, on every channel, forever.

**Be truthful about who is sending and why.** It is Zalo, offering his service. No
fabricated referrals, no invented mutual connections, no pretending to be a customer.

**Quality floor.** If the metro cannot produce enough researched prospects to fill the
quota, send fewer. Never pad a batch with an unresearched row.

## The Facebook groups channel (NOT STARTED, added 2026-09-14)

**This channel is `Active: no` with no start date and it does not run. Zalo opens it or it
stays closed.** It is written down now because the research named it the fastest channel
with evidence behind it after the warm network, and a channel nobody has specified cannot be
opened on a Tuesday afternoon without inventing its rules on the spot.

**The motion.** A post from Zalo's real personal Facebook profile into local business,
contractor and trade groups in the metros: the outcome opener, one line on what it does, the
dare, and the demo number. No link on the first post. The agent on the other end takes the
call and books the 15 minute call, which is the whole mechanic.

**It is not a DM rail and must not be counted as one.** A post is not a message to a person:
it costs no DM slot, it is not a cold first touch, it never enters a reply rate, and health
checks 1b, 2 and 5 do not see it. Its rows are `GROUP_POST` in `sent-log.csv` per
`config.md`. The one number it produces is calls to the demo number per post.

**Cap and ramp.** 5 posts a day in week 1, 10 from week 2, 10 is the cap. Posted BY A
PERSON, never automated, never scheduled through a tool. Full arithmetic and the log row
shape are in the Facebook groups section of `config.md`; the copy contract and the two
approved posts are in `templates/messages.md`; the lint holds a `<metro>-fg-G1` post to its
own laws on channel `facebook_groups`.

**Two gates before post one, both Zalo's, and the second one is the important one.** His
explicit go, and then: **he calls the demo number himself and interrupts it three times mid
sentence. If it ploughs on past a second, the play waits.** The buyers in the research state
this as their own purchase test ("cut across the bot mid sentence, see if it stops or ploughs
on"), and a group post hands that test to a room of strangers who will run it unsupervised
and post the result in the same thread.

**The evidence grade, honestly.** The MECHANIC is corroborated: four creators, two vendors
putting the number on their landing page, and the buyers' own "let me call it" checklist. The
VOLUME numbers are one creator's CLAIM (77 calls, 35 booked, about 15 closes from one post),
his video ends in a done for you pitch, and a second creator already repeats his copy word
for word, which reads as saturation rather than corroboration. **None of those numbers is a
target here.** The cadence is a cost we choose; the first read is calls per post, and if 20
posts produce near zero, the channel stops.

## The message system, in short

Full copy is in `templates/messages.md`. The shape that cannot change:

**One message per prospect, four beats, one bubble.** How you found him (a fact you can
see), why him (the specific thing you noticed about his business, with the bridge to the
phones), what we do in his language (answers calls and texts in about five seconds, 24/7,
books the job into the calendar), and the dare, a question he can answer in a word. No
pitch, no link, no meeting ask. It is the only message he gets unless he replies, so it has
to stand on its own; nothing follows it.

**Sell the outcome, never the technology as a category (the offer law, 2026-09-14).** The
product is an answered call and a booked job. The mechanism gets named once, in passing,
inside Zalo's own P1 or P2 line, and never becomes the thing being sold: "I help businesses
with AI receptionists" is the shape that fails. `P1_LINE` and `P2_LINE` already obey this
and do not change. Mechanical: `TECH_AS_CATEGORY` in the lint's `BANNED`, plus a positive
check that both halves of the outcome are named. Full law in `templates/messages.md`.

**After hours and overflow, never replacement (the position law, 2026-09-14).** We are not
replacing the person who answers at 9 a.m., on any channel, in any message. "I already have
someone at the front desk" is the most reported objection in the whole research sweep and it
ends the replacement pitch every time. Tier B is not an exception: it replaces a third party
ANSWERING SERVICE, which is a different thing and the highest willingness sale in the ICP.
The agree then narrow turn for the wall is written out in `templates/messages.md`.

**The bridge may hand him his own arithmetic, inside what the fact shows (2026-09-14).**
The research says the close is the owner's own missed call math, done in his head in about
four seconds. So a bridge can add up two posted times or count what a review itself says.
It can never invent his numbers: no money, no percentage, no calls per week, no "pays for
the year". The lint fails an invented rate and an ROI claim outright, and a money amount or
a percentage when it sits in the same SENTENCE as a result, which is what lets it keep
passing his own quoted promo price ("your $79 tune up ad is running right now"). It is a
gate, not a proof: a claim split across two sentences still gets through, and that residue
is named in `OPEN-GAPS.md` #4. Worked examples in `templates/gold-notes.md`.

**State facts you read, never claim research effort.** The one exception is the demo:
the one message DOES say a demo has been trained on his website and offers to send it
(Zalo's decision, 2026-09-08, restoring the course's champion angle), because Zalo generates
the demo in seconds when the reply lands. No link in it; the link comes after he replies,
from Zalo, in the same thread.

**No invented proof, numbers or urgency.** Astra's messages carry no numbers about results
at all. Nothing about a client appears unless Zalo wrote it in `proof.md` and authorized
it, and even then it is his to send, not Astra's.

**The tier opener is the split test.** Tier A opens with the job post. Tier B opens with
the answering service fact from Zalo's mystery call. Tier C opens with the ad plus the
after hours fact. Tier D opens with the strongest side note available. Inside a tier, the
"what we do" line alternates between phrasings P1 and P2, which is the copy comparison
that actually controls for the prospect.

**Match the channel.** LinkedIn warm and professional. Facebook and Instagram casual.
Short enough not to scroll on a phone.

**Volume before judgment.** No verdict on a variant under 20 sends. Under that, report the
count and say the sample is too small.

**One measured test arm runs beside the control, tier D only (added 2026-09-12).** It is
written in full in `templates/messages.md`, it is 20 sends against 20 sends of the control,
and it does not touch tier A, B or C.

- **`J1` and `J2`, the Facebook trade joke opener, ONE message since 2026-09-22.** An
  approved joke, setup then punchline, and the ask, all in one bubble, on the owner's
  PERSONAL Facebook profile. The split is the ask. Judged on replies at day 7. It is the one
  sanctioned exception to the specificity law, scoped to this arm, and it carries no demo
  claim at all. The 09-13 to 09-22 rows went out as three bubbles and are read as their own
  cohort, never pooled with the one message rows.
- **`N1` is retired (2026-09-22).** It was the LinkedIn connection note with no pitch, judged
  on acceptance. A connection request carries no note now, so there is nothing left for it
  to measure. The lint refuses the id.

**A second arm beside it: `FRIEND`, the Facebook friend request first (Zalo's written yes,
2026-09-12).** Not a copy arm: a friend request with no note, then the one message (the J
arm's or the control DM) into the accepted thread. Its numbers (`facebook_friend_requests_per_day`, its
ramp, its accept gate) live in the Facebook section of `config.md`, its rows are `FRIEND`
rows in `sent-log.csv`, and it is judged on ACCEPTANCE at 14 days first, then on replies at
day 7 on the messages it delivered. The batch entry names the tier and the message the
accepted thread gets; while the arm's accept gate has no 14 day number it is tier D only,
per the tier rule for friend requests in `config.md`.

**The joke arm sends nothing until Zalo has read its copy**: the six joke messages in
`templates/gold-notes.md`. That is a precondition on the arm, separate from the per batch
approval, and it holds even if `approval_mode` is ever off.

Both arms keep everything not named here: the four beats, the dare, the demo claim, the caps,
the pacing, the stop on warning rule, approval mode, and the law that Astra's messages carry
no numbers. And over all of it, the one message rule at the top of this file.

## Reading the numbers

The shape from the strategy: **100 messages, about 10 replies, about 3 real conversations,
1 booked call.** That is the yardstick until there are enough of Zalo's own numbers to
replace it, which is about 100 sends.

| Step | Broken | Below par | On shape | Good | If it is low, the fix is |
| --- | --- | --- | --- | --- | --- |
| Reply rate | under 2% | 2 to 5% | 5 to 12% | 12% and up | sharper evidence and a real side note, not more volume |
| Reply to conversation | under 10% | 10 to 20% | 20 to 40% | 40% and up | Zalo's rail: how fast the demo follows the reply |
| Conversation to booked call | under 15% | 15 to 25% | 25 to 40% | 40% and up | Zalo's rail: the demo, the VSL, the calendar |

**Read the funnel top down and name the FIRST step below par, and nothing after it.** Every
step below a break is starved of traffic, so its percentage is noise. A week with 4 replies
and 0 calls does not have a call problem.

**Small numbers lie.** Under about 20 sends on a variant, or under about 5 replies, report
counts, not rates, and say so out loud.

## Health checks

Run at the top of every session against `pipeline.csv` and `sent-log.csv`. **The last
column says what a trip halts: the whole session, one channel, or nothing.** A session halt
means no new batch is produced at all; replies are still read and the report is still
written. Astra does not run a diagnosis conversation and does not keep sending to preserve
the appearance of progress.
Sending into a broken funnel is the most expensive mistake available here, because
prospects are consumed permanently: a business that got a bad first message cannot be
approached again.

| Check | Trigger | Most likely cause, in order | What Astra does | Halts |
| --- | --- | --- | --- | --- |
| 1a. Nobody is accepting (LinkedIn) | 20 CONNECT rows have reached 14 days old, zero accepted (note-less requests from 2026-09-22 on are their own cohort, never pooled with the 41 that carried notes). Open profile and InMail `SENT` rows are not in this denominator; they have no accept gate | the profile gives no reason to accept; these owners do not use LinkedIn; for the pre 2026-09-22 cohort, the note | stop new LinkedIn invitations, report the acceptance count with its denominator plus the `last_activity` and `viewed_us` distributions from Step 2b, name the first cause to check | LinkedIn invitations (the open profile and InMail lanes have no accept gate and keep running) |
| 1b. Nobody is replying | 30 DELIVERED messages across at least 2 tiers, zero replies of any kind. A delivered message is a `SENT` row: a Facebook or Instagram DM to a personal profile, the one message after a LinkedIn accept (or, before 2026-09-22, the acceptance follow up), a LinkedIn open profile message or an InMail. `CONNECT`, `FRIEND` and the historical `SENT_CONT` rows are not delivered messages and never count here | messages are not landing (IG Requests folder, FB Message Requests); the sending profile has no credibility; the evidence is not sharp; the copy | stop new batches, report the counts by tier and channel, name the first cause to check | the session |
| 2. One channel is dead | 15 DELIVERED messages (`SENT` rows) on a channel, zero replies, while another channel is replying | delivery on that channel, not the copy | stop that channel, keep the others, report | that channel |
| 3. Replies are not reaching Zalo | 3 rows at `REPLIED` for more than 2 days with no stage movement | the report is not being read, or he is blocked | lead the report with them, say how long each has waited | nothing |
| 4. Evidence is going stale | 3 rows in one session pulled for dead evidence | the seed list has aged | report it, name the date range of the stale rows, ask for a refresh of `prospects.csv` | nothing |
| 5. Two weeks, nothing | On EVERY active DELIVERING channel, EITHER 14 days have passed since that channel's FIRST DELIVERED message, OR that channel has been Active for 14 days and has delivered NOTHING at all (a channel that cannot deliver is evidence FOR this check, never a reason to hold it back). A POSTING channel (Facebook groups) is never in this population at all: it has no inbox and no delivered message by construction, so counting it would push the halt out by 14 days every time it opened, which is the trap the OR branch exists to prevent. AND at least 20 delivered messages have reached day 7 across all channels together. AND zero replies of any kind. "Delivered" is check 1b's definition exactly: a `SENT` row, so a Facebook or Instagram DM to a personal profile, the one message after a LinkedIn accept, a LinkedIn open profile message or an InMail. `CONNECT`, `FRIEND` and the historical `SENT_CONT` rows never count, and LinkedIn acceptance is check 1a's business, not this one | something structural: account standing, delivery, or market fit | stop the cold track entirely and say so plainly. Do not keep generating batches | the cold track |

A warning event is not a health check; it stops a channel immediately and unconditionally,
per the sending rules.

**Why check 5 is written in delivered messages and not in calendar days:** a pending
invitation is not a delivered message, so a calendar count would read unaccepted LinkedIn
invitations as weeks of failed sending and halt the whole cold track on too little evidence.

The floor is **20 delivered messages aged 7 days** because that is the number this skill
already uses everywhere a rate gets read: "no verdict on a variant under 20 sends", the per
arm size of 20 against 20, and the ramp's own measured delivery gate of 20 delivered owner
DMs aged day 7. Under that floor there is no reply rate to be zero, only a count.

**A channel that has delivered nothing SATISFIES its half of the trigger, it does not
disable the check**. Reading only "14 days since that channel's first delivered message"
would make the check unreachable in exactly the state it exists to catch: a channel with
invitations and zero acceptances has no delivered message and no 14 day clock, so unanswered
messages on the other channels could pile up for months without check 5 ever firing. A
channel that has been open for two weeks and delivered nothing is the strongest structural
evidence there is. Same trap in the other direction:
opening a third channel must not push the halt out by another 14 days, which the OR branch
also prevents, because a channel that has just opened and delivered nothing yet has not been
Active for 14 days and so cannot satisfy either branch until it either delivers or goes two
weeks dry.

**Still say the denominator out loud.** When check 5 does not fire, the report says which
conjunct is missing and its number, per channel: "check 5 not met: 14 delivered aged 7 days,
floor is 20" is a different fact from "check 5 clear", and only one of them is ever true.

The floor of 20 also makes check 5 the SLOW net, not the first one. Check 1b halts the
session at 30 delivered across 2 tiers with no age requirement, so in any fast sending week
1b trips first and stops the bleeding; check 5 is what catches the slow, quiet version that
1b's counter never reaches, and it escalates the same evidence from a session halt to a cold
track halt.

## The report shape

Four parts, in this order, written to `reports/YYYY-MM-DD.md` and printed as the final
message. Template in `templates/report.md`.

1. **Replies for Zalo.** Every reply since the last session, verbatim, with the channel,
   the profile URL, the tier, and what was sent. This is first because it is the only part
   that needs him today. If there were none, say so and say how long the oldest unanswered
   threads have been waiting.
2. **What ran today, with the funnel and a verdict.** Counts of what was sent, by channel
   and tier, against the ceiling. Then the funnel against the shape above, naming the
   first step below par and nothing after it. A number without a verdict is not a report.
3. **One thing to change tomorrow.** Exactly one, drawn from that first weak step.
4. **What is on deck.** Tomorrow's ceiling, which tier and metro is next, how many rows went
   `COLD` today (one message, no reply by day 7), which accepted connections and friend
   requests are owed their one message, and anything Zalo has to do: a mystery call, a batch
   approval, an exhausted list.

Then anything that stopped: warning events, tripped checks, channels halted.

Keep it readable on a phone. No dashes.

## Zalo does

Three things, and Astra says which of them are outstanding in every report.

**The after hours mystery calls.** Call the shop around 8pm. Thirty seconds. It sorts the
list by willingness and hands over a verifiable opening fact. Voicemail means a greenfield
sale. A third party answering service means a replacement sale, which is the highest
willingness segment inside the whole ICP, because he is already paying for a worse version
of the product. Zalo logs the result himself: set `tier` to `B` on that pipeline row and
put the fact in `side_note` in his own words, or tell Astra and it will write it. Astra
never phones a prospect and never invents this fact.

**Message two and everything after the reply.** Astra hands over a replied thread and
stops. Zalo generates the demo on that business in seconds, checks it, and delivers the link
in the same thread: "Here it is, built on your info so you can see what I mean. No
strings." Then the VSL, then the call. Reference notes for that half of the rail are at the bottom of
`templates/messages.md` and in `call-one-pager.md`.

**Approving each batch while approval mode is on.** Read `batch-YYYY-MM-DD.md`, then say
go for that batch. That is the only thing standing between a draft and a send.

Optional, and blocking nothing: filling `proof.md` with the case study facts he is willing
to claim, and filling the price fields in `call-one-pager.md` before the first booked call.

## Files in this skill

- `SKILL.md`, this file. The lane, the loop, the sending rules, the numbers.
- `hunting-playbook.md`, the browser procedure and its speed defaults: one homepage load,
  seed evidence re confirmed live on every row, one quoted owner search, 4 loads and 5 minutes per
  prospect, 45 minutes per session and up to two sessions a day, the research ledger.
- `call-one-pager.md`, Zalo's call sheet. Prices are fields, not numbers.
- `RUNBOOK.md`, how M or Zalo starts a session, and how to verify Codex sees this skill.
- `templates/messages.md`, the copy contract and every message shape.
- `templates/pipeline.csv`, `templates/sent-log.csv`, the two working files' headers.
- `templates/batch.md`, `templates/report.md`, the two documents written per session.
- `templates/config.md`, `templates/proof.md`, `templates/learnings.md`, seeded once.
- `templates/gold-notes.md`, the approved notes to write toward; read before drafting.
- `scripts/note-lint.py`, the deterministic gate on a session's `notes.json`; `ALL PASS`
  or the batch does not ship. **Since 2026-09-22 it is also the one message gate.** Run it
  on the `notes.json` inside the working folder: it walks up to `pipeline.csv`,
  `sent-log.csv` and `prospects.csv` (or takes `--folder <dir>`), refuses a `prospect_id`
  that is in neither `pipeline.csv` nor `prospects.csv` (a mistyped id would otherwise read
  as a fresh prospect), refuses a history folder inside the skill itself (its templates or
  fixtures), and refuses a first touch in more than one
  part, a bump, takeaway or continuation by any name, a LinkedIn connection request with a
  note, and any message to a prospect who already has an outbound message in the log (a
  `SENT`, `SENT_CONT`, `BUMP1`, `BUMP2`, or a `CONNECT` that carried a note), or whose
  pipeline row is `SENT`, `COLD`, has touches, replied, or is `DEAD`. Exit 0 is `ALL PASS`
  with the history checked; exit 1 is a failure; `--no-history` checks the copy only,
  prints `COPY PASS` and exits 2, and never clears a batch. Every entry carries its
  `prospect_id`; a connection request is `"kind": "connect"` with an empty text.
  It knows these variant families: `P1`/`P2` (the control, which also covers the LinkedIn
  delivered lane ids `O1` and `I1`, linkedin only; every LinkedIn text is held to 420),
  `J1`/`J2` (the Facebook joke arm, one message: an approved joke then the fixed ask, on one
  line) and `G1` (the Facebook group post, channel `facebook_groups`, NOT STARTED, and not a
  message to a person, so the history check skips it). `N1` is retired and refused. It
  applies the dare and fixed line checks only where they belong, holds the arms to their
  own channel (`J` Facebook only, `G1` facebook_groups only and that channel takes nothing
  else), and caps the joke arm at 4 rows per joke per day.
  **Since 2026-09-14 it also carries the offer law and the arithmetic bridge guard, across
  every family:** `TECH_AS_CATEGORY` is in `BANNED`, so the tech as a product category
  ("ai receptionist", "ai agent", "voice ai", "our ai", "i help businesses") fails any note
  anywhere, matched on word boundaries so "your air" is not "our ai"; a note that carries an
  offer has to name both halves of the outcome, the answered call and the booked job, read
  from the OFFER sentences rather than the whole note; and an invented rate of calls per
  week, an ROI claim, or a money amount or percentage in the same sentence as a result all
  fail, because the bridge may only do arithmetic inside what the review or the posted hours
  already show. Quoting his own advertised price is a fact, not a claim, and still passes.
  It also normalises the short channel codes (`li`, `fb`, `ig`, `fbg`) and FAILS an
  unrecognised channel rather than silently giving it a limit that belongs to another.
- `scripts/note-lint.test.py`, the lint's own suite: `python3 scripts/note-lint.test.py`.
  Run it after any change to the lint; a change that does not keep it green does not ship.
- `scripts/fixtures/single-message/`, a small working folder (`pipeline.csv`,
  `sent-log.csv`, `prospects.csv`) with two hand made batches: `notes-pass.json` and
  `notes-refuse.json`, which trips every one message refusal (exit 1). A folder inside the
  skill is refused as a history source unless `--fixture` is passed, and a fixture pass
  prints `FIXTURE PASS` and exits 2, never 0. Run either by hand to see the gate work:
  `python3 scripts/note-lint.py scripts/fixtures/single-message/notes-refuse.json --fixture`.
- `scripts/fixtures/new-families.json`, one lintable message per shape (J1, J2, an open
  profile message, the one message after an accept, a note-less connect entry, the two G1
  group posts), checked for copy only: `python3 scripts/note-lint.py
  scripts/fixtures/new-families.json --no-history` prints `COPY PASS` and exits 2.
