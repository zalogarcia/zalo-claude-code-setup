# Message System, Black Umbrella Cold DM

The copy contract for everything Astra writes. The Black Umbrella cold outreach strategy
outranks this file wherever they disagree, and this file is already written to match it.

**Astra writes and sends message ONE and its two bumps. That is the whole rail.** The
moment a prospect replies with anything at all, the thread becomes Zalo's: Astra records
the reply, marks the row REPLIED, and surfaces it in the report. The material at the bottom
of this file under "Zalo's rail" is reference for him, not a script Astra sends.

## The four parts of message one

Every first touch has these four parts in this order, and nothing else. No pitch, no link,
no attachment, no calendar ask.

1. **How you found him.** A fact that answers "who is this?" before he asks it. Something
   you can literally see on a screen. "Saw the front desk role you posted on Indeed."
2. **Why him.** The specific thing you actually noticed about HIS business, not his
   industry, and wherever the research allows, the thing that ties to the phones. This
   is the part that cannot be pasted into another company's DM, and it is the part Zalo
   reads first when he approves a batch (2026-09-09: a batch went back because the
   openers were services lists and ad dates). See "The specificity law" below.
3. **What we do, in his language, and that his demo exists.** The outcome, in the words he
   uses, plus the fact that a demo has been trained on his own website. "I trained a demo
   AI setter on your website. It answers your calls and texts in about five seconds,
   24/7, and books the job into your calendar." Never "omni-channel
   conversational agent", never "AI-powered solution". Zalo's decision, 2026-09-08: the
   demo claim goes in message one because he generates the demo in seconds the moment a
   reply lands, so the prospect never finds it missing.
4. **The dare, as a question he can answer in one word.** "Want to try and break it?"
   and, when there is room, the how: "Call it, text it, throw it your weirdest customer."
   Zalo's decision, 2026-09-09: the reply is a game, not a purchase. A skeptical owner
   says yes to a dare faster than to a sales asset, and a prospect who tries to break the
   demo has tested it, which is what sells it. Not a meeting ask, and still no link in
   message one: the link is message two, in the same thread, from Zalo.

Length: LinkedIn up to about 90 words, Facebook and Instagram up to about 60. If it needs
scrolling on a phone it does not get read.

## The offer law: sell the outcome, never the category (2026-09-14)

Source: `research/ai-agents-sales-2026-09-12.md`, the one finding all four voices in the
sweep agree on (buyers, sellers, vendors and creators), and the only one the vendors acted
on with their own names. Rosie's headline is "Never miss another call". My AI Front Desk
renamed itself Frontdesk. Jobber calls its product Receptionist. The seller quote is the
whole law: "the second you lead with AI, half of them go straight to so I could just do
that myself in ChatGPT for free." A cold caller who opens with "AI receptionist" reports it
"drops you into the same bucket as every other reseller who called them last week".

**The law is the FRAME, not the vocabulary, and this distinction is the whole thing.** The
product we are selling is an answered call and a booked job. The technology is the
mechanism, named once, in passing, because it is true. What is forbidden is the technology
as the PRODUCT CATEGORY.

| Forbidden, the tech as the product | What it is instead |
| --- | --- |
| "I help businesses with AI receptionists." | "Your phone gets answered after 5 and the job lands on your calendar." |
| "We build AI agents for home service." | "It picks up when nobody can and books the job." |
| "Our AI solution for HVAC." | "The calls you miss get answered and the job gets booked." |
| "AI-powered voice automation." | "It answers in about five seconds and books the job." |

**Zalo's P1 and P2 lines already obey this and do not change.** "I trained a demo AI setter
on your website that takes those calls 24/7 and books the job" names the mechanism once and
then spends the rest of the sentence on the outcome. That is the shape that works. He wrote
and approved that line on 2026-09-08 and it is not reopened by this law; a reading of the
research that banned the words "AI setter" would have failed every note he has ever
approved, which would make the law wrong, not the copy.

**Mechanical form.** `scripts/note-lint.py` carries both halves:

- `TECH_AS_CATEGORY` is in `BANNED`, so "ai receptionist", "ai agent", "ai assistant",
  "voice ai", "artificial intelligence", "our ai", "i help businesses" and the rest fail
  any note in any family, on any channel. They are matched on WORD BOUNDARIES, plurals
  included: "our ai" is inside "your air" and this is an HVAC skill, so a substring match
  failed a note that quoted the prospect's own air conditioning (2026-09-14 QA pass).
- Every note that carries an offer has to name BOTH halves of the outcome: an answered call
  ("answers", "picks up", "takes those calls") and a booked job ("books the job"). The
  fixed line is only the head of its sentence and the tail is drafted per row, so the
  outcome can drift out of a note that still matches `P1_LINE`. It cannot now.

## The position law: after hours and overflow, never replacement (2026-09-14)

Same source, the second of its ten findings. **We are never replacing the person who
answers the phone at 9 a.m.** The sweep's phrasing: "they will not fire their receptionist
for your voice agent", and two years of one seller's failed local outreach ended on the
sentence "I already have someone at the front desk". It is the single most reported
objection in the whole sweep and it ends the replacement pitch every time it is tried.

What we sell instead, in the owner's own terms: the calls that fall through. After hours,
lunch, both lines busy, the tech on a roof, the Sunday emergency. A live human path is part
of the product, not a concession: the buyer notes name "no instant path to a person" as a
top refusal reason.

**Tier B is not an exception to this and must not be read as one.** Tier B replaces a third
party ANSWERING SERVICE, which is a vendor taking messages for a hundred companies at $200
to $1,000 a month, not the person at the front desk. The sweep's strongest buyer segment is
exactly that: "2 to 5 plumber teams paying $600 to $1,000 to Smith or Ruby for messages
only". Replacing that service is the highest willingness sale in the ICP. Replacing his
receptionist is the sale that does not exist.

The pre written objection turn for the wall itself is under "The front desk wall, the
objection that ends the pitch" in Zalo's rail at the bottom of this file.

## The specificity law (2026-09-09)

The opener has to prove, in one clause, that a person looked at this business and not at
a list. Zalo returned the 2026-09-08 batch because "saw True Home handles HVAC and
appliance repair, with technicians on call 24/7" and "saw AAction Air's June 2 Facebook
ads" are true and generic: a services list is what every HVAC site says, and an ad date
ties to nothing.

What counts as specific, strongest first:

1. **A review quote about reaching them.** "Great work but took two days to call back",
   with the month. The problem in the customer's own words, and only his customers said
   it.
2. **The duties line from the job post**, quoted. "Answer incoming calls, texts and
   emails, schedule service appointments", with the shift ("Monday to Friday, 9 to 5").
   The shift IS the after hours gap. Not the role title alone.
3. **What the ad actually says**, quoted, plus where its clicks land. "Your $79 tune up
   ad is running right now, and Google says you close at 5." Never the ad's start date
   on its own.
4. **The hours gap** from the Google Business Profile, as numbers. "Closes 5 pm weekdays,
   closed Sunday."
5. **A thing he did or said himself.** A truck wrap he posted, a podcast line, an owner
   reply on a review, years in business in his own words on his About page.

What never counts as the opener: a list of services, "family owned", "great reviews", a
service area list, the ad's date, and "24/7 emergency service" on its own (every site
says it; it counts only paired with the question it raises: "your site promises 24/7
service and Google says the office closes at 5").

**The right review (2026-09-09, second return of the same batch).** Not every review is
an opener. The review has to show one of two things: a reachability complaint ("took two
days to call back", "went to voicemail"), or a PERSON handling a call outside office
hours, with the day or the time in it ("called me back Saturday", "came out after 10pm",
"I called at 9 pm"). A speed compliment with no day or time in it ("very responsive",
"reached out right away") is not the opener on its own; it argues against the offer
unless a bridge clause turns it around, and even then it is the weakest of the five.
Search the reviews for: after hours, Saturday, Sunday, pm, called back, call back,
voicemail, no answer, never heard back, same day.

**The bridge clause, mandatory.** Between the specific and the "what we do" line there is
ONE short clause that says what the specific means for the phones. Without it a quote
that praises how fast they answer reads as "you already do this well" followed by "buy
the thing that does this", and the owner stops reading. Shapes, by opener type:

| Opener type | Bridge clause |
| --- | --- |
| A person handled an after hours call | "Someone at AAction is picking up at 10pm." / "That is a person doing it by hand." |
| The owner himself answered | "That is you on the phone." |
| Hours gap | "Every call after 4 lands somewhere." |
| Ad running | "Your Facebook ad is live, so those calls keep coming." |
| Hiring for the phones | "That is the seat this replaces." / "Until that hire starts, the phone is on you." |
| Reachability complaint | "That is the call this catches." |

The bridge is a plain sentence, under 60 characters, no cleverness. It is the line that
makes the demo claim follow from the research instead of sitting next to it.

**The arithmetic bridge (added 2026-09-14).** The bridge has one more shape available to
it, and the research says it is the strongest one there is. From
`research/ai-agents-sales-2026-09-12.md`, finding 3: the close is the owner's own math,
missed calls a week times ticket times close rate, which sellers report he does in his head
in about four seconds, and five creators converge on it independently. So where the fact
supports it, the bridge hands him the arithmetic instead of only naming who is on the
phone. That also answers the 2026-09-11 register lesson, that a mechanical bridge ("That's
a customer calling for an update") reads as a form: a number he can check against his own
week does not.

| Opener type | Arithmetic bridge |
| --- | --- |
| Hours gap, both ends visible | "Closed at 5 and open at 8 is fifteen hours a day that phone's on somebody." |
| Hours gap plus a closed day | "That's every evening plus the whole of Sunday." |
| Review naming how many times | "That's two calls you already know about, and she's the one who wrote it down." |
| Multi location, one number | "Three areas, one line, and they don't take turns." |
| Ad running plus posted hours | "The ad runs past 5 and the office doesn't." |

**The hard constraint, and it is the one that makes this safe (2026-09-12, Astra's
correction of M).** A bridge may only do arithmetic that is INSIDE what the review or the
posted hours actually show. Closed at 5 and open at 8 is fifteen hours because the profile
says both numbers. "Two messages" is two because the reviewer wrote it. What the bridge may
never do is invent the number that is not on the screen: how many calls he misses, what a
job is worth, what a percentage of them close, what it would earn him. Those are HIS
numbers, he is the only one who has them, and the sweep is explicit that the close works
because he does the multiplication himself.

So: the arithmetic bridge hands him the SHAPE of his own math. The full missed call math
and "one recovered job pays for the year" belong on the call, in `call-one-pager.md`, where
he is the one supplying the ticket and the close rate. Never in message one.

`scripts/note-lint.py` enforces the half it can see without reading the fact: a rate of
calls or jobs per day, week, month or year, a "pays for itself" claim, and a money amount or
a percentage **in the same sentence as a result** (his calls, jobs, leads, installs,
bookings, revenue, voicemail, what he is missing or losing) all fail any note in any family.

The sentence scoping is the part that matters. Quoting HIS OWN advertised price is approved
opener type 3 above ("Your $79 tune up ad is running right now, and Google says you close at
5"), and two notes carrying one went out on 2026-09-10. A flat ban on the dollar sign failed
both, which is the false positive class this lint exists to prevent (2026-09-14 QA pass). His
promo price is a fact on a screen; "$400 a month of calls in voicemail" is a claim about his
results. Worked examples of the allowed shape are in `templates/gold-notes.md`.

The test before the note is written: **could this clause be pasted into another company's
DM with only the name swapped?** If yes, it is not the opener. Find one of the five above
inside the load budget, or hold the row with "no specific found" and take the next one. A
held row beats a generic send; a generic send burns the profile's one shot at that owner.

## The rules that do not bend

1. **State facts you read. Never claim research effort.** If you can point at it on a
   screen, say it. "I went through your whole website" is out. The ONE claim of work that is
   allowed is the demo line in part 3, because Zalo generates the demo in seconds when the
   reply lands (his decision, 2026-09-08, overriding the earlier "no demo in message one"
   rule). Everything else stays a fact you can see.
2. **No invented proof, numbers or urgency.** No results nobody gave us, no capped spots,
   no "before I move on to the next city". Anything numeric has to be written in
   `proof.md` and authorized, and Astra's messages carry none of it regardless.
3. **Message one gets the yes. Message two is the link.** Astra's job ends at the reply.
   Zalo generates the demo on that business and sends the link, in the same thread.
4. **Volume before judgment.** Work the ramp, fill the quota, judge nothing before the
   sample is real. A variant under 20 sends has no rate, only a count.
5. **Match the channel.** LinkedIn is warm and professional, no emoji, full sentences.
   Facebook and Instagram are casual, contractions, shorter, at most one emoji and only
   where it is natural.
6. **Banned phrases.** "I hope this finds you well", "solutions", "streamline",
   "revolutionize", "just checking in", "circle back", "reaching out", "touch base",
   "synergy", "game changer", "cutting edge", "leverage". Also banned: em dashes and en
   dashes anywhere in a message, on any channel.
7. **One true specific per message.** If Astra cannot find one true specific thing about
   that business, the prospect is not researched enough. Research more or swap the row.

## Tokens

`[Name]` owner first name, or `[Mr./Ms. LastName]` on LinkedIn when the last name is known
and the tone calls for it. `[Company]` the business name. `[Trade]` HVAC, plumbing, or
"HVAC and plumbing". `[Evidence]` the verbatim sniper fact for this tier. `[SideNote]` the
extra true detail from the hunt. `[Metro]` his city.

Every token is filled before the message is written into the batch file. A batch entry
containing a bracket is a bug, not a draft.

## The "what we do" line, P1 and P2 (the phrasing split test)

Alternate these within each tier and channel so the two stay within a few sends of each
other. The variant id in `learnings.md` is `<tier>-<channel>-<phrasing>`, for example
`A-li-P1`.

**P1, the mechanism:**

> I trained a demo AI setter on your website. It answers your calls and texts in about
> five seconds, 24/7, and books the job straight into your calendar. Want to try and
> break it? Call it, text it, throw it your weirdest customer.

**P2, the replacement:**

> I built a quick demo off your website: the thing that picks up when nobody can, calls
> and texts, day or night, and books the job into your calendar instead of taking a
> message. Want to try and break it?

**Short forms for the LinkedIn note** (same variant id; the note has 300 characters and
the specific opener plus the bridge come first). Plain sentences, never a colon list of
features: the list form ("answers calls and texts in about five seconds, 24/7, books the
job into your calendar") reads like a spec sheet and was retired 2026-09-09.

> P1 short: I trained a demo AI setter on your website that takes those calls 24/7 and
> books the job. Want to try and break it?

> P2 short: I built a quick demo off your website: it picks up when nobody can, day or
> night, and books the job. Want to try and break it?

"takes those calls" and "picks up" point back at the bridge clause, so the three beats
read as one thought. Swap "those calls" for "them" or "it" when the bridge already said
"calls".

Both are literal descriptions of what the system does. Neither carries a number about a
result. Do not write a P3 by hand; the weekly review writes it, in the working copy of
this file, changing one element only.

**Since 2026-09-08 P1 and P2 end with the demo offer, and since 2026-09-09 that offer is
the dare, so in every template below the closing diagnostic question is DROPPED: opener line(s), then [P1 or P2], then nothing.**
The openers stay exactly as written. On LinkedIn the whole thing also has to fit a 300
character invitation note when the message travels inside the connection request.

## The LinkedIn invitation note (the default LinkedIn send since 2026-09-08)

On every owner profile opened on 2026-09-08 the Message button opened a paid Sales
Navigator prompt, so the LinkedIn send is a connection request with the message as its
note. The note is the whole artifact for a LinkedIn row; no separate full length message
one is drafted.

Shape, 300 characters or fewer, counted before it is pasted:

> Hi [First], [the specific, one sentence]. [The bridge clause, one short sentence].
> [P1 short or P2 short, verbatim]

Four beats, one sentence each, 180 to 290 characters. The specific is never what gets
cut: when the note runs long, the "what we do" line loses words before the specific
loses one. The second side note stays in the batch entry for the bump.

**Test arm N1, the note with no pitch (added 2026-09-12, tier D only, 20 sends).** The
invitation note is not a DM. It is a card a stranger sees next to an unknown face, and its
only job is to get the accept; the pitch has a whole message waiting for it on the other
side. Arm N1 carries the first two beats and stops:

> Hi [First], [the specific, one sentence]. [The bridge clause, one short sentence].
> Mind if I ask you something about it?

Shape: three beats, 3 to 5 sentences, 120 to 240 characters, and it ends on the question.
No demo claim, no dare, no link, contractions throughout, same specificity law and same
paste test as the control. The specific keeps whatever numbers it needs (a quoted shift, an
hours gap, "she called at 9 pm"), because those are facts read off a screen; what is banned
here is what is banned everywhere, a number about a RESULT. The specific is still researched exactly as hard; this
arm removes the pitch, not the work.

**The 120 to 240 character band is enforced by the lint, not just written here** (2026-09-12).
The arm measures a SHORT no pitch card, so a 267 character N1 is a different artifact even
though it sits inside LinkedIn's 300 character limit. The arm is LinkedIn only in the lint
too: an `N1` id on facebook or instagram fails.

Variant id `<tier>-li-N1`. **Live today: `D-li-N1` only.** `C-li-N1` is registered in the
scoreboard and is NOT sendable: tier C stays on the control while the accept gate has no
number, and it opens only when Zalo says so or when the gate is measured. Tier A and B keep
the control throughout, because those rows are too scarce to spend on a channel test.

It runs at 20 sends against 20 sends of the four beat note on the same tier, and it is
judged at 14 days on the ACCEPTANCE rate, not the reply rate, because acceptance is the
gate it is trying to move.

**The N1 acceptance follow up, fixed copy, N1 rows only.** When an N1 row is accepted, this
is its message one, and it carries the pitch the note left out so the prospect gets the
same offer one message later:

> Thanks for connecting, [First]. I trained a demo AI setter on [Company]'s website that
> takes those calls 24/7 and books the job. Want to try and break it?

**Every other row keeps the existing acceptance follow up unchanged** ("Thanks for
connecting, [First]. The demo on [Company]'s site is ready when you are. Want to try and
break it?"), because for those the note already carried the pitch.

Evidence for the arm: the offer first shape is the single largest disagreement between our
rail and the most detailed cold DM teaching available (`2XvCxwDHSgM`, a whole video titled
"WHY MAKING THE OFFER FIRST KILLS THE CONVERSATION"; `lFkHRLHGHVc` [00:01] and [00:59],
where the opener replaced is a free deliverable offered up front and the replacement is a
question). Evidence against it, which is why it is an arm and not a rule: his model assumes
a live chat thread with a prospect who logs in daily, and a bare permission question gives
a busy owner no reason to accept an invitation from a stranger. The 20 versus 20 exists to
settle that, and neither side of it gets declared a winner under 20 sends.

**Sounding like a person, the checks before a note ships (2026-09-09):**

- Time references the way people say them: "Clay's review this summer", "Jennifer's
  review from June", "a review last month". Never "3-month-old review", never an exact
  date unless it is the job post date.
- The reviewer's first name only when quoting or paraphrasing that review. It shows the
  research; it is not filler.
- No filler openers: "caught my eye", "I noticed", "hope you're well", "I came across".
  Start with the fact.
- No colon feature lists, no "24/7" more than once, no three adjectives in a row.
- Read it once as the owner: if any sentence is there to sound smart instead of to say
  something, cut it.
- **Contractions, always** (Zalo, 2026-09-09, "still sounds robotic"): "that's", "you're",
  "somebody's picking up", "ad's running". A note with zero contractions reads as
  written by a machine, whatever else it does right. The fixed P1 and P2 lines stay as
  written; everything around them sounds like a text to a peer.
- **Vary the opener shape across a batch.** Not every note starts "[Name]'s review this
  summer says". Some start with "saw", some with the fact, some with the quote itself.
  The four beats are the skeleton, not the wording; if three notes in a batch open the
  same way, rewrite one.
- **Say what happened, not what the review "says".** "Clay called after hours and Charles
  came out past 10pm" beats "Clay's review says he called after hours". Name the
  reviewer once, then talk about the event.
- **The bridge is casual and short.** "So somebody's picking up at 10 at night." Not
  "That is a person handling the call by hand."

**The gate, mandatory before the batch file is written (Zalo, 2026-09-09).** Three
layers, in this order, every session:

1. **Read `templates/gold-notes.md` first**, before drafting a single note. That is the
   register. Draft toward it.
2. **Run the lint.** Write the drafts to `evidence/YYYY-MM-DD/session-N/notes.json`
   (a list of `{"entry", "channel", "variant", "text"}`, plus `"part"` on joke notes and
   `"sent_parts"` with `"joke_setup"` on a joke continuation) and run
   `python3 ~/.claude/skills/bu-cold-outreach/scripts/note-lint.py <that file>`. It is
   deterministic: contractions, banned phrases, links, unfilled tokens, length, dashes,
   sentence count, and opener diversity across the batch, plus the laws of the note's own
   variant family. The control (`P1`, `P2`) must carry the bridge, the dare and its fixed
   "what we do" line. `N1` must carry none of those and must end on its fixed question.
   `J1` and `J2` must be the approved joke copy, three parts per prospect, with the
   punchline matching its own setup and no digit anywhere. A `part` field
   (`setup`, `punchline`, `ask`) is required on joke notes and ignored elsewhere.
   `ALL PASS` is required; a FAIL is a rewrite, never a send. Paste the lint output
   into the batch session header. The lint was built from the three returned rounds of
   2026-09-09 and fails every one of them.

   Four more laws it enforces, added 2026-09-12 after the audit of `184db72`: each arm is
   held to its own channel, so an `N1` note only passes on linkedin and a `J` note only on
   facebook; an `N1` note is 120 to 240 characters, the band written below; no joke opens
   more than 4 rows in one day; and a joke sequence interrupted on an earlier day is
   finished with the continuation marker rather than by re typing what already went out.

   **The continuation marker.** A joke entry whose setup, or setup and punchline, already
   went out carries only what is left, and every one of its notes carries
   `"sent_parts"` (what was delivered, in send order, read off `sent-log.csv`: `["setup"]`
   or `["setup", "punchline"]`) and `"joke_setup"` (the approved setup text that thread is
   carrying, so the punchline is still checked against its own setup a day later). The parts
   in the batch have to be the contiguous run following `sent_parts`, so an ask cannot jump a
   punchline that never went out. The order the notes are LISTED in does not matter; which
   parts are present does. The marker is an assertion about `sent-log.csv` that the lint
   cannot verify by itself, so the batch entry cites the rows it is claiming. Padding a
   batch with already sent text to get a pass is the one thing this must never become: the
   lint would then be reading yesterday's sends instead of today's drafts.

   A continuation row counts against the joke repetition cap and against pacing, and it does
   NOT consume a cold first touch slot: that slot was spent the day its setup went out.
3. **The humanizer pass**, below, for what a regex cannot see.

**The humanizer pass.**
Run every note through the humanizer skill at
`/Users/zalo/dev/zalo-kabche-brand/.claude/skills/humanizer/SKILL.md` (read it; its 28
patterns, the vocabulary tiers and the statistical tells apply to a 250 character note as
much as to an article). Rewrite what it flags, keep every fact and quote exactly as
researched, keep the four beats and the variant's "what we do" line, keep the LinkedIn
note under 300. The checks above are the DM specific subset; the humanizer is the full
audit. Record the result in the batch entry as `Humanizer: pass` or `Humanizer: changed
[what]`, and in the final message per note. A note that cannot pass without losing its
fact is a HOLD, not a send.

**Two notes that ship, from the 2026-09-09 batch:**

> Hi John, Clay's review this summer says he called after hours and Charles came out
> after 10pm. Someone at AAction is picking up at 10pm. I trained a demo AI setter on
> your website that takes those calls 24/7 and books the job. Want to try and break it?

> Hi Albert and Janet, saw AJ's is hiring an HVAC Office Manager, and Google lists the
> office at 8 to 4 weekdays, closed weekends. Every call after 4 lands somewhere.
>
> I trained a demo AI setter on your website: it answers calls and texts in about five
> seconds, 24/7, and books the job straight into your calendar. Want to try and break
> it? Call it, text it, throw it your weirdest customer.

The first is the LinkedIn shape (252 characters). The second is the Facebook shape: the
specific and the bridge as the first paragraph, a blank line, then the full P1 or P2.

**After the connection is accepted with no reply** (Step 2b of the daily loop), the
follow up is fixed copy, no per prospect drafting, and it counts as the message one send
for the scoreboard and the bump clock:

> Thanks for connecting, [First]. The demo on [Company]'s site is ready when you are.
> Want to try and break it?

**Accepted with a reply**, of any kind, is REPLIED: Astra stops and hands the thread to
Zalo. **Not accepted after 14 days** is `NO_CHANNEL` unless another channel is open.

## Test arm J, the trade joke opener (Facebook only, tier D only, added 2026-09-12)

The only cold DM tactic in the researched material with a measured LOCAL SERVICE BUSINESS
result behind it. Dylan Gigliotti's client Jacob Michaels runs an agency selling "your
roofers, your deck builders" (`lfKrZFodLx4` [00:37]). His previous opener was the market
standard greeting plus a light personalization, and it burned out. Replacing it with a joke
is the change he credits: "We're opening with dad jokes. And it's working selling service
based businesses and it's crazy" ([23:09]), CLAIM on the result at [04:58], "response rates
up from ... like 5% up to like 10% or 15% ... we pretty much tripled it". He is explicit
that it transfers: "if you are somebody that's even possibly a local service-based
business, I've proven this works great with that" ([68:00]). Every number in that paragraph
is his unverified claim and none of it goes in a message.

**Three messages, in three separate sends. Never one block.** The joke is the two part
opener, typed as two deliberate sends per the Messenger Enter rule. The ask is the third.

1. The setup line alone, from the approved list in `templates/gold-notes.md`:

   > Why don't ducts keep secrets?

2. The punchline, its own send:

   > Everything leaks eventually.

3. The ask, only if nothing came back:

   > **J1:** Alright [First], real question and then I'll leave the jokes alone. Would you
   > be open to talking about the calls that come in after you close?

   > **J2:** Okay [First], that's my one joke of the day. Mind if I ask you something about
   > the calls that come in after you close?

**The split is the ask, not the joke.** `D-fb-J1` and `D-fb-J2` differ only in that third
message; the joke varies per row by the diversity rule and is never the axis being
measured. Alternate J1 and J2 so the two stay within a few sends of each other, exactly as
P1 and P2 alternate.

**A reply ends the sequence.** If the owner answers anything at all after the setup or
after the punchline, including one word or one emoji, the row is REPLIED, the remaining
parts are NEVER sent, and the thread is Zalo's. On this arm a laugh is a reply, so he is
usually the one who asks the question. That is our rule, not Dylan's, and it wins.

**Building the jokes.** Six are approved in `templates/gold-notes.md`, three for HVAC and
three for plumbing. To write more, prompt the model for "10 witty jokes for HVAC
technicians" or "10 witty jokes for plumbers", and do NOT tell it the jokes are for a sales
message or a DM script. Dylan's reason, `1Q-8UzDvHM4` [00:17]: "it's going to start adding
in all of the noise and the crap from the sales market and it's going to stop working
because it's not social." A new joke is approved by Zalo before it ships, like any other
copy.

**Vary the joke across the batch, inside what six approved jokes allow.** Three per trade
against a Facebook ceiling of 10 means a single trade day cannot give every row a different
joke, so the rule is a cap, not a ban: **no joke goes to more than 4 rows in one day**,
enforced in `scripts/note-lint.py` since 2026-09-12 because as prose it was not enforced at
all (the generic opener cap permits 5 of 10 identical, so 10 rows running two jokes five
times each linted clean). **A row is a row whether it is fresh or a continuation**: a
continuation types that joke's punchline at a stranger today exactly like a fresh row does,
so it counts. Counting only today's setups left the whole continuation path uncapped, and 10
continuation rows carrying one identical punchline and ask passed clean (found in the re
audit of this fix). Mix the two trades wherever the batch allows it, and rotate which joke
leads. Zalo approving more jokes is what raises the variety; until then, state the repeat
count in the batch header rather than pretending it is zero.

**The setup carries no greeting and no name.** Not "Hey Mike, why don't ducts keep
secrets?" The name arrives in the ask. A name in front of a joke makes it read as a sales
line, and it also makes the batch diversity check in `scripts/note-lint.py` unreadable,
because every note would then open with a different first name.

**Rules that still bind.** Messenger sends on Enter, so these are separate deliberate
sends, never a string with newlines in it (our own 2026-09-09 learning). The personal
profile only, never the business page. The 2 to 5 minute pacing gap applies between every
one of the three sends as it does to every message typed in these apps, so the batch runs
in passes: every setup, then every punchline, then every ask, which is also how Dylan runs
it ("This will be the first line you'd send like 100 of those to roofers. And then you send
the punchline", `1Q-8UzDvHM4` [00:53]). No dashes, no banned phrases, no digits anywhere in
the three messages, no link, no demo claim, no dare.

**The one sanctioned exception to the specificity law, and its scope.** These three
messages carry no fact about his business at all, so they fail the paste test by design.
That exemption is this arm only: Facebook, tier D, 20 sends. It exists because the arm
tests a pattern interrupt AGAINST our specificity bet, and an opener that carried a
specific would not be the thing Dylan measured. The row still gets whatever true detail the
homepage gives for free, recorded as `side_note` in the batch entry, so Zalo has something
to work with the moment the thread opens. The load that would have gone to the opener's
specific goes to resolving the owner's personal profile instead.

**What it is testing, stated honestly.** Three variables at once: the channel, the opener
shape and the absence of any offer. That is bad experimental hygiene and it is acceptable
here only because all three are unmeasured on Facebook today and the arm spends 20 rows of
the tier with 2,102 of them. It cannot tell us WHICH of the three moved a reply rate, only
whether this shape produces replies at all.

**Scope and judgment.** Tier D only, 20 sends per phrasing, judged on replies at day 7, and
under 20 sends it has a count and not a rate. One prospect is ONE cold first touch against
the Facebook cap of 10 and three typed messages against the pacing gap.

**The constraint to state out loud in the batch header.** `prospects.csv` carries 1,481
business Facebook URLs and ZERO owner personal Facebook URLs across 2,264 rows, so every J
row costs an owner resolution in the browser before it can be sent at all. Budget for it
per Step 2F of `hunting-playbook.md` or the arm will quietly become a business page arm,
which the rules forbid.

## The Facebook group post, G1 (channel NOT STARTED, added 2026-09-14)

**Nothing on this channel ships until Zalo opens it in `config.md` and says go. It has no
start date on purpose.** The copy contract is written now so the channel is ready, not
because it is running. See the Facebook groups section of `config.md` for the cap, the ramp
and the two gates, and the Facebook groups section of `SKILL.md` for the motion.

This is a different motion from everything else in this file. It is a POST in a local
business, contractor or trade Facebook group, not a message to one person. Nobody is
addressed by name. There is no "your website" to have trained a demo on, because a room of
strangers has no website, and claiming one would be the one lie this rail cannot afford.
What carries it is the outcome opener, the dare, and a number he can call right now.

**The four parts of a group post.**

1. **The outcome opener, in his metro.** "Be the only HVAC company in Miami whose phone
   gets answered after 5 pm." Not "I built an AI receptionist", per the offer law above.
2. **One line on what it does.** Answers in about five seconds, day or night, books the job
   into the calendar. One line, not a feature list.
3. **The dare, the same one the DMs use.** "Want to try and break it?"
4. **The demo number.** The actual phone number, in the post. **No link on the first post**
   (per the sweep: the link is what the group admins remove and what the owner does not
   click). The agent on the other end is the pitch.

**Two approved posts, in the register of everything else in this file:**

> Be the only HVAC company in Miami whose phone gets answered after 5 pm. Mine picks up in
> about five seconds, day or night, and books the job into the calendar. It's sitting there
> right now: [demo number]. Want to try and break it?

> Plumbers in Tampa, your phone rings at 9 on a Friday night and it's going to voicemail.
> Mine answers in five seconds and books the job into the calendar. Want to try and break
> it? Call it or text it: [demo number].

**Vary the copy across groups.** Identical copy in five groups reads as spam to admins and
to the same owners who are in three of those groups. The lint's opener diversity cap applies
to G1 posts exactly as it does to notes: more than half the posts in a batch opening the
same way fails the batch. The sweep's own warning is sharper than ours: the copy four
creators teach is already being repeated word for word between them, which is the
saturation signal.

**What the lint holds a G1 post to** (`scripts/note-lint.py`, family `group`, channel
`facebook_groups` or its short code `fbg`, variant id `<metro>-fg-G1`): 600 characters, a
contraction, the dare, a demo number that parses as a phone number, both halves of the
outcome, no link, no P1 or P2 line, no tech as a product category, 2 to 6 sentences, and no
opener that addresses a PERSON. Addressing the room is fine and is the normal shape:
"Hey everyone,", "Hey HVAC owners,", "Contractors," and "Plumbers in Tampa," all pass;
"Hi Mike,", "Hi Mike.", "Hey Mike and Dana," and a bare "Mike," fail. A G1 post on any other
channel fails, and any other family on `facebook_groups` fails.

**The first post is not a pitch and the second touch is a DM, not a comment.** A person who
calls the demo number is the agent's job to book. A person who comments goes to Zalo, in
DM, like every other reply: Astra records it and stops.

## Tier A, the job post (strongest willingness signal that exists)

He is hiring a CSR, dispatcher or front desk person right now. He is in buying mode today
and shopping for this product in a different aisle. Open with his own job post.

**LinkedIn**

> Hey [Mr./Ms. LastName], saw the [role] role [Company] posted on Indeed [timeframe].
>
> Guessing the phones are the reason. [P1 or P2]
>
> Quick one while you are hiring: when someone calls after hours right now, where does it
> go?

**Facebook or Instagram**

> Hey [Name], saw you are hiring a [role] at [Company].
>
> [P1 or P2, casual trim]
>
> Where do the after hours calls go right now?

## Tier B, the answering service (replacement sale, highest willingness inside the ICP)

Zalo assigns this tier himself after his after hours mystery call, and the fact comes from
that call. Astra never invents it and never guesses it from a website. If the pipeline row
does not carry the answering service fact in `side_note`, the prospect is not tier B.

**LinkedIn**

> Hey [Mr./Ms. LastName], I called [Company]'s line at [time] the other night and got
> [what actually happened, in Zalo's own words from the mystery call].
>
> [P1 or P2]
>
> Honest question: how much of that service is actually getting you booked jobs?

**Facebook or Instagram**

> Hey [Name], called [Company] at [time] one night and got [the fact].
>
> [P1 or P2, casual trim]
>
> Is that service actually booking jobs for you, or just taking messages?

## Tier C, the ad plus the after hours fact

He is running Meta ads right now and paying for every one of those clicks. Open with the
ad, then the gap the ad money falls into. The after hours fact has to be something Astra
can see (posted hours that close at 5, a review saying nobody picked up), not something
assumed.

**LinkedIn**

> Hey [Mr./Ms. LastName], [Company]'s [offer] ad has been running on Facebook since
> [date]. [Your Google hours close at 5 on weekdays / a review from [month] says
> "[quote]"].
>
> [P1 or P2]
>
> What happens to the calls that come in after you close?

**Facebook or Instagram**

> Hey [Name], your [offer] ad is running right now, and [Company] closes at [time].
>
> [P1 or P2, casual trim]
>
> Where do the evening calls land?

## Tier D, the strongest side note available

Passed the filters, no sniper signal. The opener is whichever true detail is sharpest,
in this order of preference: a review quote about the phone, an hours gap, multiple
locations, an active content channel he clearly runs himself.

**LinkedIn, review quote version**

> Hey [Mr./Ms. LastName], one of [Company]'s Google reviews from [month] says "[quote]".
> That is not a staffing problem, no human answers two lines at once.
>
> [P1 or P2]
>
> How many calls do you reckon you miss in a normal week?

**LinkedIn, multi location version**

> Hey [Mr./Ms. LastName], noticed [Company] covers [City A], [City B] and [City C] out of
> the one number.
>
> [P1 or P2]
>
> Who picks up when all three areas call at once?

**Facebook or Instagram, content version**

> Hey [Name], watched the [thing he posted] on [Company]'s page. [One specific, true
> sentence about it.]
>
> [P1 or P2, casual trim]
>
> Out of curiosity, where do the after hours calls go?

## The two bumps (Astra sends these, then stops)

A first touch gets at most two bumps and then the row goes COLD. Every bump adds
something new: a second true fact, a different angle on the same fact, or the takeaway.
Never "just checking in", never "bumping this up", never a bare re-send.

**Bump 1, day 3 after the first touch.** New fact, same soft question.

> [The new true fact, one line, for example: "Saw the [role] post is still up." or "The
> [offer] ad is still running."] The demo is still sitting here if you want a look.

**Bump 2, day 7, the takeaway. This is always the last thing Astra sends.**

> Last one from me, [Name]. If the after hours calls are already handled, ignore me and
> good luck with [the true thing, softened]. If they are not, you know where I am.

After bump 2 the row is COLD. No third touch, ever, on any channel. A prospect who went
COLD is not re-approached with a different angle later.

## Stop means stop

Any form of "not interested", "stop", "remove me", "do not contact me", or a block: mark
the row DEAD immediately, in that session, and never contact that person or that business
again on any channel. There is no clever re-approach and no cooling off period. If the
message is hostile, Astra records it and does not reply at all.

A plain "no thanks" is a reply, so it also goes in the report for Zalo, marked DEAD in the
same breath, so he sees it and does not chase it.

---

# Zalo's rail (reference, Astra never sends these)

Everything below is what happens after a reply. It lives here so the whole sequence is in
one file and so Astra can tell Zalo what stage a thread is at. Astra does not send any of
it, does not build the demo, and does not judge the demo.

## The moment he replies

Any reply at all, including "it goes to voicemail", is the trigger. The demo gets built on
his information and delivered in the same thread. The line the strategy locks:

> Built one on your info so you can see what I mean. No strings.

The demo is built AFTER the reply, never before. That is what keeps message one honest.

## Demo delivery notes

- Operator Base, Toolkit, 1-Click Demo Generator. Email field BLANK so nothing auto sends
  from `demo@aidemo.app` and the link arrives from Zalo in the existing thread.
- Website is mandatory in practice even though the form does not require it. No site, no
  standard demo: use Free Form mode built from real details instead.
- Copy the link from the Copy button on the Demo Ready screen, never the hub level Share
  button, which copies the public generator page instead of this prospect's demo.
- Test it before it goes anywhere, with one question only that business could answer. A
  generic answer means regenerate once, then Free Form. A generic demo never gets sent.

## The front desk wall, the objection that ends the pitch (added 2026-09-14)

**"I already have someone at the front desk."** Per
`research/ai-agents-sales-2026-09-12.md` this is the single most reported objection in the
sweep, and it is the one that ends the replacement pitch every time it is tried: one seller
spent two years on local outreach that died on this sentence. It is not a price objection
and it is not skepticism about the tech. He has heard "replace your receptionist" and he is
telling you no.

**The shape is agree first, then narrow.** Every trades facing creator in the sweep
converges on it independently, which is why it is corroborated rather than one person's
claim. Do not argue with the premise, do not explain that the bot is cheaper than her, and
do not mention her cost at all.

> I'd still have your person on the phone during the day. This only catches the calls that
> fall through: after hours, lunch, and when both lines are going at once.

Three things that turn make it work, all of them from the buyer notes:

1. **Agree.** His receptionist stays. Say it in the first clause, before anything else.
2. **Narrow to the gap he already knows about.** After hours, lunch, both lines busy. Never
   a new problem he has to be convinced of.
3. **Leave the human path in.** It transfers to a person, it says it is automated in its
   first breath. "No instant path to a person" and "a human name that hides that it is a
   bot" are the top two refusal reasons in the buyer notes; a turn that does not mention the
   human path wins the objection and loses the sale later.

Variants of the same wall, same shape:

- **"We pride ourselves on a personal touch."** Same turn, the version two creators use
  verbatim: "I'd still have your person on the phone during the day, this only catches the
  calls that fall through."
- **"My wife answers the phone."** Same turn. Then the only question worth asking: "What
  happens to the ones that come in while she's at the school run?"
- **"I answer it myself."** Same turn, aimed at him: "You'd still get the ones you want.
  This is for the ones that come in when you're under a house."

## Objections, short forms

- "I do not trust AI." Try the demo and try to break it. If you hate it, no hard feelings.
- "I already have an agency." Most clients did. This is the lead response layer, not the
  marketing.
- "We already have a receptionist." The front desk wall, above. Agree first, then narrow:
  she stays on the phone during the day, this only catches the calls that fall through.
- "We use an answering service." That is the replacement sale. Ask what it costs a month
  and how many of those messages became booked jobs.
- "Is this a bot messaging me?" No, this is me typing. I do use AI to do the research so
  the message is actually about you.
- "How much is it?" Setup varies by build. Fifteen minutes to find the right tier.
- "Not interested." Thanks for the straight answer. Mark DEAD.

## After the demo

Demo, then the VSL, then the call. The demo shows what it is, the VSL shows how it makes
money, the call closes. Prices and the call structure are in `call-one-pager.md`.
