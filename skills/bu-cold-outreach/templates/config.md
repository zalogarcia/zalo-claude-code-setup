# Cold Outreach Config

Astra reads this file at the START of every session, before anything else, and states
the mode, the ramp week and today's per channel quota in its first lines of output.
Zalo owns this file. Astra edits only the fields marked "Astra maintains".

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
| Instagram | yes | Zalo Kabche | 10 | |

Maximum cold volume with all three live is 35 a day. There is no configuration that
produces more. Adding a channel is the only way to raise the ceiling, and no hold, mode or
ramp week ever raises a cap above the number in this table.

## Channel holds (Astra maintains)

Written when a warning event escalates past the same day stop, and read before computing
any quota. Format: `channel | cap N or stopped | until YYYY-MM-DD | reason`. A captcha or a
"slow down" halves that channel's cap for 7 days. A formal restriction or temporary block
stops that channel for 7 days. Astra removes a hold once its date has passed and reports it
as lifted. Zalo is the only one who lifts a hold early.

```
(none)
```

Today's quota per channel is the cap in the table above, reduced by any active hold, then
capped again by the ramp ceiling below.

## Ramp

```
ramp_start_date: YYYY-MM-DD
```

Astra maintains the derived line below. Week 1 is the 7 days from `ramp_start_date`.

```
ramp_week: 1
daily_cold_ceiling: 10
```

| Ramp week | Cold sends per day | Condition to advance |
| --- | --- | --- |
| 1 | 10 | none |
| 2 | 20 | zero warnings, captchas or restrictions in week 1 |
| 3 and after | up to the per channel caps (35 max) | zero warnings in week 2 AND replies read and reported daily |

A warning event of any kind resets the ramp: Astra sets `ramp_week: 1` and
`daily_cold_ceiling: 10`, writes the event into `learnings.md`, and reports it. Zalo is
the only one who can advance the week early.

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
