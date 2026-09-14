---
name: bu-cold-outreach
description: Run Black Umbrella's own cold DM outreach. Triggers "run today's cold outreach", "cold DM batch", "outreach replies", "bu outreach", "approve the batch and send", "outreach report". Astra executes it in the codex-bare Codex session with Computer Use, sending from Zalo's real LinkedIn, Facebook and Instagram accounts in Chrome, to HVAC and plumbing owner operators countrywide (whatever metros prospects.csv holds; tranche 1 is twelve Sun Belt metros plus a nationwide LinkedIn rail). Enforces the four part message one with no pitch and no link, the per channel caps, the ramp, the pacing, the stop on warning rule, and the approval mode in config.md. Not the course outreach-operator skill, which is for CMAA members sending by hand.
---

# Black Umbrella Cold Outreach

Zalo's own client acquisition rail, not a course deliverable. Astra runs it: it researches
each prospect in the browser, writes the four part message, and sends it from Zalo's real
accounts. Zalo approves batches, makes the after hours mystery calls, and owns every
thread from the moment a prospect replies.

The target is the owner operator of a 3 to 8 truck HVAC or plumbing company doing $1M to
$3M, anywhere in the US (the strategy doc named Phoenix, Dallas-Fort Worth and Tampa
first; Zalo widened it to countrywide on 2026-09-08). He is off the tools, spends on ads or is
hiring office help, and every after hours call that hits voicemail is a service call or an
install he already paid to generate.

## The lane requirement, read this before anything else

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
| Sends message one and its two bumps, within the caps and the pacing | Fills the price fields in `call-one-pager.md` before the first call |
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
there is nothing to work: read replies, run the bumps that are due, report, and say the
seed list is exhausted. Never generate prospects and never modify `prospects.csv`.

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
  re confirm them live before using them (hunting playbook, Step 1).
- `qualified` and `drop_reason` are the seed list's own filter verdict. Only work rows
  where `qualified` is true.

### `pipeline.csv`, the working state

```
prospect_id,business_name,metro,tier,channel,profile_url,owner_name,stage,last_touch,next_due,angle,side_note,demo_link,demo_views_last,touches,notes
```

`angle` is the variant id, `<tier>-<channel>-<phrasing>`, for example `A-li-P1`, or the lane
id `<tier>-li-O1` (open profile message) or `<tier>-li-I1` (InMail) for the two delivered
LinkedIn lanes added 2026-09-12. `touches`
is how many messages Astra has sent to this row (0, 1 for the first touch, 2 after bump 1,
3 after bump 2). `demo_link` and `demo_views_last` are Zalo's columns; Astra reads them and
never writes them. `notes` carries the reply text verbatim once a reply lands.

**Stages.**

| Stage | Meaning | Whose |
| --- | --- | --- |
| `FOUND` | qualified, owner and channel resolved, nothing sent yet | Astra |
| `SENT` | first touch delivered, no reply | Astra |
| `REPLIED` | any reply at all, including a no | Astra sets it, Zalo owns the thread |
| `DEMO_SENT` | Zalo built the demo and delivered the link | Zalo |
| `TESTED` | the prospect used the demo | Zalo |
| `VSL_SENT` | VSL handed off, no booking yet | Zalo |
| `CALL` | call booked | Zalo |
| `NO_SHOW` | booked, did not show | Zalo |
| `CALL_HELD` | call happened, no decision | Zalo |
| `CLOSED` | client won | Zalo |
| `COLD` | two bumps, no reply | Astra |
| `DEAD` | said stop, not interested, or blocked | Astra sets it on sight, forever |
| `NO_CHANNEL` | qualified, no open DM path on any active channel | Astra |

`CONNECT` and `FRIEND` are not pipeline stages. They are values that appear only in the
`stage` column of `sent-log.csv`: `CONNECT` marks a LinkedIn connection request and `FRIEND`
a Facebook friend request (added 2026-09-12), neither of which is a message. A prospect
whose request is pending stays at `FOUND` in the pipeline.

**Follow up timing.** Astra runs only the first two rows of this table. Everything below
`REPLIED` belongs to Zalo and Astra never sends into it, though it tracks the dates so the
report can tell him what is due.

| Stage | Due when | Action | If still nothing | Whose |
| --- | --- | --- | --- | --- |
| `SENT` | 3 days after the first touch | Bump 1, with a new fact | day 7, Bump 2 the takeaway, then `COLD` | Astra |
| `SENT` | day 7 | Bump 2, the takeaway | row goes `COLD`, no third touch ever | Astra |
| `REPLIED` | immediately | surface in the report, do not answer | Zalo | Zalo |
| `DEMO_SENT` | 2 days, no movement | nudge | day 5, final, then `COLD` | Zalo |
| `TESTED` | as soon as he sees it | feedback opener, then the VSL | day 3, resend the VSL once | Zalo |
| `VSL_SENT` | 24 hours, no booking | did the video make sense | day 4 value, day 8 takeaway, then `COLD` | Zalo |
| `CALL` | day before and morning of | confirmation nudge | kills no shows | Zalo |
| `NO_SHOW` | same day | warm reschedule | day 2, then day 6 takeaway | Zalo |
| `CALL_HELD` | day 1 | recap with the exact offer discussed | day 4 their objection, day 10 takeaway | Zalo |

**Rules that keep the bumps from becoming spam.**

- Every bump adds something: a new true fact, a new angle on the same fact, or the
  takeaway. Never "just checking in", never a bare re-send.
- The takeaway is always the last thing sent. Every sequence ends with a graceful exit
  that leaves the door open, not with silence.
- Bumps do not count against the daily cold quota, but they DO count for pacing: the 2 to
  5 minute gap applies to every message, cold or bump.
- A row that replies exits the timed sequence permanently. Conversations do not get bumps.
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
`message_head` set to the first 80 characters of the note when the request carries one.
Count the `CONNECT` rows from the last 7 days before sending any new request; they are the
denominator for the 80 per week limit.

**Facebook friend requests get a row too (added 2026-09-12 on Zalo's written yes).** A
friend request carries no message and is not a cold first touch. Its row has `stage`
`FRIEND`, `channel` `fb`, the owner's PERSONAL profile URL, `variant` set to the id the
accepted thread will carry (`D-fb-J1`, `D-fb-J2` or the control id), and `message_sha1`,
`message_head`, `opener_type` and `message_text` empty, because nothing was typed. It counts
for pacing like every action typed in these apps, against `facebook_friend_requests_per_day`
in `config.md`, and against nothing else. It has its own accept gate: denominator is
`FRIEND` rows aged 14 days, numerator is accepts. An accepted request turns the row into a
deliverable: the J arm or the control DM goes into the accepted thread and lands in Chats,
past the spam filter, and only then is it a `SENT` row and a cold first touch against the
Facebook 10, on the day it is typed. A request pending 14 days is `NO_CHANNEL` on Facebook
unless another channel is open. Stop on the friend request warning exactly like the message
warning. A `FRIEND` row is never a delivered message and is a denominator nowhere except its
own accept gate.

**Open profile messages and InMails are `SENT` rows (added 2026-09-12).** A LinkedIn message
sent to an open profile, or by InMail, is a delivered first touch: `stage` `SENT`, `variant`
`<tier>-li-O1` (open profile) or `<tier>-li-I1` (InMail), counted against the LinkedIn daily
cap of 15 and never against the 80, in health check 1b's delivered denominator and never in
1a's acceptance denominator. Message one for these rows is the control four part DM shape
from `templates/messages.md` (not the invitation note), because it is a delivered message
with room to carry the specific, the bridge, the what we do line and the question; it
carries the P1 or P2 line like every control message and the batch entry names which. The
three LinkedIn lanes share the one cap of 15: `CONNECT` rows plus `O1` rows plus `I1` rows on
a day never exceed 15. InMail is further capped by `inmail_credits_per_month` in `config.md`
(2 a day and 5 in the calendar month until Zalo writes the number). An InMail also carries a
subject line, which is not one of the four parts and is not linted: the business name or
the first part's fact, no pitch, no link.

The lint knows the two lane ids (closed 2026-09-12, the same day the gap was written):
`scripts/note-lint.py` maps `O1` and `I1` to the pitch family, so a note for either lane is
linted in `notes.json` under its OWN id, `<tier>-li-O1` or `<tier>-li-I1`, and every control
check runs on the exact text about to be typed. Two things differ from the invitation note:
the lint holds an `O1` or `I1` text to 420 characters (the Facebook control shape, because
these are DMs, not the 300 character note), and it refuses either id on any channel but
linkedin. The `sent-log.csv` `variant` and the pipeline `angle` carry the same lane id. The
text linted and the text sent are the same string, checked by sha1 in the batch as usual.

**LinkedIn is a two gate funnel and each gate gets its own denominator (2026-09-12).** The
skill previously said CONNECT rows were "excluded from every send count and every reply
rate" while `learnings.md` rule 5 said "on LinkedIn a send is the connection note". Both
cannot be true, and the disagreement made five days of numbers unreadable. The rule now:

- **Gate 1, acceptance.** Denominator is CONNECT rows that have reached 14 days old.
  Numerator is acceptances. This is the LinkedIn number that matters first, and it is the
  one the copy on the note is actually competing for.
- **Gate 2, reply.** Denominator is delivered LinkedIn messages: accepted invitations that
  received the acceptance follow up, plus open profile messages and InMails (added
  2026-09-12, delivered on send). Numerator is human replies. This is the only LinkedIn
  number comparable to a Facebook or Instagram reply rate.

A CONNECT row is never counted as a delivered message, and an accepted invitation with the
follow up sent is; so is an open profile message or an InMail, which is delivered on send
and skips gate 1 entirely (it sits in gate 2's denominator and in check 1b, never in gate
1). Report both gates side by side, always with their denominators, and
never blend them into one "reply rate". An invitation younger than 14 days belongs in
neither denominator: it is pending, not failed.

**A multi part first touch is ONE send, logged as several rows (2026-09-12).** The `J` arm
on Facebook types a setup, a punchline and an ask, and the 2026-09-08 Geo entry went out as
two messages for the same reason. Log every message that leaves, but mark the continuations
so nothing counts a prospect twice:

- the FIRST message of the first touch takes `stage` `SENT`. That row, and only that row,
  is the delivered send for that prospect in every count, every rate and the scoreboard.
- every later part of the same first touch takes `stage` `SENT_CONT`, in timestamp order,
  with its own `message_sha1` and `message_head`. `SENT_CONT` rows are audit and pacing
  evidence and are counted nowhere.

So a J prospect is 3 rows, 1 counted send, 1 cold first touch against the cap, and 3 pacing
gaps. The permitted `stage` values in this file are `CONNECT`, `FRIEND`, `SENT`,
`SENT_CONT`, `BUMP1`, `BUMP2` and `GROUP_POST`, and only `SENT` is ever a denominator (a
`FRIEND` row is the denominator of its own accept gate and of nothing else, and a
`GROUP_POST` row of its own calls per post read and of nothing else).

**`GROUP_POST` is the Facebook groups row (added 2026-09-14, channel NOT STARTED).** A post
in a group is not a message to a person: `prospect_id` is empty, `profile_url` is the
group's URL, `channel` is `fbg`, `variant` is the `<metro>-fg-G1` id. It is never a
delivered message, never a cold first touch, and never in a reply rate. It counts for
pacing like anything else typed in the app. Full shape in `config.md`.

**Count DISTINCT prospects, not rows.** Sends on a channel or a variant are the number of
distinct `prospect_id` values among its `SENT` rows. `SENT_CONT` makes a continuation
explicit going forward; the distinct count makes the same thing true for rows written before
`SENT_CONT` existed, and it is the structural fix for the bug rather than a rule that has to
be remembered.

**Two rows in the working log predate all of this and are corrected here, not rewritten,
because the log is append only:**

- `a5647b073a` (Geo, facebook, 2026-09-09) has TWO `SENT` rows, 10:45 and 11:20. They are the
  two halves of one message. Today the 11:20 row would be `SENT_CONT`. One prospect, one
  send.
- `f4e1c0f25e` (AJ's Air, facebook, 2026-09-09 10:56) went to a business PAGE,
  `facebook.com/AJsAirAC`. A page is not a channel, so it is excluded from every send count,
  every reply rate and the scoreboard. It stays in the file as the audit record of a rule
  violation, and an auto responder answered it, which is not a reply either.

So the working log's delivered owner messages to date is ONE, not three. Any count that says
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

### 0. Read, check, state

Read `config.md`, `pipeline.csv`, `sent-log.csv`, yesterday's `batch-*.md` and yesterday's
report. Run the health checks. Then state, in the first lines of output:

- the mode (approval on or off),
- **one line per ACTIVE channel**, because since 2026-09-12 each channel has its own ramp:
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

There is no single shared ceiling any more. A channel that is held, reset or inactive takes
nothing away from the others, and no channel is ever allowed above its own cap in the
channel table of `config.md`.

If a health check has tripped, **stop producing a new batch**. Read replies, report the
trip with its numbers and the likely cause, and end the session there.

### 1. Replies first

Open each active channel's inbox in Chrome and read every reply on threads that are in
`pipeline.csv`. For each one:

1. Set the stage to `REPLIED` (or `DEAD` if it is a stop request).
2. Paste the reply verbatim into the pipeline `notes`. Do not summarize it, do not clean
   it up, do not correct its spelling.
3. Add it to the "Replies for Zalo" section of the report with the channel, the profile
   URL, the tier, the message that was sent, and the reply.
4. Send nothing.

**An auto-responder is not a reply (2026-09-09).** "Thanks for messaging us, we'll get back
to you soon" and its cousins arrive within seconds of a Facebook page message and come
from the page's settings, not a person. The row stays SENT with its bump clock; do not
mark it REPLIED, do not clear next_due, and do not count it in the scoreboard. A reply is
a human answering.

Also check for anything the platform says. A captcha, a "slow down" notice, a restriction
notice or an unusual login prompt is a warning event and is handled under the sending
rules. A single message that failed to deliver is NOT a warning event: a deactivated or
blocked account is a fact about that prospect, not about the sending account. Record it in
the notes, set the row to `NO_CHANNEL` if that was the only channel, and do not count it as
a send. Only escalate it to a warning event if the platform states a reason that is about
Zalo's account.

### 2. Bumps due

Date driven from `pipeline.csv`. Walk every `SENT` row, compare `last_touch` to today, and
draft what is due per the follow up table: bump 1 at day 3, bump 2 at day 7, then `COLD`.
Nothing else. Bumps go in the batch file in their channel's section.

Before drafting a bump, check the new fact actually exists. If the job post came down or
the ad stopped, that IS the new fact and it can open the bump honestly ("the role came
down, guessing you filled it"). If there is genuinely nothing new, go straight to the
takeaway rather than sending an empty bump.

### 2b. Rows already in the pipeline that are waiting

Walk every row at stage `FOUND`. These are rows Astra already researched and that never
went out: an approval mode batch Zalo did not approve, a row pulled for stale evidence, a
LinkedIn owner who had to be connection requested first, or a tier B row Zalo created after
his mystery call. Without this step they sit in `pipeline.csv` forever and Step 3 skips
them, because Step 3 only takes rows that are not already in the pipeline.

For each `FOUND` row:

- **Connection request pending on LinkedIn.** Check whether it was accepted. Accepted with
  no reply means put the fixed acceptance follow up from `templates/messages.md` into
  today's batch (no new drafting; it is the message one send for that row). **An `N1` row
  takes the N1 acceptance follow up, which carries the pitch the note left out; every other
  row takes the standard one.** Accepted with a reply is REPLIED and goes to Zalo. Still
  pending after 14 days means set `NO_CHANNEL` unless another active channel is open, in
  which case switch the channel and redraft.

  **While the profile is open, record two things in `notes`, because they are what make a
  pending invitation interpretable instead of just silent:** `last_activity: YYYY-MM-DD`
  from the profile's Activity tab (the most recent post, comment or reaction, or `none
  visible`), and `viewed_us: yes|no` from "Who viewed your profile". An invitee who viewed
  Zalo's profile and did not accept READ the note and said no, which is a copy or profile
  signal. An invitee who never viewed it and has no activity in six months never saw
  anything, which is a channel signal. Report the two distributions in the session report.
  Without them, a pending invitation carries no information and zero acceptances cannot be
  diagnosed.

- **Friend request pending on Facebook (added 2026-09-12).** Check whether it was accepted.
  Accepted with nothing said means the message one this row was assigned (the J arm's
  setup, punchline and ask, or the control DM) goes INTO TODAY'S BATCH under today's
  approval, typed into the accepted thread; on the day it is typed it is a `SENT` row and a
  cold first touch against the Facebook 10. Accepted with anything said, one word or one
  emoji, is REPLIED and the thread is Zalo's. Still pending after 14 days means set
  `NO_CHANNEL` unless another active channel is open, in which case switch the channel and
  redraft. Record `friend_request: pending|accepted YYYY-MM-DD` in `notes` so the accept
  gate reads by send date.

- **A Facebook `J` row waiting on its next part.** The joke arm is three messages. If the
  setup went out and the punchline did not, the punchline goes INTO TODAY'S BATCH FILE,
  under today's approval, ahead of any new first touch on that channel. If both went out and
  nothing came back, the ask goes into today's batch the same way. Yesterday's approval
  covers yesterday's batch and nothing else, so an unfinished sequence waits for today's go
  exactly like a new row does. **If anything came back at any point, including one word or one emoji, the row
  is REPLIED, the remaining parts are never sent, and the thread is Zalo's.** A laugh is a
  reply, so on this arm Zalo is usually the one who asks the question.

  **How a continuation is written so the lint accepts it** (added 2026-09-12). A
  continuation entry carries only the parts that still have to be typed, and every one of
  its notes in `notes.json` carries two extra fields:

  ```json
  { "entry": 11, "channel": "facebook", "variant": "D-fb-J1", "part": "punchline",
    "text": "Everything leaks eventually.",
    "sent_parts": ["setup"], "joke_setup": "Why don't ducts keep secrets?" }
  ```

  `sent_parts` is what already went out, in send order, read off `sent-log.csv`: `["setup"]`
  or `["setup", "punchline"]` and nothing else. `joke_setup` is the approved setup text this
  thread is carrying, which is how the punchline still gets checked against its own setup a
  day later. The parts in the batch have to be the contiguous run that follows `sent_parts`,
  so an ask cannot jump a punchline that never went out. The batch entry quotes the
  `sent-log.csv` rows it is claiming, because the marker is an assertion the lint cannot
  verify by itself. Never pad the batch with text that already went out just to get a pass:
  a batch file is the list of messages about to be typed, and a lint reading yesterday's
  sends is a lint checking nothing.

  **What a continuation costs (added 2026-09-12).** It does NOT consume a cold first touch
  slot: that slot was spent on the day its setup went out, and a cold first touch is one
  prospect, not one typed message. It DOES count for pacing like every message typed in these
  apps, and it counts against the joke repetition cap, because it types that joke at a
  stranger today exactly like a fresh row does. So the brake on a continuation heavy day is
  the pacing gap, not the cap: six interrupted rows plus a full 10 row day is 42 typed
  Facebook messages at 2 to 5 minutes each, which no session can hold. **Continuations are
  typed FIRST, then as many new first touches as the session can fit at the full gap, and
  the batch header states the typed message total for the day, not just the first touch
  count.** Send fewer new rows and report the real number; never compress the gap.
- **Pulled for stale evidence.** Re confirm per the hunting playbook. Live again means
  redraft. Still dead means demote the tier and open on a side note, or set `NO_CHANNEL`.
- **Tier B created by Zalo.** Draft the tier B opener from the answering service fact in
  `side_note`. These go first in the batch.
- **Anything else at `FOUND`.** Redraft it into today's batch. The research is already done,
  so it costs nothing but a re confirmation.

These rows count against today's quota exactly like new rows do.

### 3. Today's batch

Take rows from `prospects.csv` that are `qualified` and whose `prospect_id` is not in
`pipeline.csv` at a stage other than `FOUND`. **Order: tier A, then B, then C, then D**,
the same order everywhere in this skill. Within a tier, prefer rows that already have an
owner resolved (the linkedin rail), then higher `review_count`. Tier B rows exist only in
`pipeline.csv`, never in the seed file, so they enter the batch through Step 2b below.

For each row, per `hunting-playbook.md` and inside its speed defaults (4 page loads and 5
minutes per prospect, 45 minutes of research per session, accessibility text not
screenshots, one quoted owner search, Indeed never opened):

1. Load the homepage once. Kill on size, franchise, commercial only or an AI chat widget;
   otherwise take the owner name if it is there and keep the homepage facts as bump
   material, not as the opener.
2. Take the sniper evidence from the seed row when the tranche is under 7 days old (no re
   confirmation), then spend one load on the specific the opener needs per the
   specificity law in `templates/messages.md`: the duties and shift line on the
   employer's own job posting (tier A), what the ad says plus the Google hours (tier C),
   a review quote about the phone or the hours gap from the Google Business Profile
   (tier D). Re confirm evidence only for older tranches, FOUND redrafts and bumps. Dead
   evidence means demote the tier or pull the row; never write around a fact that
   stopped being true.
3. Resolve the owner with one quoted search for maps rail rows. Ambiguous means hold.
4. Pick the channel: LinkedIn when the owner profile exists, then the owner's PERSONAL
   Facebook profile (never the business page; a page is not a channel, Zalo 2026-09-09),
   then Instagram.
   **On LinkedIn, check for an open profile before defaulting to the connection request
   (added 2026-09-12).** On most profiles the Message button opens a paid Sales Navigator
   prompt and the send is a connection request carrying the note. But a LinkedIn Premium
   member who has turned on Open Profile can be messaged free by anyone with no connection
   request, no accept and no wait, and the message lands in their main inbox. The check is
   one click during research: open the profile while not connected and see whether the
   Message button opens a free composer or an upsell (on mobile the button reads InMail but
   charges no credit). A free composer means the row is an open profile send, variant
   `<tier>-li-O1`, which skips the accept gate entirely and gets the control four part
   message one rather than the invitation note (the sent-log section above has the counting
   rules). Record `open_profile: yes|no` in the pipeline `notes` for EVERY LinkedIn row
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
   batch entry says which: the cold DM (message one now, a `SENT` row against the 10) or
   the friend request (a `FRIEND` row now, against `facebook_friend_requests_per_day`; the J
   arm or the control DM goes into the thread after the accept, per Step 2b). Friend
   requests are listed in the batch file under Facebook with a status line each and no
   `notes.json` entry, because there is nothing to lint, and they wait for Zalo's go like
   every other action. Miami rows go first on Facebook, for the delivery reason in
   `config.md`.
5. Write the finished message per `templates/messages.md`, every token filled. On the
   control the opener passes the paste test (if it could go to another company with the
   name swapped, it does not ship), the bridge clause ties it to the phones and the dare
   closes it. On the `J` arm the paste test is deliberately waived and the lint enforces
   the approved fixed copy instead. Every note goes through the gate in
   `templates/messages.md` before the batch file is written: read `templates/gold-notes.md` first, then `ALL PASS` from
   `scripts/note-lint.py` on the session's `notes.json`, then the humanizer pass (the
   skill at `~/dev/zalo-kabche-brand/.claude/skills/humanizer/SKILL.md`). The lint output
   goes in the batch header. LinkedIn invitation rows carry the 300
   character invitation note and nothing else; the acceptance follow up is fixed copy,
   so no second draft per row. Open profile and InMail rows carry the control four part
   message one instead, inside the 420 character DM limit the lint applies to `O1` and
   `I1` (the Facebook control shape, not the 300 character invitation note), per the
   sent-log section.
6. Append the row to the research ledger: id, seconds, page loads, outcome.

Stop researching when every active channel has hit its own number, or at 45 minutes of
research, whichever comes first, and say which. One 45 minute budget covers the whole
research session, not 45 minutes per channel. Since 2026-09-12 a day may run two sessions,
a research and resolution session and a send session, each with its own 45 minutes
(`hunting-playbook.md`, Speed defaults, rule 2); the send session types and paces only, and
every row it sends was drafted, linted and, on LinkedIn, checked for an open profile in the
research session. Report the real number per channel.

Write `batch-YYYY-MM-DD.md` from `templates/batch.md`, grouped by channel, tier order
inside each channel, bumps last within each channel.

**In approval mode, stop here.** Report the file path, how many drafts are waiting, and
the split by channel and tier. Send nothing until Zalo says go for that batch. His go
applies to that batch only; it does not change `config.md` and it does not carry to
tomorrow.

**Outside approval mode**, send down the list, and after every single send:

1. Append the row to `sent-log.csv`.
2. Update the pipeline row for a MESSAGE: stage `SENT`, `last_touch` today, `next_due`
   today plus 3, `touches` incremented. A `CONNECT` or `FRIEND` row is not a message: the
   pipeline row stays at `FOUND` with the pending request in `notes`, per Step 2b.
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

**The measured failures. All of these are DATA, not somebody's opinion.**

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
against two different budgets, and BOTH bind. Before this was written down the playbook said
an invitation counts against the week and "not the 15 DMs per day", which would have let a
week 3 session send 15 follow ups plus the whole weekly invitation remainder in one
afternoon. There is no day on which LinkedIn actions exceed that channel's daily number.
An open profile message or an InMail is a cold first touch against the same 15 and never
against the 80; it has no accept gate, so the ramp hold, which binds invitations, does not
reduce it (`config.md`, arithmetic step 6).

**The ramp, one per channel (restructured 2026-09-12).** Each ACTIVE channel carries its
own `ramp_start_date`, `ramp_week` and `daily_cold_ceiling` in `config.md`. Week 1 is 10
cold first touches a day on that channel. Week 2 is 20, and never above that channel's own
cap. Week 3 and after is that channel's cap. A channel advances only if ITS week had zero
warnings AND it has a measured delivery number: on LinkedIn, 20 CONNECT notes aged 14 days
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

Before this there was ONE shared ramp for all three channels, so opening a second channel
either could not happen or silently halved the first. Now: opening Facebook costs LinkedIn
nothing, and a warning that resets Facebook leaves LinkedIn where it was. The one exception
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

**A cold first touch is one prospect, not one typed message.** The three part joke sequence
of the `J` arm is ONE first touch against the daily cap and three typed messages against
the pacing gap. Any multi part first touch counts the same way.

**Messenger sends on Enter (2026-09-09).** A newline passed to the Facebook composer fires
Send mid message: entry 4 of the 2026-09-08 batch went out as the opener alone. Type
paragraph one, press Shift+Return twice, type paragraph two, then Send. Never pass a
string containing a newline to the composer. LinkedIn's note field does not have this
problem.

**Pacing.** One message at a time, with a randomized gap of 2 to 5 minutes between sends.
Never a burst. Bumps and any other message typed in these apps count for pacing even
though they do not count against the cold quota.

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

**Message one has four parts and nothing else.** How you found him (a fact you can see),
why him (the specific thing you noticed about his business), what we do in his language
(answers calls and texts in about five seconds, 24/7, books the job into the calendar),
and a question he can answer in four words. No pitch, no link, no meeting ask.

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
message one DOES say a demo has been trained on his website and offers to send it (Zalo's
decision, 2026-09-08, restoring the course's champion angle), because Zalo generates the
demo in seconds when the reply lands. No link in message one; the link is message two, from
Zalo, in the same thread.

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

**Two measured test arms run beside the control, tier D only (added 2026-09-12).** Both are
written in full in `templates/messages.md`, both are 20 sends against 20 sends of the
control, and neither touches tier A, B or C while the accept gate has no number.

- **`N1`, the LinkedIn note with no pitch.** The invitation note's only job is the accept,
  so this arm carries the specific, the bridge and one question, and the pitch moves to the
  acceptance follow up. Judged on the ACCEPTANCE rate at 14 days.
- **`J1` and `J2`, the Facebook trade joke opener.** A two part joke typed as two deliberate
  sends, then the ask as a third, on the owner's PERSONAL Facebook profile. Judged on
  replies at day 7. It is the one sanctioned exception to the specificity law, scoped to
  this arm, and it carries no demo claim at all.

**A third arm beside those two: `FRIEND`, the Facebook friend request first (Zalo's written
yes, 2026-09-12).** Not a copy arm: a friend request with no note, then the J arm or the
control DM into the accepted thread. Its numbers (`facebook_friend_requests_per_day`, its
ramp, its accept gate) live in the Facebook section of `config.md`, its rows are `FRIEND`
rows in `sent-log.csv`, and it is judged on ACCEPTANCE at 14 days first, then on replies at
day 7 on the messages it delivered. The batch entry names the tier and the message the
accepted thread gets; while the arm's accept gate has no 14 day number it is tier D only,
per the tier rule for friend requests in `config.md`.

**Neither arm sends anything until Zalo has read its copy**: the six joke openers and the
two no pitch notes, both in `templates/gold-notes.md`. That is a precondition on the arm,
separate from the per batch approval, and it holds even if `approval_mode` is ever off. The
LinkedIn arm additionally waits for the accept gate read (the invitees' last activity dates
and who viewed the profile), because a no pitch note measured on a channel these owners do
not use measures nothing.

Everything not named in those two arms is unchanged: the four part message one, the dare,
the demo claim, the caps, the pacing, the stop on warning rule, approval mode, and the law
that Astra's messages carry no numbers.

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
| 1a. Nobody is accepting (LinkedIn) | 20 CONNECT notes have reached 14 days old, zero accepted. Open profile and InMail `SENT` rows are not in this denominator; they have no accept gate | the profile gives no reason to accept; these owners do not use LinkedIn; the note | stop new LinkedIn invitations, report the acceptance count with its denominator plus the `last_activity` and `viewed_us` distributions from Step 2b, name the first cause to check | LinkedIn invitations (the open profile and InMail lanes have no accept gate and keep running) |
| 1b. Nobody is replying | 30 DELIVERED messages across at least 2 tiers, zero replies of any kind. A delivered message is a `SENT` row: a Facebook or Instagram DM to a personal profile, a LinkedIn acceptance follow up, a LinkedIn open profile message or an InMail. `CONNECT`, `FRIEND` and `SENT_CONT` rows are not delivered messages and never count here | messages are not landing (IG Requests folder, FB Message Requests); the sending profile has no credibility; the evidence is not sharp; the copy | stop new batches, report the counts by tier and channel, name the first cause to check | the session |
| 2. One channel is dead | 15 DELIVERED messages (`SENT` rows) on a channel, zero replies, while another channel is replying | delivery on that channel, not the copy | stop that channel, keep the others, report | that channel |
| 3. Replies are not reaching Zalo | 3 rows at `REPLIED` for more than 2 days with no stage movement | the report is not being read, or he is blocked | lead the report with them, say how long each has waited | nothing |
| 4. Evidence is going stale | 3 rows in one session pulled for dead evidence | the seed list has aged | report it, name the date range of the stale rows, ask for a refresh of `prospects.csv` | nothing |
| 5. Two weeks, nothing | On EVERY active DELIVERING channel, EITHER 14 days have passed since that channel's FIRST DELIVERED message, OR that channel has been Active for 14 days and has delivered NOTHING at all (a channel that cannot deliver is evidence FOR this check, never a reason to hold it back). A POSTING channel (Facebook groups) is never in this population at all: it has no inbox and no delivered message by construction, so counting it would push the halt out by 14 days every time it opened, which is the trap the OR branch exists to prevent. AND at least 20 delivered messages have reached day 7 across all channels together. AND zero replies of any kind. "Delivered" is check 1b's definition exactly: a `SENT` row, so a Facebook or Instagram DM to a personal profile, a LinkedIn acceptance follow up, a LinkedIn open profile message or an InMail. `CONNECT`, `FRIEND` and `SENT_CONT` rows never count, and LinkedIn acceptance is check 1a's business, not this one | something structural: account standing, delivery, or market fit | stop the cold track entirely and say so plainly. Do not keep generating batches | the cold track |

A warning event is not a health check; it stops a channel immediately and unconditionally,
per the sending rules.

**Why check 5 is written in delivered messages and not in calendar days** (restated
2026-09-12). It used to read "14 days of sending, zero replies on every channel", which is
the same misread checks 1a and 1b were fixed to stop making: a pending invitation is not a
delivered message. Sending began 2026-09-08, so on 2026-09-22 the old wording fires on a
delivered set of one Facebook message plus whatever the Facebook joke arm has managed since
it opened on 2026-09-13 (its start date moved forward later on 2026-09-12), a few days of it
7 days old and nowhere near 20, and it would read 37 unaccepted LinkedIn
invitations as two weeks of failed sending and halt the whole cold track on Facebook's day 7.

The floor is **20 delivered messages aged 7 days** because that is the number this skill
already uses everywhere a rate gets read: "no verdict on a variant under 20 sends", the per
arm size of 20 against 20, and the ramp's own measured delivery gate of 20 delivered owner
DMs aged day 7. Under that floor there is no reply rate to be zero, only a count.

**A channel that has delivered nothing SATISFIES its half of the trigger, it does not
disable the check** (corrected in the re audit of this fix, 2026-09-12). The first cut read
"14 days since that channel's first delivered message" and nothing else, which made the
check unreachable in exactly the state it exists to catch: on this account LinkedIn is
`Active: yes` with 37 invitations and zero acceptances, so it has no delivered message and no
14 day clock, and a literal reading let 400 unanswered Facebook messages pile up over five
months without check 5 ever firing. A channel that has been open for two weeks and delivered
nothing is the strongest structural evidence there is. Same trap in the other direction:
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
4. **What is on deck.** Tomorrow's ceiling, which tier and metro is next, which bumps are
   due, and anything Zalo has to do: a mystery call, a batch approval, an exhausted list.

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
  seed evidence trusted for 7 days, one quoted owner search, 4 loads and 5 minutes per
  prospect, 45 minutes per session and up to two sessions a day, the research ledger.
- `call-one-pager.md`, Zalo's call sheet. Prices are fields, not numbers.
- `RUNBOOK.md`, how M or Zalo starts a session, and how to verify Codex sees this skill.
- `templates/messages.md`, the copy contract and every message shape.
- `templates/pipeline.csv`, `templates/sent-log.csv`, the two working files' headers.
- `templates/batch.md`, `templates/report.md`, the two documents written per session.
- `templates/config.md`, `templates/proof.md`, `templates/learnings.md`, seeded once.
- `templates/gold-notes.md`, the approved notes to write toward; read before drafting.
- `scripts/note-lint.py`, the deterministic gate on a session's `notes.json`; `ALL PASS`
  or the batch does not ship. It knows four variant families: `P1`/`P2` (the control,
  which also covers the LinkedIn delivered lane ids `O1` and `I1` at a 420 character DM
  limit, linkedin only), `N1` (the no pitch LinkedIn arm), `J1`/`J2` (the Facebook joke
  arm) and `G1` (the Facebook group post, channel `facebook_groups`, NOT STARTED), and
  applies the dare and fixed line checks only where they belong. It also holds the arms to
  their own channel (`N1` LinkedIn only, `J` Facebook only, `G1` facebook_groups only and
  that channel takes nothing else), the `N1` note to 120 to 240 characters,
  and the joke arm to 4 rows per joke per day, and it accepts the `sent_parts` plus
  `joke_setup` continuation marker so an interrupted joke sequence can be finished in a
  later batch without padding it with messages that already went out.
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
  unrecognised channel rather than silently giving it LinkedIn's 300 character limit.
- `scripts/note-lint.test.py`, the lint's own suite: `python3 scripts/note-lint.test.py`.
  Run it after any change to the lint; a change that does not keep it green does not ship.
  202 cases as of 2026-09-14.
- `scripts/fixtures/new-families.json`, one lintable note per test arm plus one joke
  CONTINUATION entry carrying the `sent_parts` and `joke_setup` marker and the two G1 group
  posts, so every arm shape can be checked without a live batch.
