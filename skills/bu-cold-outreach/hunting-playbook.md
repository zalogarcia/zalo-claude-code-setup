# Hunting Playbook, Black Umbrella Cold DM

The browser procedure Astra runs per prospect in the codex-bare Chrome session. The raw
list already exists in `prospects.csv`, so this playbook is not about finding businesses.
It is about three things the seed file cannot do: confirming the evidence is still live,
resolving the owner and the DM handle, and grabbing one extra true detail.

Budget about 4 minutes per prospect. Everything here is free and public: Meta Ad Library,
Indeed, Google Maps, the company website, LinkedIn, Facebook, Instagram. No paid data
tools, no scrapers, no email finders.

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

## Step 1, re confirm the evidence is live

A message that opens with a job post that came down last week reads as a bot. Confirm
before writing, and record the date confirmed in the batch entry.

**Tier A, the hiring signal.** Open the `indeed_evidence` link or search Indeed for
`[business_name]` plus `[metro]`. The post has to still be up and still be the role in
`indeed_role`. A post older than about 30 days is stale even if it is technically still
listed: use it only if the listing shows a recent repost date, otherwise demote the row to
tier D and open with a side note instead.

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
empty for `source_rail = maps` rows. For maps rows, work these in order and stop at the
first hit. Record where the name came from, because a name from a signed review reply is
stronger than a name from a directory.

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

## Step 3, pick the channel

Only channels marked active in `config.md` count, and only accounts Zalo is actually
logged into in this Chrome profile. Record the exact profile URL so the right thread opens
without searching.

**Priority order:**

1. **LinkedIn DM to the owner.** Best channel for owner operators at this size. Usable
   when the owner's own profile exists and a message path is open. If he is a 2nd or 3rd
   degree connection with no open profile and no InMail, a connection request with no note
   is the move, and that request counts against the 80 per week limit, not the 15 DMs per
   day. **Log the connection request as a row in `sent-log.csv` with `stage` set to
   `CONNECT`**, because those rows are the only denominator the 80 per week cap has: count
   the last 7 days of them before sending another. Leave the pipeline row at `FOUND` with
   the pending request in the notes, so Step 2b of the daily loop picks it up and checks
   for an acceptance. The pipeline row becomes `SENT` only when a MESSAGE goes out.
2. **The owner's personal Facebook profile.** Better than the business page, because a
   page inbox goes to whoever manages the page and often lands in a filtered folder that
   nobody opens. Only use the business Page when the personal profile cannot be found, and
   record which one was used, because they behave differently.
3. **Instagram DM.** Use when the account is active, meaning it posted within the last
   month or so. DMs from non followers land in Requests, which many owners rarely check,
   so this is a real channel and a slow one.

**No open path on any of the three:** set the pipeline stage to `NO_CHANNEL`, write the
reason in notes, and move to the next row. Do not chase an email address, do not use a
website contact form, do not message a shared info@ inbox, and do not send to a general
company page as a substitute for the owner.

## Step 4, grab one extra side note

Every message carries one true specific. The tier evidence is one; this is the second, and
it is what makes a bump possible later without repeating yourself. While the tabs are
already open, take whichever of these is available and record it verbatim:

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

Some things only become visible in the browser. Kill the row rather than writing around
them, and record the reason in `drop_reason` style wording in the pipeline notes:

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
