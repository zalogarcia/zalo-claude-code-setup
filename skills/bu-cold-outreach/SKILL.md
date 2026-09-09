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

`angle` is the variant id, `<tier>-<channel>-<phrasing>`, for example `A-li-P1`. `touches`
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

`CONNECT` is not a pipeline stage. It is a value that appears only in the `stage` column of
`sent-log.csv`, marking a LinkedIn connection request rather than a message. A prospect
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

```
timestamp_et,channel,prospect_id,profile_url,stage,message_sha1,message_head
```

Append one row immediately after each message actually leaves, before starting the pacing
gap for the next one. `timestamp_et` is US Eastern, `YYYY-MM-DD HH:MM`. `message_sha1` is
the sha1 of the exact message body as sent. `message_head` is its first 80 characters,
with newlines replaced by spaces and any comma quoted per CSV rules.

**LinkedIn connection requests get a row too**, with `stage` set to `CONNECT` and
`message_head` set to `connection request, no note`. Those rows are the ONLY denominator for
the 80 per week limit, and they are excluded from every send count, every reply rate and the
variant scoreboard, because a connection request is not a message. Count the `CONNECT` rows
from the last 7 days before sending any new request.

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
- the ramp week and today's ceiling,
- today's per channel quota, already reduced by anything sent today,
- any tripped health check.

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
  today's batch (no new drafting; it is the message one send for that row). Accepted with
  a reply is REPLIED and goes to Zalo. Still pending after 14 days means set `NO_CHANNEL`
  unless another active channel is open, in which case switch the channel and redraft.
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

For each row, per `hunting-playbook.md` and inside its speed defaults (3 page loads and 4
minutes per prospect, 40 minutes of research per session, accessibility text not
screenshots, one quoted owner search, Indeed never opened):

1. Load the homepage once. Kill on size, franchise, commercial only or an AI chat widget;
   otherwise take the side note, and the owner name if it is there.
2. Take the sniper evidence from the seed row when the tranche is under 7 days old. Re
   confirm only for older tranches, FOUND redrafts and bumps. Dead evidence means demote
   the tier or pull the row; never write around a fact that stopped being true.
3. Resolve the owner with one quoted search for maps rail rows. Ambiguous means hold.
4. Pick the channel: LinkedIn when the owner profile exists (the send is a connection
   request carrying the note, because the Message button is a paid Sales Navigator
   prompt), then the owner's personal Facebook over the business page, then Instagram.
   No channel on any active platform means `NO_CHANNEL` in the pipeline and take the next
   row.
5. Write the finished message per `templates/messages.md`, every token filled. LinkedIn
   rows carry the 300 character invitation note and nothing else; the acceptance follow
   up is fixed copy, so no second draft per row.
6. Append the row to the research ledger: id, seconds, page loads, outcome.

Stop researching at the ceiling or at 40 minutes, whichever comes first, and say which.

Write `batch-YYYY-MM-DD.md` from `templates/batch.md`, grouped by channel, tier order
inside each channel, bumps last within each channel.

**In approval mode, stop here.** Report the file path, how many drafts are waiting, and
the split by channel and tier. Send nothing until Zalo says go for that batch. His go
applies to that batch only; it does not change `config.md` and it does not carry to
tomorrow.

**Outside approval mode**, send down the list, and after every single send:

1. Append the row to `sent-log.csv`.
2. Update the pipeline row: stage `SENT`, `last_touch` today, `next_due` today plus 3,
   `touches` incremented.
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

## Sending rules, non negotiable

These protect accounts that cannot be replaced. A restricted LinkedIn account ends this
rail; there is no second profile and no workaround.

**Per channel daily caps.** LinkedIn 15 cold DMs a day and 80 connection requests a week.
Instagram 10 a day. Facebook Messenger 10 a day. **35 a day maximum** with all three live,
and there is no configuration that produces more. Adding a channel is the only way to
raise the ceiling.

**The ramp.** Week 1 is 10 a day. Week 2 is 20 a day, and only if week 1 had zero
warnings. Week 3 and after is up to the channel caps, and only if week 2 had zero warnings
and replies are being read and reported daily. The current week and ceiling live in
`config.md`. A warning event of any kind resets the ramp to week 1.

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
`templates/batch.md`. Then, in the same session:

1. Write the event to the warning events block in `config.md`, `YYYY-MM-DD HH:MM ET |
   channel | what the screen said`.
2. Mirror it into `learnings.md` with the action taken.
3. Reset `ramp_week` to 1 and `daily_cold_ceiling` to 10.
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
active hold, then capped again by the ramp ceiling.** State that arithmetic in the session
header so a halved channel is visible rather than silently applied.

**Honor every opt out instantly and permanently.** DEAD is DEAD, on every channel, forever.

**Be truthful about who is sending and why.** It is Zalo, offering his service. No
fabricated referrals, no invented mutual connections, no pretending to be a customer.

**Quality floor.** If the metro cannot produce enough researched prospects to fill the
quota, send fewer. Never pad a batch with an unresearched row.

## The message system, in short

Full copy is in `templates/messages.md`. The shape that cannot change:

**Message one has four parts and nothing else.** How you found him (a fact you can see),
why him (the specific thing you noticed about his business), what we do in his language
(answers calls and texts in about five seconds, 24/7, books the job into the calendar),
and a question he can answer in four words. No pitch, no link, no meeting ask.

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
| 1. Nobody is replying | 30 cold sends across at least 2 tiers, zero replies of any kind | messages are not landing (LinkedIn filtering, IG Requests folder); the sending profile has no credibility; the evidence is not sharp; the copy | stop new batches, report the counts by tier and channel, name the first cause to check | the session |
| 2. One channel is dead | 15 sends on a channel, zero replies, while another channel is replying | delivery on that channel, not the copy | stop that channel, keep the others, report | that channel |
| 3. Replies are not reaching Zalo | 3 rows at `REPLIED` for more than 2 days with no stage movement | the report is not being read, or he is blocked | lead the report with them, say how long each has waited | nothing |
| 4. Evidence is going stale | 3 rows in one session pulled for dead evidence | the seed list has aged | report it, name the date range of the stale rows, ask for a refresh of `prospects.csv` | nothing |
| 5. Two weeks, nothing | 14 days of sending, zero replies on every channel | something structural: account standing, delivery, or market fit | stop the cold track entirely and say so plainly. Do not keep generating batches | the cold track |

A warning event is not a health check; it stops a channel immediately and unconditionally,
per the sending rules.

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
  seed evidence trusted for 7 days, one quoted owner search, 3 loads and 4 minutes per
  prospect, 40 minutes per session, the research ledger.
- `call-one-pager.md`, Zalo's call sheet. Prices are fields, not numbers.
- `RUNBOOK.md`, how M or Zalo starts a session, and how to verify Codex sees this skill.
- `templates/messages.md`, the copy contract and every message shape.
- `templates/pipeline.csv`, `templates/sent-log.csv`, the two working files' headers.
- `templates/batch.md`, `templates/report.md`, the two documents written per session.
- `templates/config.md`, `templates/proof.md`, `templates/learnings.md`, seeded once.
