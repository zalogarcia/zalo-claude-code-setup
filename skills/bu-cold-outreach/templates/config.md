# Cold Outreach Config

Astra reads this file at the START of every session, before anything else, and states
the mode, and then PER CHANNEL the ramp week and today's quota, in its first lines of
output. Zalo owns this file. Astra edits only the fields marked "Astra maintains".

## Mode

```
approval_mode: on
```

`on` (the default): Astra researches, drafts, writes `batch-YYYY-MM-DD.md`, and sends
NOTHING. It reports where the batch file is and how many drafts are waiting. Zalo reads
the file and says go for that batch before a single message leaves.

`off`: Astra sends within the caps, the ramp and the pacing rules without asking. Bumps on
unanswered first touches do NOT count against the daily cold cap, because the caps are cold
first touch caps, but they DO count for pacing: the 2 to 5 minute gap applies to every
message typed in these apps.

Changing this file is the only way to change the mode. Astra never flips it, and a message
in the chat saying "you can send now" applies to the ONE batch named in it, not to the file.

## Channels

Set `active: yes` only for accounts Zalo is logged into in the codex-bare Chrome profile
and that are older than about 6 months with a real photo and a bio that says what he does.

| Channel | Active | Account | Daily cold cap | Other cap |
| --- | --- | --- | --- | --- |
| LinkedIn | yes | Zalo Kabche | 15 | 80 connection requests per week |
| Facebook Messenger | yes | Zalo Kabche | 10 | |
| Instagram | no | Zalo Kabche | 10 | |

Maximum cold volume is the sum of the caps of the ACTIVE channels, and 35 a day if all
three ever run at their caps. There is no configuration that produces more. Adding a
channel is the only way to raise the ceiling, and no hold, mode or ramp week ever raises a
cap above the number in this table.

A channel whose Active column says no gets no ramp and no sends. Opening it is Zalo
setting Active to yes and giving it a start date in the ramp section, which buys it a
week 1 of its own and takes nothing from the channels already running.

**Active yes plus a start date in the FUTURE is a correctly configured channel, not a
contradiction** (added 2026-09-12). That is how a channel is opened ahead of time: the
Active flag says Zalo wants it, the start date says when it begins, and the quota
arithmetic below returns zero for it until that date arrives. Nothing on that channel needs
a prose line or an `active: no` to hold it back, and nobody has to remember to read one.

## Channel holds (Astra maintains)

Written when a warning event escalates past the same day stop, and read before computing
any quota. Format: `channel | cap N or stopped | until YYYY-MM-DD | reason`. A captcha or a
"slow down" halves that channel's cap for 7 days. A formal restriction or temporary block
stops that channel for 7 days. Astra removes a hold once its date has passed and reports it
as lifted. Zalo is the only one who lifts a hold early.

**A hold whose `until` is a CONDITION rather than a date is never auto lifted** (added
2026-09-12). It comes off when the condition is met and somebody says so, and until then it
binds every quota computation. The ramp holds written in the ramp section below always get a
matching line here, because this block is what the arithmetic reads.

```
(none)
```

Today's quota per channel is the cap in the table above, reduced by any active hold, then
capped again by that channel's own ramp ceiling below.

## Ramp, one per channel (restructured 2026-09-12)

Every ACTIVE channel carries its own start date, its own week and its own ceiling. Opening
a channel never costs an open one a send, and a channel that gets held or reset never drags
the others back with it. Before 2026-09-12 there was one shared ramp for all three, which
made opening a second channel either impossible or a silent halving of the first.

Astra maintains the derived `ramp_week` and `daily_cold_ceiling` lines. A channel's week 1
is the 7 days from its own start date.

### LinkedIn

```
linkedin_ramp_start_date: YYYY-MM-DD
linkedin_ramp_week: 1
linkedin_daily_cold_ceiling: 10
```

### Facebook Messenger

```
facebook_ramp_start_date: YYYY-MM-DD
facebook_ramp_week: 1
facebook_daily_cold_ceiling: 10
```

Write a real date here to open the channel. Until that date arrives Facebook's quota is
zero and the session header says which date it is waiting for.

Facebook's cap is 10, so its week 1 ceiling is already the cap: week 2 and week 3 raise
nothing on this channel. The J arm in `templates/messages.md` types three messages per
prospect, so 10 cold first touches is up to 30 typed messages, each taking the 2 to 5
minute pacing gap. Send fewer and report the real number rather than compress the gap.

### Instagram

Inactive by default. No ramp until Zalo activates it in the channel table and writes
`instagram_ramp_start_date` here.

### The ladder every channel climbs, separately

| Ramp week | Cold first touches per day | Condition to advance |
| --- | --- | --- |
| 1 | 10 | none |
| 2 | 20, and never above that channel's own cap | zero warnings, captchas or restrictions ON THAT CHANNEL in its week 1 AND that channel has a measured delivery number |
| 3 and after | that channel's cap (LinkedIn 15, Facebook 10, Instagram 10) | zero warnings on that channel in its week 2 AND replies read and reported daily |

**Zero warnings is a safety condition, not a funnel condition, and it is not enough on its
own.** A channel does not advance while it has no measured delivery rate. The measured
number, per channel:

- **LinkedIn:** at least 20 CONNECT notes have reached 14 days old, so there is an
  acceptance rate to read.
- **Facebook and Instagram:** at least 20 delivered owner DMs have reached day 7, so there
  is a reply rate to read.

Doubling volume into an unmeasured gate spends the scarce tiers fastest and learns nothing
(2026-09-12: 43 of 144 tier C rows nationwide were consumed in five days with zero
delivered messages).

### Today's quota arithmetic, stated in the session header

Per channel, in this order:

0. Read that channel's `<channel>_ramp_start_date`. If it is missing, still the literal
   `YYYY-MM-DD`, unparseable, or a date LATER THAN TODAY, that channel's number is zero and
   the rest of the arithmetic is not run for it. Print it as
   `not yet started, waiting for YYYY-MM-DD, quota 0` in the session header.
1. Start at that channel's daily cold cap from the channel table.
2. Reduce it by an active hold on that channel.
3. Cap it again by that channel's `daily_cold_ceiling`.
4. On LinkedIn only, also read the weekly invitation cap: 80 minus the CONNECT rows in
   `sent-log.csv` from the last 7 days. If what is left is smaller than the number from
   step 3, that remainder is today's LinkedIn number.
5. Subtract what already went out on that channel today.

**A connection request is a cold first touch and consumes a daily slot**, as well as being
the denominator for the 80 per week limit. It is counted against both budgets and both bind.
The daily number is not a DM only number: the skill used to say an invitation counted
"against the 80 per week limit, not the 15 DMs per day", which would have allowed a whole
weekly remainder to go out in one afternoon.

**A missing, placeholder or unreadable ramp field is week 1, not the cap.** If a channel's
`ramp_week` or `daily_cold_ceiling` is absent or unparseable, treat that channel as week 1
at 10 and say so in the session header. If its `<channel>_ramp_start_date` is missing or
still the literal `YYYY-MM-DD`, that channel has no ramp and sends nothing until Zalo writes
a date. A ramp field never fails open to the cap.

**A start date in the FUTURE is the same state: no ramp and no sends until that date**
(added 2026-09-12). The week and ceiling fields are filled in ahead of the date on purpose,
so reading them without reading the date yields a quota for a channel that has not opened:
on 2026-09-13 a Facebook block carrying `facebook_ramp_start_date: 2026-09-15`,
`facebook_ramp_week: 1` and `facebook_daily_cold_ceiling: 10` must compute "Facebook: not
yet started, waiting for 2026-09-15, quota 0", never "Facebook: 10 left". Week 1 is the 7
days FROM the start date, so it cannot have begun before it.

The result can never be above the channel's cap in the table, whatever the ramp says. The
day's total is the sum of the per channel quotas, and nothing computes a total first and
then divides it.

A **cold first touch** is one prospect, not one typed message. A three part joke sequence
is ONE cold first touch against the cap and three typed messages against the pacing gap.

### Warning events reset the channel they happened on

Astra sets THAT channel's `ramp_week` to 1 and its `daily_cold_ceiling` to 10, writes the
event into `learnings.md`, and reports it. The other channels keep their ramps, because a
captcha on one platform is evidence about one account's standing on that platform, and the
channel holds block above is already per channel.

**The exception:** two warning events on two different channels inside 7 days resets EVERY
channel to week 1 and 10 a day. That pattern is about how we are sending, not about one
platform, and it is the one case where a channel that has done nothing wrong still pays.

Zalo is the only one who can advance a week early.

## Warning events (Astra maintains, append only)

One line per captcha, "slow down", "you are sending too fast", restriction notice or
unusual login prompt. Format: `YYYY-MM-DD HH:MM ET | channel | what the screen said`.

```
(none yet)
```

## Metros in play

```
metros: countrywide (tranche 1: Phoenix, Dallas-Fort Worth, Houston, Tampa, Orlando, Miami, Atlanta, Las Vegas, San Antonio, Austin, Charlotte, Jacksonville, plus the nationwide LinkedIn rail)
```

Geography is countrywide by Zalo's decision on 2026-09-08. The metros actually in play are
whatever `prospects.csv` contains; update this line when a new tranche is added. Miami is
the home metro and unlocks the "I'm local" line.

## What is deliberately not in this file

No calendar link and no VSL link. Astra never sends a booking ask, a demo link or a VSL,
so it has no use for either. Everything after a prospect replies is Zalo's rail; see the
"Zalo does" section of `SKILL.md`.
