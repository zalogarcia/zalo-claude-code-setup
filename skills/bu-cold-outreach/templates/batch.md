# Batch [YYYY-MM-DD]

Astra writes this file to the working folder as `batch-YYYY-MM-DD.md` in every session,
before any message is sent. In approval mode it is the artifact Zalo reads and approves.
Outside approval mode it is still written first, then Astra works down it and updates each
status line as it sends.

**A status line in this file is a working note. The audit trail is `sent-log.csv`, and
nothing counts as sent unless it has a row there.**

**One entry per prospect, one message per entry (Zalo, 2026-09-22).** Every entry in this
file is the ONE message that prospect gets from Astra unless they reply, or a connection or
friend request that carries no message. There are no bumps, no takeaways, no continuations
and no second channel for a prospect already messaged, and `scripts/note-lint.py` refuses a
batch that has any.

---

## Session header

**Mode:** approval_mode on, nothing sends until Zalo says go for this batch
**LinkedIn:** ramp week [N], ceiling [n], cap 15, hold [none], sent today [n], left [n]. Invitations [n] of 80 in the last 7 days
**Facebook:** ramp week [N], ceiling [n], cap 10, hold [none], sent today [n], left [n] (or, before the start date: not yet started, waiting for [YYYY-MM-DD], quota 0)
**Instagram:** inactive, no ramp (or: ramp week [N], ceiling [n], cap 10, left [n])
**Total today:** [n], the sum of the per channel numbers above, never a number divided up
**Drafted:** [n] one messages (cold first touches), [n] connection requests with no note, [n] friend requests. Bumps: none, retired 2026-09-22
**Owed their one message today:** [n] accepted note-less connections, [n] accepted friend requests
**Went COLD today:** [n] rows, one message and no reply by day 7. Nothing is drafted for them
**Test arms in this batch:** [n] `D-fb-J1`, [n] `D-fb-J2`, [n] control
**Joke repeats:** [joke]: [n] rows, [joke]: [n] rows. Cap is 4 rows per joke per day
**Typed messages today:** [n] total across all channels, one per prospect, at a 2 to 5 minute gap each
**Lint:** [the `ALL PASS` line from `scripts/note-lint.py`, run inside the working folder, naming the folder the one message rule was checked against. A `COPY PASS` line means the batch is NOT cleared]
**Owner resolution:** [n] Facebook rows resolved to a verified personal profile, [n] held
**Health checks:** all clear (or: CHECK [n] TRIPPED, see the report)

Ordering inside this file: grouped by channel so each app opens once, and inside a channel
tier A, then B, then C, then D. There is no bump section.

---

## LinkedIn

### 1. [Owner Name], [Company], tier D, connection request

**Open:** https://www.linkedin.com/in/...
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** D-li-P1 (the one message the accepted thread will carry)
**Evidence:** [the verbatim fact the one message will open on, kept for the day of the accept]
**Budget:** [n] loads, [n] seconds

**Connection request, NO note** (option A, Zalo 2026-09-22). Nothing is typed into the
request. In `notes.json` this entry is `"kind": "connect"` with an empty `"text"`, and the
lint fails it if the text is not empty. The one message goes after the accept, as its own
entry in that day's batch.

**Status:** DRAFT

### 2. [Owner Name], [Company], tier C, the one message after the accept

**Open:** https://www.linkedin.com/in/...
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** C-li-P2
**Accepted:** [YYYY-MM-DD], request sent [YYYY-MM-DD] with no note (`sent-log.csv` CONNECT row with an empty `message_text`)
**Evidence:** [verbatim; re confirmed live today]
**Side note:** [detail]

([n]/420 characters. The ONE message this prospect gets unless he replies.)

```
[Message. Every token filled. No brackets.]
```

**Status:** DRAFT

### 3. [Owner Name], [Company], tier A, open profile message (or InMail)

**Open:** https://www.linkedin.com/in/...
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** A-li-O1 (or A-li-I1)
**Evidence:** [verbatim; seed date, and re confirmed live today]
**Side note:** [detail]
**Budget:** [n] loads, [n] seconds

```
[Message, under 420 characters]
```

**Status:** DRAFT

---

## Facebook Messenger

### 4. [Owner Name], [Company], tier D

**Open:** https://www.facebook.com/... (the owner's personal profile, verified by the intro or posts naming the business; a business page URL here is a bug, pull the row)
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** D-fb-P1
**Evidence:** [the strongest true side note, since tier D has no sniper signal]
**Side note:** [detail]

(ONE message. The blank line is Shift+Return twice inside it, never a second send.)

```
[Message]
```

**Status:** DRAFT

### 4b. [Owner Name], [Company], tier D, test arm `D-fb-J1`

**Open:** https://www.facebook.com/... (the owner's PERSONAL profile, verified per Step 2F of the hunting playbook; a business page URL here is a bug, pull the row)
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** D-fb-J1
**Opener type:** trade joke
**Side note:** [any true detail seen for free, for Zalo when the thread opens. The joke arm's messages carry no fact, by design]
**Owner resolution:** [where the name came from, how the profile was verified, n loads, n seconds]

ONE message: the approved joke, setup then punchline, then the J1 ask, on one line with no
line break. One cold first touch against the cap and one pacing gap. If anything comes back
it is REPLIED and the thread goes to Zalo; if nothing comes back the row goes `COLD` at day
7 and nothing else is ever sent.

```
[The approved joke from templates/gold-notes.md, setup then punchline, then the J1 ask with the owner's first name. One line. No greeting before the joke.]
```

**Status:** DRAFT

---

## Instagram

### 5. [Owner Name], [Company], tier C

**Open:** https://www.instagram.com/...
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** C-ig-P1
**Evidence:** [verbatim, re confirmed today]
**Side note:** [detail]

```
[Message]
```

**Status:** DRAFT

---

## Facebook groups (NOT STARTED, added 2026-09-14)

**This section stays empty until Zalo opens the channel in `config.md` and the demo
interrupt gate has been run.** A batch carrying group posts while
`facebook_groups_ramp_start_date` says `NOT STARTED` is a bug, not a draft.

### 6. [Group name], [metro]

**Open:** https://www.facebook.com/groups/...
**Group:** [name] · **Members:** [n] · **Metro:** [metro] · **Variant:** [metro]-fg-G1
**Admin rules read:** [the group's own promo rule, in one line, or "no promo rule posted"]
**Demo number in the post:** [the number]

```
[Post]
```

**Status:** DRAFT

---

## Status values

| Value | Meaning |
| --- | --- |
| `DRAFT` | written, not sent, waiting on approval or on its turn in the pacing queue |
| `CONNECT SENT YYYY-MM-DD HH:MM ET` | LinkedIn connection request sent with NO note; a `CONNECT` row with an empty message exists in `sent-log.csv`; pipeline row stays `FOUND` until the one message goes out after acceptance |
| `FRIEND SENT YYYY-MM-DD HH:MM ET` | Facebook friend request sent, nothing typed; a `FRIEND` row exists in `sent-log.csv`; pipeline row stays `FOUND` until the one message goes out after acceptance |
| `SENT YYYY-MM-DD HH:MM ET` | the one message went out, and a row exists in `sent-log.csv` with the same timestamp and `stage` `SENT`. Nothing else is ever sent to this prospect unless they reply |
| `PULLED, already messaged` | the lint or the log shows this prospect already had their one message (on any channel); the entry never sends |
| `HELD, cap reached` | the channel hit its daily cap before this entry; it rolls to tomorrow |
| `HELD, channel stopped` | a warning event stopped that channel for the day |
| `PULLED, evidence stale` | the ad stopped or the job post came down before sending; row goes back to FOUND |
| `PULLED, [reason]` | anything else that stopped it, with the reason in plain words |
| `POSTED YYYY-MM-DD HH:MM ET` | a Facebook group post went up; a `GROUP_POST` row exists in `sent-log.csv`. Never a delivered message and never a cold first touch |
| `REMOVED BY ADMIN` | the post was taken down. Record it, do not repost in that group, and log it as a warning event if the account itself was actioned |

## Rules while sending

- One message per prospect, ever, until they reply. If a stray Enter sends part of a
  message, the rest is NOT sent as a second bubble; log what went out.
- One message at a time. A randomized gap of 2 to 5 minutes between sends, every time.
- Never a platform bulk, broadcast, sequence or automation feature. Type it, send it.
- Only Zalo's own accounts. Never a second profile to raise the ceiling.
- Any captcha, "slow down", "you are sending too fast", restriction notice or unusual
  login prompt: stop that channel for the day immediately, log the event, report it.
- A prospect who ever said stop is DEAD and is not in this file. If one appears here, it
  is a bug: pull it and say so.
