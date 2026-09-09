# Batch [YYYY-MM-DD]

Astra writes this file to the working folder as `batch-YYYY-MM-DD.md` in every session,
before any message is sent. In approval mode it is the artifact Zalo reads and approves.
Outside approval mode it is still written first, then Astra works down it and updates each
status line as it sends.

**A status line in this file is a working note. The audit trail is `sent-log.csv`, and
nothing counts as sent unless it has a row there.**

---

## Session header

**Mode:** approval_mode on, nothing sends until Zalo says go for this batch
**Ramp:** week [N] of the ramp, ceiling [N] cold sends today
**Quota today:** LinkedIn [n] of 15, Facebook [n] of 10, Instagram [n] of 10, total [n] of [ceiling]
**Channels live:** LinkedIn, Facebook, Instagram
**Drafted:** [n] cold, [n] bumps
**Health checks:** all clear (or: CHECK [n] TRIPPED, see the report)

Ordering inside this file: grouped by channel so each app opens once, and inside a channel
cold tier A, then B, then C, then D, then the bumps due on that channel.

---

## LinkedIn

### 1. [Owner Name], [Company], tier A

**Open:** https://www.linkedin.com/in/...
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** A-li-P1
**Evidence:** [the verbatim sniper fact; "seed, tranche dated YYYY-MM-DD" when the tranche is under 7 days old, otherwise the date it was re confirmed]
**Side note:** [the extra true detail, from the homepage]
**Budget:** [n] loads, [n] seconds

**Invitation note** ([n]/300 characters, the whole artifact for a LinkedIn row; the
acceptance follow up is fixed copy in `templates/messages.md`):

```
[The note. Under 300 characters. Every token filled. No brackets.]
```

**Status:** DRAFT

### 2. [Owner Name], [Company], tier C

**Open:** https://www.linkedin.com/in/...
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** C-li-P2
**Evidence:** [verbatim; seed date or the date re confirmed]
**Side note:** [detail]
**Budget:** [n] loads, [n] seconds

```
[Message]
```

**Status:** DRAFT

### 3. [Owner Name], [Company], bump 1 of 2

**Open:** https://www.linkedin.com/in/...
**Prospect id:** [id] · **First touch:** [YYYY-MM-DD] · **Variant:** A-li-P1
**New fact this bump adds:** [what is new, because a bump with nothing new does not go]

```
[Bump message]
```

**Status:** DRAFT

---

## Facebook Messenger

### 4. [Owner Name], [Company], tier D

**Open:** https://www.facebook.com/... (personal profile, not the business page)
**Prospect id:** [id] · **Metro:** [metro] · **Variant:** D-fb-P1
**Evidence:** [the strongest true side note, since tier D has no sniper signal]
**Side note:** [detail]

```
[Message]
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

## Status values

| Value | Meaning |
| --- | --- |
| `DRAFT` | written, not sent, waiting on approval or on its turn in the pacing queue |
| `CONNECT SENT YYYY-MM-DD HH:MM ET` | LinkedIn connection request with the note sent; a `CONNECT` row exists in `sent-log.csv`; pipeline row stays `FOUND` until the message goes out after acceptance |
| `SENT YYYY-MM-DD HH:MM ET` | sent, and a row exists in `sent-log.csv` with the same timestamp |
| `HELD, cap reached` | the channel hit its daily cap before this entry; it rolls to tomorrow |
| `HELD, channel stopped` | a warning event stopped that channel for the day |
| `PULLED, evidence stale` | the ad stopped or the job post came down before sending; row goes back to FOUND |
| `PULLED, [reason]` | anything else that stopped it, with the reason in plain words |

## Rules while sending

- One message at a time. A randomized gap of 2 to 5 minutes between sends, every time.
- Never a platform bulk, broadcast, sequence or automation feature. Type it, send it.
- Only Zalo's own accounts. Never a second profile to raise the ceiling.
- Any captcha, "slow down", "you are sending too fast", restriction notice or unusual
  login prompt: stop that channel for the day immediately, log the event, report it.
- A prospect who ever said stop is DEAD and is not in this file. If one appears here, it
  is a bug: pull it and say so.
