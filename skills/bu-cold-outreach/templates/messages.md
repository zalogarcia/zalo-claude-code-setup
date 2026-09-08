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
   industry. This is the part that cannot be pasted into another company's DM.
3. **What we do, in his language, and that his demo exists.** The outcome, in the words he
   uses, plus the fact that a demo has been trained on his own website. "I went ahead and
   trained a demo AI setter on your website. It answers your calls and texts in about five
   seconds, 24/7, and books the job into your calendar." Never "omni-channel
   conversational agent", never "AI-powered solution". Zalo's decision, 2026-09-08: the
   demo claim goes in message one because he generates the demo in seconds the moment a
   reply lands, so the prospect never finds it missing.
4. **The offer, as a question he can answer in one word.** "Want me to send it over?" or
   "Want the link?" Not a meeting ask, and still no link in message one: the link is
   message two, in the same thread, from Zalo.

Length: LinkedIn up to about 90 words, Facebook and Instagram up to about 60. If it needs
scrolling on a phone it does not get read.

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

> I went ahead and trained a demo AI setter on your website. It answers your calls and
> texts in about five seconds, 24/7, and books the job straight into your calendar. Want
> me to send it over?

**P2, the replacement:**

> I built a quick demo off your website: the thing that picks up when nobody can, calls
> and texts, day or night, and books the job into your calendar instead of taking a
> message. Want the link?

Both are literal descriptions of what the system does. Neither carries a number about a
result. Do not write a P3 by hand; the weekly review writes it, in the working copy of
this file, changing one element only.

**Since 2026-09-08 P1 and P2 end with the demo offer, so in every template below the
closing diagnostic question is DROPPED: opener line(s), then [P1 or P2], then nothing.**
The openers stay exactly as written. On LinkedIn the whole thing also has to fit a 300
character invitation note when the message travels inside the connection request.

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

## Objections, short forms

- "I do not trust AI." Try the demo and try to break it. If you hate it, no hard feelings.
- "I already have an agency." Most clients did. This is the lead response layer, not the
  marketing.
- "We already have a receptionist." This catches what she cannot: after hours, lunch, both
  lines busy. She gets booked jobs instead of voicemails.
- "We use an answering service." That is the replacement sale. Ask what it costs a month
  and how many of those messages became booked jobs.
- "Is this a bot messaging me?" No, this is me typing. I do use AI to do the research so
  the message is actually about you.
- "How much is it?" Setup varies by build. Fifteen minutes to find the right tier.
- "Not interested." Thanks for the straight answer. Mark DEAD.

## After the demo

Demo, then the VSL, then the call. The demo shows what it is, the VSL shows how it makes
money, the call closes. Prices and the call structure are in `call-one-pager.md`.
