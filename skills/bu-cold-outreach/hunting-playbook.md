# Hunting Playbook, Black Umbrella Cold DM

The browser procedure Astra runs per prospect in the codex-bare Chrome session. The raw
list already exists in `prospects.csv`, so this playbook is not about finding businesses.
It is about three things the seed file cannot do: confirming the evidence is still live,
resolving the owner and the DM handle, and grabbing one extra true detail.

## Speed defaults, measured, not optional

These are the defaults from the two sessions on 2026-09-08. Session 1 ran the long
procedure: 46 minutes for 4 drafts, native screenshots failing and shell captures
replacing them, ten searches for one owner name. Session 2 ran the rules below: 6 drafts
from 12 prospects in 10.95 minutes of research (15.89 with the artifact QA), 28 page
loads, 0 screenshots, every prospect under 4 minutes. Run session 2's way unless the
session instruction says otherwise.

1. **Hard budget per prospect: 4 page loads and 5 minutes.** A Google search is a load.
   The loads are assigned: the homepage, the evidence load for the opener (default 5),
   the owner search, and one reserve for opening the reviews. The fifth load or the sixth
   minute means the row is held with the reason written down and the next row starts. No
   exception for a row that "almost" resolved. (Was 3 loads and 4 minutes on 09-08; Zalo
   returned that batch for generic openers, so one load moved to the specific.)
2. **Hard budget per session: stop at the ceiling or at 45 minutes of research, whichever
   comes first.** Report the real number. Ten researched rows in 30 minutes beats fifteen
   in 70. Since 2026-09-12 the ceiling is PER CHANNEL, so the 45 minutes is split across
   the channels that are open rather than spent on whichever one is opened first. A
   research session with LinkedIn at 10 and Facebook at 10 does not get 90 minutes; it
   gets 45 and delivers fewer rows on both, which is the honest outcome and goes in the
   report as a number.
   **Two sessions a day, each with its own 45 (added 2026-09-12 evening).** A day may run
   a research and resolution session (owner names, Step 2F, the open profile check on
   every LinkedIn row, the drafts, the lint) and then a send session, and each session
   has its own 45 minute research budget; the send session types and paces only, and
   every row it sends was drafted, linted and, where relevant, checked for an open profile
   in the research session. The measured reason: at 20 sends a day the throughput on the
   09-10 to 09-12 ledgers (95 rows touched, 29 drafts, 5,013 seconds) needs 58 minutes of
   research plus 83 minutes of paced sending at the measured mean gap of 218 seconds, 2.3
   browser hours, and one session has stalled at entry 6 before (learnings, 2026-09-11).
   One session still never exceeds its own 45; a third session does not exist.
   **A Facebook J row gets 5 loads and 6 minutes**, not 4 and 5, because the owner's
   personal profile has to be resolved from nothing (Step 2F) and the opener needs no
   evidence load at all. Expect 6 to 8 resolved owners inside a 45 minute session, not 10.
   The Facebook ceiling of 10 will usually not be filled by research, and that is fine:
   send fewer, never pad, never fall back to the business page.
3. **Trust the seed evidence.** `prospects.csv` carries the hiring post (role and posted
   date) and the ad (offer, active count, start date), pulled the day the tranche was
   built. Use it verbatim in the message and do not reopen the source while the tranche
   is under 7 days old (the date is in `SEED-REPORT.md`). Re confirmation is for older
   tranches, FOUND redrafts and bumps, per Step 1.
4. **Never open Indeed.** It shows the bot a verification wall and burns minutes. Employer
   careers portals (prevueaps and the like) are fine when a re confirmation is actually
   due.
5. **Two loads carry the research, both read through the accessibility tree.** The
   homepage answers Step 0 (size, franchise, AI chat, commercial only, residential, owner
   if named). The evidence load finds the specific the opener needs, per the specificity
   law in `templates/messages.md`: tier A, the employer's own job posting for the duties
   line and the shift; tier C, the Google Business Profile panel (search "[Company]
   [metro]") for the hours and a review snippet, with the ad's own words from the seed's
   `meta_ads_offer` or one Ad Library load when that is thin; tier D, the same Google
   panel for a review quote about the phone or the hours gap. A services list from the
   homepage is bump material, never the opener. In the reviews, look for the words that
   mark the right review (after hours, Saturday, Sunday, pm, called back, voicemail, no
   answer, never heard back, same day): a person handling a call outside office hours,
   or a reachability complaint. A speed compliment with no day or time in it is not the
   opener; keep looking within the budget, then hold.
6. **One owner search, quoted.** `"Exact Company Name" owner linkedin`, plus the metro when
   the name is generic. Session 2's biggest time sink was owner ambiguity: unquoted names
   matched same name companies in other states. If the first search does not resolve to
   a profile whose headline names the company, hold the row. Never a second or third
   search.
7. **Read pages as text, not pixels.** `get_app_state` (the accessibility tree) is the
   default read for every page. Screenshots are for two moments only: the filled
   invitation or message field right before Send, and the sent confirmation. Both are
   saved under `evidence/YYYY-MM-DD/`. Never retry a failed screenshot during research.
8. **Disqualify before you resolve.** Size, franchise and AI chat are visible on the
   homepage in seconds. Owner resolution costs a search. Do the cheap kill first.
9. **Never revisit a held or disqualified row in the same tranche.** They are in
   `pipeline.csv` as DEAD or in the ledger as held. Take the next unseen row.
10. **Write the ledger as you go.** `evidence/YYYY-MM-DD/session-N/research-ledger.json`
    with one entry per prospect touched: id, seconds, page loads, outcome (draft, held
    with reason, dead with reason). The report's efficiency block is computed from it.
11. **The paste test before the note is written.** If the opener clause could go to
    another company with only the name swapped, the row is not ready: spend the reserve
    load on the reviews, or hold it with "no specific found". Never ship generic to save
    a minute.

Everything here is free and public: the company website, Google, LinkedIn, Facebook,
Instagram, and, only when a re confirmation is due, the Meta Ad Library and employer
careers portals. No paid data tools, no scrapers, no email finders.

A row is READY TO WRITE only when all four are true:

1. The sniper evidence is confirmed still live today (tier A and C), or the tier B fact is
   in the row from Zalo's mystery call, or the tier D side note is confirmed on screen.
2. An owner name is known, or the row is honestly workable without one (see Step 2e).
3. A DM channel is open on LinkedIn, Facebook or Instagram, with the exact profile URL
   recorded.
4. The prospect id does not already exist in `pipeline.csv` at a stage other than `FOUND`.
   COLD, DEAD, NO_CHANNEL and everything from SENT onward are all exclusions. A row at
   `FOUND` is one Astra already researched that never went out, and it comes back into a
   batch through Step 2b of the daily loop in `SKILL.md`, not by being found again here.

## Step 0, the homepage load

One load, read through the accessibility tree. From it, in this order:

1. **Kill or keep.** A franchise or brand name, a holding company footer ("An Ace
   Hardware Company"), "10,000+ reviews", a CSR department on a careers link,
   "commercial", "multi-family", "property management", "Request a Bid", new
   construction, or a chat widget labelled AI. Any of these means the row is dead or held
   with the reason written down (Step 5 has the full list) and the next row starts. Cost
   so far: one load, under 30 seconds.
2. **Residential confirmed.** Service call language: repair, emergency, same day,
   residential, home.
3. **Bump material.** Whatever the homepage states that Step 4 would accept: on call
   24/7, one number for three trades, service areas, no chat widget in the tree. Record
   it verbatim, and know that none of it is the opener on its own: the opener comes from
   the evidence load (speed default 5) and has to pass the paste test.
4. **The owner, if named.** "Meet the owner", "family owned by", a founder line. Free.

Session 2 held 6 of 12 rows at this step in 22 to 51 seconds each. That is the step
working, not the step failing.

## Step 1, the evidence

A message that opens with a job post that came down last week reads as a bot, so the
evidence has to be current. Currency comes from the seed first and the browser second.

**When the tranche is under 7 days old, the seed IS the confirmation.** Take the role and
its posted date, or the ad and its start date, straight from the row and write the message
from them. Record "seed, tranche dated YYYY-MM-DD" as the confirmation in the batch entry.
Re confirmation applies to older tranches, to rows at FOUND being redrafted, and to bumps.
The evidence load below happens on every tranche, because the opener needs what the seed
row does not carry.

**Tier A, the hiring signal.** Do not open Indeed (verification wall). Search
`"[business_name]" careers` once and open the employer's own portal if one appears. This
is the tier A evidence load even on a fresh tranche, because the opener needs the duties
line and the shift from the posting ("answer incoming calls, texts and emails", "Monday
to Friday, 9 to 5"), not the role title. On an older tranche the same load also confirms
the post is still up and still the role in `indeed_role`. No portal in one search means
the seed's role title plus the Google hours gap is the opener; a seed post older than
about 30 days with no portal to confirm it demotes the row to tier D.

**Tier C, the ads signal.** Go to `facebook.com/ads/library`, set the country, search the
business name (or the page). The ad in `meta_ads_offer` has to still be ACTIVE. If the
count in `meta_ads_active_count` has dropped to zero, the row is no longer tier C: demote
to tier D. If a DIFFERENT ad is running now, use the one that is actually live and record
the new offer verbatim.

**Tier B.** Nothing to confirm in the browser. The fact came from Zalo's after hours call
and lives in the pipeline `side_note`. If it is not there, the row is not tier B, and
Astra never phones a prospect to create it.

**Tier D.** There is no sniper signal, so the side note IS the evidence and it gets
confirmed the same way: open the thing and read it.

**If the evidence is dead:** do not write the message from it. Either demote the tier and
open with a side note, or set the batch status to `PULLED, evidence stale`, leave the
pipeline row at FOUND, and take the next row. Never write around a fact that is no longer
true.

## Step 2, resolve the owner

`prospects.csv` fills the owner columns for `source_rail = linkedin` rows and leaves them
empty for `source_rail = maps` rows. For maps rows the budget is one search:

`"[business_name]" owner linkedin`, quoted, plus the metro when the name is generic ("All
Airs", "Comfort", "Anytime" all matched other states unquoted in session 2). Accept the
hit only when the profile headline or experience names this company in this metro.
Anything else is a hold: write "owner unresolved in one search" and take the next row.
Never guess a name, never take a name from a review written BY a customer, never use a
first name that appears only in a Google review as if it were the owner's.

The homepage already loaded in Step 0 often names the owner outright ("Meet our
founder"); that costs nothing and beats the search. The ladder below is the full set of
places an owner name can live. It is for a session instruction that lifts the one search
budget, or for a FOUND row being redrafted where the research is already paid for. Record
where the name came from, because a name from a signed review reply is stronger than a
name from a directory.

**2a. The website's About, Team, Our Story or Meet the Owner page.** Fastest and most
reliable. Owners of shops this size put their own face on the About page. Take the name,
the title, and anything usable as a side note while you are there.

**2b. Signed owner replies on Google reviews.** Open the Google Maps listing, read the
owner responses. Owners at this size sign them: "Thanks Karen, we appreciate it. Mike,
owner". This also tells you he personally reads the reviews, which is worth knowing.

**2c. LinkedIn company page, then People.** Search LinkedIn for the business name, open
the company page, click People, and look for Owner, Founder, President, General Manager,
Co-Owner. Cross check the metro: franchisees and same name businesses in other states are
a common trap. If the company page does not exist, search LinkedIn for
`[owner first name] [business name]` once the name is known from 2a or 2b.

**2d. Facebook page, then the owner's personal profile.** Open the business page, check
the About section for a listed owner, and look at who posts and who replies to comments.
Then search Facebook for that person by name plus the metro to find the PERSONAL profile.
The personal profile is the better channel; see Step 3.

**2e. Instagram bio and pinned posts.** Small trades often name the owner in the bio or
run the account personally.

**2f. No name anywhere.** The row is still workable but weaker. Use it only when the batch
is short, and open with the business rather than a person: "Hey, whoever handles the
phones at [Company]". Prefer named rows every time. Never guess a name, never use a name
from a review written BY a customer, and never use a first name that appears only in a
Google review as if it were the owner's.

## Step 2F, resolve the owner's PERSONAL Facebook profile (the Facebook rail, 2026-09-12)

The seed file carries 1,481 business Facebook URLs and ZERO owner personal Facebook URLs
across 2,264 rows. A business page is not a channel (Zalo, 2026-09-09), so every Facebook
row is an owner resolution before it is anything else. This step is the whole cost of the
Facebook rail, and budgeting for it is what stops the rail from quietly becoming a business
page rail.

**Budget: 5 page loads and 6 minutes for the row, of which this step gets 3 loads and about
4 minutes.** A J arm row needs no evidence load, because the joke opener carries no fact
about the business, so the budget that would have bought the specific buys the owner here
instead. Over the budget means hold the row and write the reason; never guess a profile.

The ladder, cheapest first, stopping at the first hit:

**2F.1. The name you already have.** `prospects.csv` fills `owner_name` for many linkedin
rail rows, and Step 0's homepage load often names him outright. A name in hand turns this
step into one search.

**2F.2. The business page, About and the posts.** Open the page once. The About section
sometimes lists the owner. More reliably, read who writes the posts and who answers the
comments in the owner's own voice, signed with a first name. Take the name, not the page.

**2F.3. Facebook people search, name plus metro.** Search the person by name and city. The
photo, the work field and the friends of the business are what disambiguate a common name.
A profile with no connection to the trade or the metro is not him.

**2F.4. Verify the personal profile before it is a channel.** The intro, the work field,
the cover photo or a recent post has to name THIS business in THIS metro. That check is
from Step 3.2 and it does not get relaxed for a test arm. Record the exact profile URL in
the batch entry.

**2F.5. No verified personal profile.** The Facebook channel for that row is closed. Try
LinkedIn, then Instagram if `config.md` has it active (it is inactive as of 2026-09-12, so
today the ladder is LinkedIn then nothing), then `NO_CHANNEL`. Never message the business page as a
substitute, never send to a shared inbox, and never put a page URL in a batch entry: that
is a bug, not a fallback, and the 2026-09-09 AJ's Air page message is the reason the rule
exists (an auto responder answered, the owners never saw it).

While the personal profile is open, take whatever true detail is free for the `side_note`
field. The J arm's messages do not use it, but the moment he replies, Zalo does.

## Step 3, pick the channel

Only channels marked active in `config.md` count, and only accounts Zalo is actually
logged into in this Chrome profile. Record the exact profile URL so the right thread opens
without searching.

**Priority order:**

1. **LinkedIn, the owner's own profile.** Best channel for owner operators at this size.
   Three lanes inside the one daily cap of 15, checked in this order (lanes added
   2026-09-12 evening; the counting rules are in the sent-log section of `SKILL.md`):
   **First, the open profile check, one click.** Open the profile while not connected and
   click Message. A free composer means the owner is an Open Profile Premium member: the
   row is an open profile send, variant `<tier>-li-O1`, the control four part message one
   inside 300 characters, delivered on send with no accept gate. An InMail credit prompt
   or a Sales Navigator upsell means the profile is closed: close it and move on. Either
   way record `open_profile: yes|no` in the pipeline notes; measured 2026-09-08, every
   owner profile opened was closed, and the share in this ICP is being measured on every
   row from now on.
   **Second, InMail for a closed tier A profile, then tier C, A first** (`<tier>-li-I1`),
   inside `inmail_credits_per_month` in `config.md`, delivered on send.
   **Third, the connection request carrying the message as its note** (300 character
   limit), the default for every other closed profile, and tier D only while the ramp hold
   in `config.md` is on: draft the invitation note per `templates/messages.md`, and the
   full message one goes out only after the connection is accepted (Step 2b of the daily
   loop picks that up). Open More, then Connect, then Add a note. A connection request
   counts against BOTH budgets, the 80 per week limit AND that day's LinkedIn cold first
   touch number (corrected 2026-09-12; this line used to say "not the 15 DMs per day",
   which left invitations with no daily brake at all). **Log it as a row in
   `sent-log.csv` with `stage` set to `CONNECT`**, because those rows are the only
   denominator the 80 per week cap has: count the last 7 days of them before sending
   another. Leave the pipeline row at `FOUND` with the pending request in the notes, so
   Step 2b of the daily loop picks it up and checks for an acceptance. The pipeline row
   becomes `SENT` only when a MESSAGE goes out.
2. **The owner's personal Facebook profile, and ONLY that (Zalo, 2026-09-09).** A business
   page is not a channel: its inbox goes to whoever manages the page, lands in a filtered
   folder, and answers with an auto-responder (AJ's Air, 2026-09-09: "Thanks for messaging
   us, we'll get back to you soon", the owners never saw it). If the personal profile
   cannot be verified (the intro, work field, cover or posts name the business), the
   Facebook channel for that row is closed: try LinkedIn or Instagram, else `NO_CHANNEL`.
   Never message the page as a fallback. A verified personal profile takes ONE of two
   Facebook lanes on a given day, and the batch entry says which: the cold DM now, or the
   friend request first (`FRIEND` row, its own daily number in `config.md`, the message
   into the accepted thread later; Zalo's written yes, 2026-09-12). Miami rows go first
   on Facebook, for the delivery reason in `config.md`.
3. **Instagram DM.** Use when the account is active, meaning it posted within the last
   month or so. DMs from non followers land in Requests, which many owners rarely check,
   so this is a real channel and a slow one.

**No open path on any of the three:** set the pipeline stage to `NO_CHANNEL`, write the
reason in notes, and move to the next row. Do not chase an email address, do not use a
website contact form, do not message a shared info@ inbox, and do not send to a general
company page as a substitute for the owner.

## Step 4, grab one extra side note

Every message carries one true specific. The tier evidence is one; this is the second, and
it is what makes a bump possible later without repeating yourself. Under the speed
defaults it is captured from the homepage load in Step 0; the list below is what to look
for there. Reviews and hours cost extra loads and are only for a row with a load to
spare. Take whichever is available and record it verbatim:

- **A review quote about the phone.** Search the Google reviews for "call", "phone",
  "answer", "voicemail", "never got back", "no one picked up". A quote like "great work
  but impossible to reach" is the strongest side note in this whole list, because it is the
  problem in the customer's own words.
- **The hours gap.** The Google Business Profile says closes at 5pm weekdays, closed
  weekends. Every evening call goes somewhere.
- **No chat widget on the site.** The `chat_widget` column already says so; confirm it by
  looking at the bottom right corner of the homepage.
- **Multiple service areas on one number.** The footer lists three cities.
- **Something he clearly made himself.** A YouTube channel, a podcast appearance, a truck
  wrap he posted about, a build he is proud of. Use it only if you actually read or
  watched enough of it to say one specific true sentence about it.

Never invent one and never stretch one. "I saw you have great reviews" is not a side note,
it is filler, and it reads as filler.

## Step 5, disqualify late

Some things only become visible in the browser. Most of them show on the homepage and are
caught in Step 0; the rest surface on the owner's profile. Kill the row rather than
writing around them, and record the reason in `drop_reason` style wording in the pipeline
notes:

- A franchise or brand that the seed file's `franchise_flag` missed (One Hour, Mr. Rooter,
  ARS, Service Experts, and their local trading names).
- An AI chat widget already on the site.
- New construction or commercial mechanical only. The offer is residential service call
  economics.
- The business is clearly bigger than the band: a careers page with a CSR department, a
  published 24/7 answering guarantee with named staff, a private equity or holding company
  footer.
- The listing resolves to an aggregator (Angi, Thumbtack, Yelp profile) rather than the
  business.
- The owner's public profile shows he is well past the copy avatar and the account is
  clearly dormant. This is a soft signal, not a hard rule; it only matters alongside a
  thin listing and no tech signals.

## Step 6, write the row

Add or update the row in `pipeline.csv` with the channel, the profile URL, the owner name,
the tier, the variant, the side note, stage `FOUND`, and today's date in `last_touch` only
once the message has actually gone out. Then write the batch entry per
`templates/batch.md`.

## When the well runs dry

If today's tier cannot fill the quota from `prospects.csv`, do not pad the batch. Work
down in this order and say in the report which step was reached:

1. Next tier down in the same metro (A, then B, then C, then D).
2. Next metro in `config.md`.
3. Stop short and report the real number. A smaller batch of researched prospects beats a
   full batch of unresearched ones, and the strategy's whole edge is that the message
   cannot be pasted into another company's DM.

Never generate prospects. `prospects.csv` is produced elsewhere and this skill never
modifies it. If it is exhausted, that is a finding for the report, not a problem for Astra
to solve by widening the filters.
