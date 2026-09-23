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
   the owner search, and one reserve for opening the reviews (on a tier C row the reserve
   is the Ad Library load that re confirms the ad, Step 1). The fifth load or the sixth
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
3. **Re confirm the seed evidence live, every row, every time.** `prospects.csv` carries
   the hiring post (role and posted date) and the ad (offer, active count, start date),
   pulled the day the tranche was built. It tells you what to look for; it is not the
   confirmation, however young the tranche is (Zalo, 2026-09-23: each prospect gets one
   message, so a stale fact wastes it). Quote it verbatim only after Step 1 has seen it
   live today. FOUND redrafts, an accepted connection's one message included, are re
   confirmed the same way.
4. **Never open Indeed.** It shows the bot a verification wall and burns minutes. Employer
   careers portals (prevueaps and the like) are fine, and they are where a tier A re
   confirmation happens.
5. **Two loads carry the research (three on tier C, where the Ad Library load is the re
   confirmation), all read through the accessibility tree.** The
   homepage answers Step 0 (size, franchise, AI chat, commercial only, residential, owner
   if named). The evidence load finds the specific the opener needs, per the specificity
   law in `templates/messages.md`: tier A, the employer's own job posting for the duties
   line and the shift; tier C, the Google Business Profile panel (search "[Company]
   [metro]") for the hours and a review snippet, plus one Ad Library load that confirms
   the ad in the seed's `meta_ads_offer` is still active (Step 1); tier D, the same Google
   panel for a review quote about the phone or the hours gap. A services list from the
   homepage is side note material for Zalo, never the opener. In the reviews, look for the words that
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
Instagram, the Meta Ad Library and employer careers portals (the live re confirmation).
No paid data tools, no scrapers, no email finders.

A row is READY TO WRITE only when all four are true:

1. The sniper evidence is confirmed still live today (tier A and C), or the tier B fact is
   in the row from Zalo's mystery call, or the tier D side note is confirmed on screen.
2. An owner name is known. A row with no name anywhere is a HOLD (Step 2f and Step 2E,
   2026-09-13); it has no door on either live channel.
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
3. **Side note material.** Whatever the homepage states that Step 4 would accept: on call
   24/7, one number for three trades, service areas, no chat widget in the tree. Record
   it verbatim, and know that none of it is the opener on its own: the opener comes from
   the evidence load (speed default 5) and has to pass the paste test.
4. **The owner, if named.** "Meet the owner", "family owned by", a founder line. Free.

Session 2 held 6 of 12 rows at this step in 22 to 51 seconds each. That is the step
working, not the step failing.

## Step 1, the evidence

A message that opens with a job post that came down last week reads as a bot, so the
evidence has to be current. The seed says what to look for; the browser, today, says it is
still true.

**Re confirm live on every row, whatever the tranche's age.** Zalo decided this on
2026-09-23: each prospect gets one message, so a stale fact wastes it. There is no age
below which the seed counts as the confirmation. Record "re confirmed live YYYY-MM-DD" and
what was seen in the batch entry. Rows at FOUND being redrafted, including the one message
owed to an accepted connection or friend request, are re confirmed the same way. There are
no bumps to re confirm for (retired 2026-09-22).
The evidence load below happens on every row, because the opener needs what the seed row
does not carry, and for tier A it is also the re confirmation.

**Tier A, the hiring signal.** Do not open Indeed (verification wall). Search
`"[business_name]" careers` once and open the employer's own portal if one appears. This
is the tier A evidence load even on a fresh tranche, because the opener needs the duties
line and the shift from the posting ("answer incoming calls, texts and emails", "Monday
to Friday, 9 to 5"), not the role title. The same load confirms the post is still up and
still the role in `indeed_role`. No portal in one search means the post cannot be
confirmed live, so it is not quoted: demote the row to tier D and open on a side note.

**Tier C, the ads signal.** One Ad Library load on every tier C row: go to
`facebook.com/ads/library`, set the country, search the business name (or the page). The
ad in `meta_ads_offer` has to still be ACTIVE. If the
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

**2f. No name anywhere: HOLD (2026-09-13).** This used to say the row was workable but
weaker, opening with "whoever handles the phones at [Company]". It is not workable on
either live channel: Facebook needs a verified personal profile (2F.5) and LinkedIn needs
the owner's own profile (Step 3.1), so a nameless row has no door. Hold it and write the
reason, per Step 2E. Never guess a name, never use a name from a review written BY a
customer, and never use a first name that appears only in a Google review as if it were the
owner's.

## Step 2E, route a NAMED row by whether it has a fact (2026-09-13)

A name and a timed reachability fact are two different scarcities, and after 2026-09-13
they are stocked very differently. Measured that day: the offline resolver read every row
it could reach and the named pool went 110 to **320**, while the evidence miner covered
186 of 186 named rows and found a qualifying fact on **14, 7.5 percent**. Google's review
surfaces are closed to a logged out client (six endpoints tested and recorded in
`~/dev/bu-cold-outreach/tools/evidence-miner/README.md`), so the miner could only read the
reviews a business republishes on its own site, and conditional on that text existing at
all the yield was 9.0 percent. **More offline pages will not fix it.**

So a named row without a fact is NOT a hold. Route it:

- **Name AND a qualifying fact** goes to a lane whose message carries the specific: the
  control DM (the four beats in one message), an open profile message, an InMail, or a
  note-less connection request whose one message follows the accept (tier D only while the
  invitation hold is on). The `N1` note was retired on 2026-09-22 with every connection
  note.
- **Name, NO fact, TIER D ONLY** goes to the **J arm on Facebook**, and only there. The
  joke opener carries no fact about the business by design, which is exactly why the budget
  line above gives a J arm row no evidence load. It still needs 2F.4, the owner's personal
  profile, which is browser work. **The tier is not optional:** the J arm is Facebook only
  and tier D only, 20 sends (`templates/messages.md` "Test arm J", and `SKILL.md` on the two
  measured arms), and the invitation tier rule reserves A and C for the lanes that deliver
  on send. A tier A or C row must never be drafted as `A-fb-J1` or `C-fb-J1`; the lint does
  not catch it because it checks channel and family, not tier, so this rule is the only
  guard.
- **A tier A or C row is not factless just because the evidence miner found nothing.**
  Their fact is their own seed evidence, which is a different artifact: tier A's hiring post
  for the phones, tier B's mystery call result, tier C's live ad. The miner only looks for a
  timed reachability quote in reviews, which those tiers do not need. Confirm the seed
  evidence is still live per Step 1 and route the row to the control DM, an open profile
  message or an InMail. If the seed evidence is DEAD, Step 1 demotes the row to tier D
  first, and only then does the bullet above apply.
- **No name** is a hold, and after 2026-09-13 it is a hold nothing offline can lift.

The consequence for a session's budget: the loads that used to hunt names are free now, and
the fact is the thing worth spending them on. A Google reviews read in the logged in browser
is the one source that can produce a fact the offline rail cannot, so a row that has a name
and is destined for a LinkedIn lane earns that reserve load. A row destined for the J arm
does not.

## Step 2F, resolve the owner's PERSONAL Facebook profile (the Facebook rail, 2026-09-12)

The seed file carries 1,481 business Facebook URLs and ZERO owner personal Facebook URLs
across 2,264 rows. A business page is not a channel (Zalo, 2026-09-09), so every Facebook
row is an owner resolution before it is anything else. This step is the whole cost of the
Facebook rail, and budgeting for it is what stops the rail from quietly becoming a business
page rail.

**Budget: 5 page loads and 6 minutes for the row, of which this step gets 3 loads and about
4 minutes, or ONE load and about 1 minute when 2F.0 hands you a candidate.** A J arm row needs no evidence load, because the joke opener carries no fact
about the business, so the budget that would have bought the specific buys the owner here
instead. Over the budget means hold the row and write the reason; never guess a profile.

The ladder, cheapest first, stopping at the first hit:

**2F.0. The pre resolved candidate files, read them BEFORE you load anything.** There are
two: `research/owner-candidates-<date>.csv` for the name (below) and
`research/evidence-candidates-<date>.csv` for the fact (14 qualifying quotes as of
2026-09-13, each with `evidence_quote`, `evidence_url`, `evidence_shape` and
`evidence_confidence`). A row appearing in BOTH is draft ready and should be worked first;
Step 2E says where a row with only one of them goes. Two handling rules for the evidence
file: only 4 of the 14 quotes carry a date the page actually shows, so a note built on an
undated one says "a review on your site" and never invents "Jennifer's review from June";
and a quote flagged `dash_in_quote` contains an em dash, so it is rewritten rather than
pasted verbatim or the note lint rejects it.

The owner file in detail: `research/owner-candidates-<date>.csv` (first written 2026-09-13, keyed by `prospect_id`)
holds names mined offline from company websites, each with `owner_evidence_url` and a
verbatim `owner_evidence_quote`, plus `owner_confidence` high or medium. A row with a
candidate costs you a VERIFICATION, not a hunt: open the evidence URL, confirm the sentence
still says it, and go straight to 2F.4 with the name. A row carrying a `no_owner_reason`
instead was already searched and came back empty, so do NOT re spend the budget on it;
skip to the next row and note the reason. Two rules, because a candidate is evidence and
not truth: where a candidate CONTRADICTS the seed `owner_name`, the website wins only if
its quote is about the business itself and dated no older than the seed, otherwise hold
the row and write both names; and a `medium` candidate is a first name only, so it needs
2F.3 to become a person. Measured on the 2026-09-13 seed: rows that already carried a name
drafted at 29.4 percent against 4.3 percent for rows without one, on identical page loads,
which is why this step is first.

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
   row is an open profile send, variant `<tier>-li-O1`, the one message in the control
   shape inside the 420 character limit the lint applies to every LinkedIn text, delivered
   on send with no accept gate. An InMail credit prompt
   or a Sales Navigator upsell means the profile is closed: close it and move on. Either
   way record `open_profile: yes|no` in the pipeline notes; measured 2026-09-08, every
   owner profile opened was closed, and the share in this ICP is being measured on every
   row from now on.

   **Check the flagged rows FIRST (2026-09-13).** The Apify export we already paid for
   carries a top level `openProfile` boolean, and it is the WRONG field: it reads false on
   1,345 of 1,345 profiles, including Joe Borter, whom a live session confirmed the same
   morning as having a free composer. One falsification is enough, so the click stays
   mandatory and `openProfile` is never read as a negative. What the export IS good for is
   ORDER: Open Profile is a Premium feature, so `premium` is a necessary condition, and the
   rows carrying `premium` true AND `composeOptionType` PREMIUM_INMAIL are 18 of our 110
   owner rows. Check those 18 before the other 92: same information, about 9 minutes of
   clicking instead of 55. The flags joined to 110 of 110 owner rows with zero unmatched,
   so this costs nothing to apply. It is a prioritisation hypothesis with one positive
   data point, and checking the 18 first is itself the test: after 18 rows the hit rate
   inside the flagged set is measured. Our owners are 23.6 percent Premium against 52.0
   percent across the whole harvest, which is independent reason to expect the low end of
   the 5 to 40 percent open share.
   **Second, InMail for a closed tier A profile, then tier C, A first** (`<tier>-li-I1`),
   inside `inmail_credits_per_month` in `config.md`, delivered on send.
   **Third, the connection request with NO note** (option A, Zalo 2026-09-22), the default
   for every other closed profile, and tier D only while the ramp hold in `config.md` is
   on. Open More, then Connect, then **Send without a note**; never Add a note. In
   `notes.json` it is an entry with `"kind": "connect"` and an empty text, and the lint
   fails any text. The one message goes out only after the connection is accepted (Step 2b
   of the daily loop picks that up), drafted per `templates/messages.md`. A connection request
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
   friend request first (`FRIEND` row, its own daily number in `config.md`, the one
   message into the accepted thread later; Zalo's written yes, 2026-09-12). Never both on
   one prospect: a prospect who got the DM has had their one message. Miami rows go first
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
it goes in the batch entry as the side note Zalo has in hand the moment a reply lands (it
used to be bump material; there are no bumps since 2026-09-22). Under the speed
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
