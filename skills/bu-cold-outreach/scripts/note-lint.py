#!/usr/bin/env python3
"""Deterministic gate for cold DM notes (Zalo, 2026-09-09: "make sure we always get
messages that sound like texting a friend"), and since 2026-09-22 the gate that holds every
prospect to ONE message until that prospect replies (Zalo, 2026-09-22, about 17:05 ET: "we
should not send 4 messages with no reply... needs to be a single cold message").

Input: a JSON file, a list of objects, one per ENTRY of the batch, one entry per prospect:

  {"entry": 3, "prospect_id": "f4942f6285", "channel": "linkedin"|"facebook"|"instagram"|
   "facebook_groups", "variant": "C-li-P1", "kind": "message"|"connect", "text": "..."}

`kind` defaults to "message", the one message that prospect will ever get from Astra unless
they reply. "connect" is a LinkedIn connection request, and it carries NO note (Zalo chose
option A, 2026-09-22, about 17:10 ET): its `text` must be empty, and the one message goes
after the accept. Any other kind (a bump, a takeaway, a continuation) fails, and so does a
`part`, `sent_parts` or `joke_setup` field, because those were the machinery of the multi
part first touch and the bumps, retired 2026-09-22.

Usage:
  note-lint.py <notes.json>                  the SEND GATE. Finds pipeline.csv and
                                             sent-log.csv by walking up from notes.json (the
                                             working folder holds
                                             evidence/YYYY-MM-DD/session-N/notes.json)
  note-lint.py <notes.json> --folder <dir>   the same, with the working folder named
  note-lint.py <notes.json> --no-history     copy checks only. Prints COPY PASS and exits 2,
                                             never ALL PASS and never 0, because a batch
                                             nobody checked against the log is not cleared
                                             to send

Output: one line per note, PASS or FAIL with every reason, then the batch level checks.
Exit 0 only when every note passed AND the one message rule was checked against the working
folder. Exit 1 if anything failed. Exit 2 when the copy passed with --no-history. Facts are
not checked here; the humanizer pass and the approval do that.

The one message rule, three refusals (templates/messages.md, SKILL.md "One message"):

  1. A multi part first touch: two notes on one entry, or one prospect in two entries, or
     a `part` field. A first touch is one message, one bubble.
  2. A bump, a takeaway or a continuation, whatever it is called: any kind other than
     message or connect, any `stage` other than SENT or CONNECT, and the follow up phrases
     in BANNED ("last one from me", "following up", ...).
  3. A second message to a prospect who has not replied, on ANY channel: the prospect
     already has an outbound message in sent-log.csv (SENT, SENT_CONT, BUMP1, BUMP2, or a
     CONNECT that carried a note), or its pipeline row is SENT or COLD or has touches. A
     replied prospect is Zalo's thread and a DEAD one is never contacted, so both refuse
     too. A FRIEND row and a CONNECT with no note are not messages and refuse nothing.

Variant families. The family is read off the end of the variant id, and the laws that
belong to one family are not applied to another:

  P1, P2  the control. The four beat message one: the specific, the bridge, the fixed
          "what we do" line, the dare. On LinkedIn it is the one message after the accept.
  O1, I1  the LinkedIn open profile message and InMail: the control shape, LinkedIn only.
  J1, J2  the Facebook trade joke opener, ONE message since 2026-09-22: an approved joke,
          setup then punchline, then the fixed J1 or J2 ask, on one line. No digits, no
          pitch, no dare.
  G1      the Facebook group post. Nobody addressed by name, no per prospect demo claim,
          the dare and the demo number required. Channel NOT STARTED. Not a message to a
          person, so the one message history check does not apply to it.
  N1      RETIRED 2026-09-22. It was the LinkedIn connection note with no pitch, and a
          connection request no longer carries a note.

Three families are channel locked: a J message only lints on facebook, an O1 or I1 only on
linkedin, and a G1 post only on facebook_groups (which takes nothing else).

The offer law runs across ALL of them (added 2026-09-14): the tech as a product category is
banned everywhere, and every family that carries an offer has to name the outcome.

Tests: python3 ~/.claude/skills/bu-cold-outreach/scripts/note-lint.test.py
"""
import argparse, csv, json, os, re, sys

CONTRACTION = re.compile(r"(?i)\b\w+'s\s+(picking|running|live|on|not|going|been|still|already|just|coming|landing|doing|sitting|open|closed|out|in|at|the|a|an)\b|\b(that's|it's|you're|they're|we're|i'm|i've|you've|we've|there's|here's|what's|who's|somebody's|someone's|nobody's|ad's|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|can't|won't|wouldn't|couldn't|shouldn't|i'll|you'll|we'll|he's|she's|let's|you'd|i'd|we'd)\b")
# The offer law, added 2026-09-14 from research/ai-agents-sales-2026-09-12.md. The thing
# being SOLD is the outcome, an answered call and a booked job, never the technology as a
# product category. All four voices in that sweep agree (buyers, sellers, vendors, creators)
# and the vendors renamed themselves to match: Rosie leads with "Never miss another call",
# My AI Front Desk became Frontdesk, Jobber calls it Receptionist. The seller quote is the
# whole rule: "the second you lead with AI, half of them go straight to so I could just do
# that myself in ChatGPT for free", and a cold caller reports "AI receptionist" in the opener
# "drops you into the same bucket as every other reseller who called them last week".
#
# The law is the FRAME, not the vocabulary. P1_LINE names the mechanism once and then
# describes the outcome, which is the shape that works, and it is Zalo's own approved copy
# from 2026-09-08. So what is banned is the tech as a PRODUCT CATEGORY ("we build AI agents
# for home service", "our AI solution"), never the word that appears inside his fixed line.
TECH_AS_CATEGORY = [
    "ai receptionist", "ai agent", "ai assistant", "ai employee", "ai chatbot", "ai bot",
    "ai automation", "ai technology", "ai tool", "ai software", "ai platform", "ai system",
    "ai service", "voice ai", "ai voice", "ai-powered", "ai powered", "ai solution",
    "artificial intelligence", "i help businesses", "we help businesses",
    "i help companies", "we help companies", "i build ai", "we build ai", "we do ai",
    "our ai", "automation agency", "ai agency", "ai agencies", "ai receptionists",
]
BANNED_PLAIN = [
    "that is a person", "that is you", "that is your", "that is someone", "that is somebody",
    "caught my eye", "i noticed", "i came across", "hope you", "i hope", "reach out to you",
    "leverage", "streamline", "seamless", "solution", "cutting-edge", "game changer",
    "game-changer", "month-old", "i wanted to", "quick question", "just checking",
    "touching base", "circle back", "excited to", "passionate", "delighted", "kindly",
    "i would love", "i'd love to", "let me know if", "feel free", "don't hesitate",
    "website: answers",
    # The follow up phrases (2026-09-22). A prospect gets ONE message until he replies, so a
    # line that only makes sense as a second message is refused in any note on any channel,
    # whatever the batch calls it. "Last one from me" was the takeaway bump, word for word.
    "last one from me", "just following up", "following up on my", "bumping this",
    "my last message", "in case you missed", "circling back",
]
BANNED = BANNED_PLAIN + TECH_AS_CATEGORY
TECH_SET = set(TECH_AS_CATEGORY)
# The tech phrases are matched on WORD BOUNDARIES, not as bare substrings, and in an HVAC
# skill that is not a nicety: "our ai" is inside "your air", "we do ai" is inside "we do air
# conditioning", and `prospects.csv` carries 3,016 businesses with "Air" in the name. The
# 2026-09-14 QA pass caught a plain substring version failing a note that quoted the
# prospect's own air conditioning. The plain list above keeps substring matching, unchanged.
# The trailing `s?` is what makes the plural forms fire: "we build AI agents" is the shape a
# drafter actually writes, and a bare \b after "agent" refuses to match it.
TECH_RE = {p: re.compile(r"\b" + re.escape(p) + r"s?\b") for p in TECH_AS_CATEGORY}
DARE = "want to try and break it?"
P1_LINE = "trained a demo ai setter on your website"
P2_LINE = "built a quick demo off your website"
# LinkedIn was 300 while the message rode inside the connection request as its note. Since
# 2026-09-22 a connection request carries no note (option A), so every LinkedIn text this
# lint sees is a delivered message (the one message after the accept, an open profile
# message or an InMail) and takes the 420 DM limit the O1 and I1 lanes already had.
LIMITS = {"linkedin": 420, "facebook": 420, "instagram": 420, "facebook_groups": 600}
# `sent-log.csv` writes the short channel codes and the batch files have used both, so a note
# arriving as "fb" used to fall through to the 300 character LinkedIn default in silence. The
# aliases make the two vocabularies one, and an unrecognised channel now fails instead of
# quietly taking a limit that belongs to another channel (2026-09-14 QA pass).
CHANNEL_ALIASES = {"li": "linkedin", "fb": "facebook", "ig": "instagram",
                   "fbg": "facebook_groups", "facebook messenger": "facebook",
                   "facebook_messenger": "facebook"}
# The channels a note may declare. An invented channel name ("linkedin_dm" was one) fails
# rather than buying itself a limit.
CHANNELS = {"linkedin", "facebook", "instagram", "facebook_groups"}
# The two LinkedIn lanes that deliver on send (open profile message O1, InMail I1, added
# 2026-09-12) carry the control shape and exist on LinkedIn only.
LANE_CHANNEL = {"O1": ("linkedin", "an open profile message"), "I1": ("linkedin", "an InMail")}
LINK = re.compile(r"(?i)https?://|\bwww\.")
# Figure dash, en dash, em dash, horizontal bar, written as escapes so this file is
# itself free of the characters it bans.
DASH = re.compile("[\u2012\u2013\u2014\u2015]")

# The bridge may hand the owner the SHAPE of his own arithmetic, but only inside what the
# review or the posted hours already show (messages.md, the arithmetic bridge). What it may
# never do is assert a number about HIS results: the sweep's close is the owner's own math
# done in his head, not ours done for him, and this skill's oldest law is that Astra's
# messages carry no numbers about results at all. The lint cannot read the fact behind a
# bridge, so it catches an invented rate and an ROI claim outright, and a money amount or a
# percentage only when it shares a SENTENCE with a result. It is a gate, not a proof: a
# claim split across two sentences gets through. See OPEN-GAPS.md #4 for why that residue
# is deliberate (closing it reintroduces the false positive on his own quoted promo price).
# A number in a note is not automatically a claim about his results. Quoting his OWN
# advertised price is approved opener type 3 ("Your $79 tune up ad is running right now, and
# Google says you close at 5") and two notes that already went out on 2026-09-10 quote an
# "$83-off drain cleaning offer" and a "$50 referral offer". A flat ban on "$" failed both,
# which is the exact false positive class this lint exists to avoid (found by the 2026-09-14
# QA pass). So money and percentages are only a claim when they sit in the same SENTENCE as
# a result: his calls, his jobs, his revenue, what he is missing or losing.
NUMWORD = (r"(?:\d+|a\s+few|dozens?|hundreds?|thousands?|two|three|four|five|six|seven|eight|"
           r"nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)")
MONEY = re.compile(r"(?i)\$\s*\d|\b\d+(?:\.\d+)?\s*k\b|\b" + NUMWORD + r"\s*(?:dollars|bucks|grand)\b")
PERCENT = re.compile(r"(?i)\b\d+(?:\.\d+)?\s*%|\b(?:\d+(?:\.\d+)?|" + NUMWORD[4:-1] + r")\s*percent\b")
RESULT_NOUN = re.compile(r"(?i)\b(?:calls?|callers?|jobs?|leads?|customers?|clients?|installs?|"
                         r"bookings?|appointments?|estimates?|sales|deals?|revenue|business|work|"
                         r"voicemail|missing|missed|lost|losing|worth|ticket|table|door)\b")
SENTENCE_CLAIMS = [
    (MONEY, "a money amount next to a result: message one carries no numbers about results"),
    (PERCENT, "a percentage next to a result: message one carries no numbers about results"),
]
RESULT_CLAIMS = [
    # Spelled out numbers, "hundreds OF calls" and one adjective between the count and the
    # noun all had to be added: the house register spells numbers out ("fifteen hours a day",
    # "two calls"), so the digits only version banned the shape nobody writes and passed the
    # shape the drafter actually reaches for.
    (re.compile(r"(?i)\b" + NUMWORD + r"\s+(?:of\s+)?(?:\w+\s+)?(?:calls?|jobs?|leads?|customers?)\b"
                r"[^.?!]{0,30}\b(?:an?|per|every)\s+(?:day|week|month|year)\b"),
     "a rate we made up for him: the missed call math is HIS to do, on the call"),
    (re.compile(r"(?i)\bpays? for (?:itself|the year|the month|it)\b"),
     "an ROI claim: that is the close on the call, not message one"),
]


def result_claims(text):
    """Every shape that asserts a number about HIS results, whatever fact it hangs on."""
    reasons = []
    for sent in sentences(text):
        if not RESULT_NOUN.search(sent):
            continue
        for pattern, why in SENTENCE_CLAIMS:
            if pattern.search(sent): reasons.append(why)
    for pattern, why in RESULT_CLAIMS:
        if pattern.search(text): reasons.append(why)
    return reasons

# The positive half of the offer law. A pitch note has to say what he GETS, in outcome
# words, not just that a demo exists: the fixed line alone is a mechanism sentence, and its
# tail is drafted per row, so the outcome can drift out of it while P1_LINE still matches.
# "catches" is deliberately NOT in this list. It is the bridge word ("that's the call this
# catches"), so counting it as the offer let a note that never says what the thing DOES pass
# on the strength of its own bridge clause.
OUTCOME_ANSWER = ["answers", "answer ", "answered", "picks up", "pick up", "picking up",
                  "takes those calls", "takes the calls", "takes your calls", "gets the phone"]
OUTCOME_BOOK_RE = re.compile(
    r"(?i)\bbooks?\s+(?:the\s+job|the\s+appointment|jobs|it|them|you|him|her)\b"
    r"|\bgets?\s+(?:the\s+job|it)\s+(?:on|into|in|booked)\b|\bon\s+(?:your|the)\s+calendar\b"
    r"|\bschedul\w+\s+(?:the\s+)?(?:job|appointment|work)\b|\bbooks?\s+the\s+work\b")

# The J arm is fixed copy end to end, approved by Zalo in templates/gold-notes.md.
# Adding a joke is a deliberate act: it lands here and in gold-notes.md, together.
APPROVED_JOKES = [
    ("Why don't ducts keep secrets?", "Everything leaks eventually."),
    ("My AC and I are fighting again.", "Now it's giving me the cold shoulder."),
    ("Serious question for you. Why did the thermostat get promoted over the whole crew?",
     "Only one with a degree."),
    ("Why did the plumber fold in poker?", "He kept getting flushed."),
    ("My kid asked me what a plumber's favorite shoe is.",
     "Clogs. He's seven and I'm still mad about it."),
    ("What do you call a plumber who works every Saturday?", "Drained."),
]
# The asks are unchanged from 2026-09-12 so the J1 against J2 numbers stay comparable. What
# changed on 2026-09-22 is that the joke and the ask are ONE message: until then the setup,
# the punchline and the ask were three bubbles, and Zalo's screenshot of the Sandra Zurick
# thread (three bubbles on 09-14 and a "Last one from me" bump on 09-22, zero replies) is
# the reason the rule exists.
J_ASKS = {
    "J1": re.compile(r"^Alright .{1,40}, real question and then I'll leave the jokes alone\. "
                     r"Would you be open to talking about the calls that come in after you close\?$"),
    "J2": re.compile(r"^Okay .{1,40}, that's my one joke of the day\. Mind if I ask you "
                     r"something about the calls that come in after you close\?$"),
}
# No joke goes to more than this many rows in one day (templates/messages.md). Six approved
# jokes against a Facebook ceiling of 10 makes this a cap, not a ban, and before it was a
# number in the lint it was prose only: 10 rows running two jokes five times each passed.
J_ROW_CAP = 4
FAMILIES = {"P1": "pitch", "P2": "pitch", "N1": "retired", "J1": "joke", "J2": "joke",
            "O1": "pitch", "I1": "pitch", "G1": "group"}
RETIRED = {
    "N1": "N1 was retired 2026-09-22: it was the LinkedIn connection note with no pitch, and a "
          "connection request carries NO note now (Zalo, option A). The one LinkedIn message "
          "goes after the accept and it is the control, P1 or P2",
}
# G1, the Facebook group post (added 2026-09-14, channel NOT STARTED, see config.md). It is
# a post in a local business or trade group, not a DM: nobody is addressed by name, there is
# no "your website" to have trained a demo on, and what carries it is the outcome opener plus
# the dare plus the demo number. It lints so that the offer law is mechanical on this channel
# from its first draft rather than prose only, and nothing on it ships until Zalo opens the
# channel and the demo agent passes the interrupt gate in SKILL.md.
DEMO_NUMBER = re.compile(r"\b(?:\+?1[ .\-]?)?\(?\d{3}\)?[ .\-]?\d{3}[ .\-]?\d{4}\b")
# The J arm is a Facebook personal profile opener and G1 is a group post. A family on the
# wrong channel is not a variant of the arm, it is a different experiment nobody approved.
ARM_CHANNEL = {"joke": ("facebook", "J", "a"), "group": ("facebook_groups", "G1", "a")}

# ------------------------------------------------ the one message rule (Zalo, 2026-09-22)
ONE_MESSAGE = "one message per prospect until they reply (Zalo, 2026-09-22)"
# What a notes.json entry may be. "message" is the one message; "connect" is a LinkedIn
# connection request, which carries NO note. There is no third kind: a bump, a takeaway and
# a continuation are all a second message to a prospect who has not replied.
KINDS = {"message", "connect"}
# The fields of the retired machinery. A `part` was one bubble of a multi part first touch;
# `sent_parts` and `joke_setup` let a later batch finish one. All three mean more than one
# message, so all three fail on sight rather than being ignored.
RETIRED_FIELDS = ("part", "sent_parts", "joke_setup")
# If a note says which `sent-log.csv` stage it will be logged as, only these two are one
# message. SENT_CONT, BUMP1 and BUMP2 are the retired second, third and fourth messages.
NOTE_STAGES = {"SENT", "CONNECT"}
# sent-log.csv stages that are a message typed at a person. A CONNECT row is one only when it
# carried a note (every one before 2026-09-22 did), and a FRIEND row never is.
MESSAGE_STAGES = {"SENT", "SENT_CONT", "BUMP1", "BUMP2"}
# Pipeline stages. SENT and COLD mean the one message went out and nothing came back.
# Everything from REPLIED on is Zalo's thread, and Astra types nothing into it.
HAD_ITS_MESSAGE = {"SENT", "COLD"}
# The sha1 of the empty string. A note-less CONNECT row logged with the hash of nothing is
# still a request with no note, so this value reads as empty (2026-09-22 QA observation).
EMPTY_SHA1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
# This skill's own directory. Its templates/ and scripts/fixtures/ hold a pipeline.csv too, so
# a history check pointed at either would "pass" against an empty or a made up log.
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ZALO_STAGES = {"REPLIED", "DEMO_SENT", "TESTED", "VSL_SENT", "CALL", "NO_SHOW",
               "CALL_HELD", "CLOSED"}


def note_kind(note):
    return str(note.get("kind") or "message").strip().lower()


def pid_of(value):
    """Prospect ids are compared trimmed and lower case on both sides, so a drafter's "F4942F6285"
    is the log's "f4942f6285" and cannot slip a second message past the history check."""
    return str(value or "").strip().lower()


def note_channel(note):
    """One normalisation, used by check() AND by the diversity buckets. They disagreed."""
    raw = (note.get("channel") or "linkedin").lower()
    return CHANNEL_ALIASES.get(raw, raw)


def family(variant):
    return FAMILIES.get((variant or "")[-2:].upper(), None)


def sentences(text):
    parts = re.split(r"(?<=[.?!])[\"')]*\s+", text.strip())
    return [p for p in parts if p]


def shape(text):
    first = sentences(text)[0] if sentences(text) else ""
    first = re.sub(r"^(hi|hey|hello)\s+[^,]+,\s*", "", first, flags=re.I)
    first = re.sub(r'"[^"]*"', "QUOTE", first)
    first = re.sub(r"\b[A-Z][a-z]+'s\b", "NAME's", first)
    toks = re.findall(r"[A-Za-z']+", first.lower())
    return " ".join(toks[:3])


def common(text, ch, low):
    """The checks every family gets, whatever it is."""
    reasons = []
    key = ch
    if DASH.search(text): reasons.append("em or en dash")
    if len(text) > LIMITS.get(key, 300): reasons.append(f"{len(text)} chars over the {key} limit {LIMITS.get(key, 300)}")
    for b in BANNED:
        if b in TECH_SET:
            if TECH_RE[b].search(low):
                reasons.append(f"the tech as a product category: {b!r}. Sell the outcome, "
                               "the call answered and the job booked")
        elif b in low:
            reasons.append(f"banned phrase: {b!r}")
    reasons += result_claims(text)
    if "!" in text: reasons.append("exclamation mark")
    if LINK.search(text): reasons.append("a link: message one never carries one")
    if "[" in text or "]" in text: reasons.append("an unfilled token")
    return reasons


def check_pitch(text, low, var):
    """The control. Unchanged from 2026-09-09."""
    reasons = []
    if not CONTRACTION.search(text): reasons.append("no contraction: reads as machine written")
    if DARE not in low: reasons.append("the dare is missing")
    if var.endswith("P1") and P1_LINE not in low: reasons.append("P1 row without the P1 line")
    if var.endswith("P2") and P2_LINE not in low: reasons.append("P2 row without the P2 line")
    if low.count("24/7") > 1: reasons.append("24/7 more than once")
    if low.count("review") > 1: reasons.append("'review' more than once")
    sents = sentences(text)
    if not 3 <= len(sents) <= 7: reasons.append(f"{len(sents)} sentences, want 3 to 7")
    pitch_idx = next((i for i, s in enumerate(sents) if P1_LINE in s.lower() or P2_LINE in s.lower()), None)
    if pitch_idx is None: reasons.append("no pitch sentence")
    elif pitch_idx < 2: reasons.append("no bridge: the pitch follows the fact with nothing in between")
    reasons += outcome_missing(" ".join(sents[pitch_idx:]) if pitch_idx is not None else text)
    if re.search(r"\b\d+-month-old\b", low): reasons.append("N-month-old time reference")
    return reasons


def outcome_missing(text):
    """The offer law's positive half: the note names what he gets, answered and booked.

    P1_LINE and P2_LINE are the fixed heads of their sentences and the TAIL is drafted per
    row ("that takes those calls 24/7 and books the job", "it picks up when nobody can, day
    or night, and books the job"), so a row can carry the approved head and still drift into
    describing a product. Both halves are in every note Zalo has approved.

    Read the OFFER, not the whole note. A bag of words over the whole text was satisfied by
    the fact clause: a note whose opener quoted a review saying "nobody answers the phone and
    she books the job elsewhere" passed with a pitch that was pure product speak
    (2026-09-14 QA pass). The caller passes the offer half; a family with no pitch sentence
    to anchor on passes the whole text, which is the old behaviour.
    """
    low = text.lower()
    reasons = []
    if not any(a in low for a in OUTCOME_ANSWER):
        reasons.append("no answered call in the offer: say it answers, picks up or takes the calls")
    if not OUTCOME_BOOK_RE.search(text):
        reasons.append("no booked job in the offer: the outcome sold is the job on the calendar")
    return reasons


# Words that address the ROOM. The first cut of the rule keyed on capitalisation under
# (?i), which made it "greeting plus one word plus comma": it rejected "Hey everyone," and
# "Hi all," and passed "Hi Mike." and "Mike, your phone" (2026-09-14 QA pass).
ROOM_WORDS = {
    # the room
    "everyone", "everybody", "folks", "all", "guys", "team", "owners", "y'all", "yall",
    "anyone", "anybody", "contractors", "plumbers", "techs", "neighbors", "neighbours",
    "there", "friends", "crew",
    # sentence adverbs and openers that address nobody
    "alright", "allright", "okay", "ok", "look", "listen", "so", "honestly", "right",
    "well", "anyway", "quick", "real", "serious", "genuine", "update", "psa", "morning",
    "afternoon", "evening", "first", "second", "also", "meanwhile", "anyways",
    # the metros in play, per config.md "Metros in play"
    "phoenix", "dallas", "worth", "houston", "tampa", "orlando", "miami", "atlanta",
    "vegas", "antonio", "austin", "charlotte", "jacksonville",
}
GREETED = re.compile(r"^\s*(?:Hi|Hey|Hello|Yo|Morning|Afternoon|Evening)\s+([A-Za-z']+)"
                     r"(?:\s+and\s+([A-Za-z']+))?\s*[,.!]")
BARE_NAME = re.compile(r"^\s*([A-Z][a-z]+)(?:\s+and\s+([A-Z][a-z]+))?\s*,")


def addressed_by_name(text):
    """True when a post opens by addressing a PERSON rather than the room."""
    m = GREETED.match(text) or BARE_NAME.match(text)
    if not m:
        return False
    return any(w and w[:1].isupper() and w.lower() not in ROOM_WORDS for w in m.groups())


def check_group(text, low):
    """G1: the Facebook group post. Outcome opener, one line on what it does, the dare, the
    demo number, and nothing else. No link on the first post (common already blocks one).

    Two laws are specific to this channel. It carries no per prospect demo claim, because a
    post has no "your website" to have been trained on and saying so in a room of strangers
    is the one lie this rail cannot afford. And it carries the demo NUMBER, because without
    a number the owner can call and try to break, the post is an ad; the number is the whole
    mechanic the sweep found four creators, five vendor home pages and the buyers' own
    "let me call it" checklist agreeing on.
    """
    reasons = []
    if not CONTRACTION.search(text): reasons.append("no contraction: reads as machine written")
    if DARE not in low: reasons.append("the dare is missing")
    if P1_LINE in low or P2_LINE in low:
        reasons.append("a per prospect demo claim in a group post: there is no 'your website' in a group")
    if addressed_by_name(text):
        reasons.append("a group post is not addressed to one person by name")
    if not DEMO_NUMBER.search(text):
        reasons.append("no demo number: the post is the dare plus a number he can call")
    sents = sentences(text)
    reasons += outcome_missing(" ".join(sents[1:]) if len(sents) > 1 else text)
    if not 2 <= len(sents) <= 6: reasons.append(f"{len(sents)} sentences, want 2 to 6")
    return reasons


def joke_of(text):
    """The approved joke a J message opens on, or None. Setup, one space, punchline, one
    space, then the ask: one line, because Messenger sends on Enter and a line break would
    leave as a second bubble."""
    for setup, punch in APPROVED_JOKES:
        m = re.match(re.escape(setup) + r" +" + re.escape(punch) + r"(?: +(.*))?$", text.strip())
        if m:
            return setup, m.group(1) or ""
    return None


def check_joke(text, low, var):
    """J1 and J2: ONE message since 2026-09-22. An approved joke, then the fixed ask, on one
    line. No fact and no offer by design; the paste test is waived for this arm only."""
    reasons = []
    if "\n" in text:
        reasons.append("a line break in a joke message: Messenger sends on Enter, so it would "
                       "leave as two bubbles. One line, one message")
    if re.search(r"\d", text): reasons.append("a digit: the joke arm carries no numbers at all")
    if DARE in low: reasons.append("the dare is in a joke note")
    if P1_LINE in low or P2_LINE in low: reasons.append("a pitch line in a joke note")
    if "24/7" in low: reasons.append("24/7 in a joke note")
    if re.match(r"(?i)^\s*(hi|hey|hello|yo)\b", text):
        reasons.append("a greeting before the joke: the message opens on the joke and the name "
                       "arrives in the ask")
    if not CONTRACTION.search(text): reasons.append("no contraction: reads as machine written")
    arm = (var or "")[-2:].upper()
    found = joke_of(text)
    if found is None:
        reasons.append("not an approved joke from gold-notes.md, setup then punchline, at the "
                       "start of the message")
    else:
        pattern = J_ASKS.get(arm)
        if pattern is None or not pattern.match(found[1].strip()):
            reasons.append(f"the joke is not followed by the fixed {arm} ask, in the same message")
    return reasons


def check_connect(note, ch):
    """A LinkedIn connection request: NO note (Zalo, option A, 2026-09-22). The one message
    goes after the accept, so the request itself carries nothing to lint but its emptiness."""
    reasons = []
    text = note.get("text") or ""
    if text.strip():
        reasons.append(f"a connection note ({len(text.strip())} chars): a LinkedIn connection "
                       "request goes out with NO note (Zalo, option A, 2026-09-22). The one "
                       "message goes after the accept, as its own entry")
    if ch != "linkedin":
        reasons.append(f"a connect entry on {ch}: connection requests are LinkedIn only (a "
                       "Facebook friend request carries nothing and has no notes.json entry)")
    if family(note.get("variant", "")) != "pitch" or (note.get("variant") or "")[-2:].upper() not in ("P1", "P2"):
        reasons.append("a connect entry names the variant its accepted thread will carry, "
                       f"<tier>-li-P1 or <tier>-li-P2, got {note.get('variant')!r}")
    return reasons


def one_message_fields(note):
    """The per note half of the one message rule: nothing that is not the one message."""
    reasons = []
    kind = note_kind(note)
    if kind not in KINDS:
        reasons.append(f"kind {kind!r}: {ONE_MESSAGE}. Bumps, takeaways and continuations are "
                       "retired; the only kinds are 'message' and 'connect'")
    stage = note.get("stage")
    if stage is not None and str(stage).strip().upper() not in NOTE_STAGES:
        reasons.append(f"stage {stage!r}: {ONE_MESSAGE}. SENT_CONT, BUMP1 and BUMP2 are retired")
    for f in RETIRED_FIELDS:
        if note.get(f) is not None:
            reasons.append(f"a {f!r} field: the first touch is one message, one bubble. The joke "
                           "arm's parts and its continuation marker were retired 2026-09-22")
    return reasons


def check(note):
    text = note.get("text") or ""; raw_ch = (note.get("channel") or "linkedin").lower()
    ch = note_channel(note); var = note.get("variant", "")
    low = text.lower()
    fam = family(var)
    lane = (var or "")[-2:].upper()
    reasons = one_message_fields(note)
    if ch not in CHANNELS:
        reasons.append(f"unrecognised channel {raw_ch!r}: expected one of {sorted(CHANNELS)}")
    if note_kind(note) == "connect":
        return reasons + check_connect(note, ch)
    reasons += common(text, ch, low)
    if fam is None:
        reasons.append(f"unrecognised variant family in {var!r}: expected P1, P2, J1, J2, O1, I1 or G1")
        fam = "pitch"
    if fam == "retired":
        return reasons + [RETIRED.get(lane, f"{lane} is retired")]
    lane_ch, lane_label = LANE_CHANNEL.get(lane, (None, None))
    if lane_ch and ch != lane_ch:
        reasons.append(f"{lane_label} on {ch}: the {lane} lane is {lane_ch} only")
    want_ch, label, art = ARM_CHANNEL.get(fam, (None, None, None))
    if want_ch and ch != want_ch:
        reasons.append(f"{art} {label} note on {ch}: the {label} arm is {want_ch} only")
    # The lock runs both ways on facebook_groups. It is a posting channel, not an inbox:
    # a DM shape there would be a per prospect message typed into a room of strangers.
    if ch == "facebook_groups" and fam != "group":
        reasons.append(f"a {fam} note on facebook_groups: that channel takes G1 posts only")
    if fam == "pitch":
        reasons += check_pitch(text, low, var)
    elif fam == "joke":
        reasons += check_joke(text, low, var)
    elif fam == "group":
        reasons += check_group(text, low)
    return reasons


def joke_row_cap(notes):
    """No approved joke goes to more than J_ROW_CAP rows in one batch."""
    count = {}
    for n in notes:
        if family(n.get("variant", "")) == "joke" and note_kind(n) == "message":
            found = joke_of(n.get("text") or "")
            if found:
                count[found[0]] = count.get(found[0], 0) + 1
    return [f"FAIL batch: the joke {j!r} goes to {c} rows today, cap is {J_ROW_CAP} (templates/messages.md)"
            for j, c in sorted(count.items()) if c > J_ROW_CAP]


def one_message_batch(notes):
    """Refusal 1, batch side: one entry is one message, and one prospect is one entry."""
    out = []
    by_entry, by_pid = {}, {}
    for n in notes:
        if n.get("entry") is not None:
            by_entry.setdefault(str(n.get("entry")), []).append(n)
        pid = pid_of(n.get("prospect_id"))
        # Two notes on one entry are already refused above; two notes with no entry number
        # at all are two messages, so they are counted here rather than folded together.
        if pid and (n.get("entry") is None or n.get("entry") not in by_pid.get(pid, [])):
            by_pid.setdefault(pid, []).append(n.get("entry"))
    for e, ns in sorted(by_entry.items()):
        if len(ns) > 1:
            out.append(f"FAIL batch: entry {e} carries {len(ns)} notes. A first touch is ONE "
                       f"message, one bubble, never parts or a continuation: {ONE_MESSAGE}")
    for pid, es in sorted(by_pid.items()):
        if len(es) > 1:
            out.append(f"FAIL batch: prospect {pid} is in {len(es)} entries {es}. {ONE_MESSAGE}: "
                       "one entry, one channel, one message")
    return out


# --------------------------------------------------------------- the history check
def read_csv(path):
    """Rows as dicts keyed by the header, each header cell stripped (the files have been
    written with and without a space after each comma)."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    head = [h.strip().lstrip("\ufeff").strip() for h in rows[0]]
    return head, [dict(zip(head, r)) for r in rows[1:]]


def find_folder(notes_path):
    """The working folder: the nearest directory at or above notes.json holding pipeline.csv."""
    d = os.path.dirname(os.path.abspath(notes_path))
    while True:
        if os.path.isfile(os.path.join(d, "pipeline.csv")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_history(folder):
    """(pipeline row by prospect id, outbound message rows by prospect id, every prospect id
    the folder knows). Raises ValueError with a sentence that names the file when it cannot
    be read or lacks a column."""
    out = []
    for name, need in (("pipeline.csv", ("prospect_id", "stage")),
                       ("sent-log.csv", ("prospect_id", "stage")),
                       ("prospects.csv", ("prospect_id",))):
        path = os.path.join(folder, name)
        try:
            head, rows = read_csv(path)
        except OSError as e:
            raise ValueError(f"cannot read {path} ({e.strerror or e}). On iCloud run "
                             "`brctl download` on it, wait a few seconds, and lint again")
        missing = [c for c in need if c not in head]
        if missing:
            raise ValueError(f"{path} has no {', '.join(missing)} column")
        out.append(rows)
    pipe = {}
    for r in out[0]:
        pid = pid_of(r.get("prospect_id"))
        if pid:
            pipe[pid] = r
    sent = {}
    for r in out[1]:
        pid = pid_of(r.get("prospect_id"))
        if not pid:
            continue
        stage = (r.get("stage") or "").strip().upper()
        typed = any((r.get(k) or "").strip() not in ("", EMPTY_SHA1)
                    for k in ("message_text", "message_sha1", "message_head"))
        if stage in MESSAGE_STAGES or typed:
            sent.setdefault(pid, []).append(r)
    known = set(pipe) | {pid_of(r.get("prospect_id")) for r in out[2]} - {""}
    return pipe, sent, known


def history_failures(notes, pipe, sent, known):
    """Refusal 3: a second message to a prospect who has not replied, on any channel. Also a
    replied prospect (Zalo's thread) and a DEAD one (never again). A G1 group post has no
    prospect and is skipped."""
    out = []
    for n in notes:
        if family(n.get("variant", "")) == "group":
            continue
        e = n.get("entry"); kind = note_kind(n)
        pid = pid_of(n.get("prospect_id"))
        if not pid:
            out.append(f"FAIL entry {e}: no prospect_id, so the one message rule cannot be "
                       "checked against pipeline.csv and sent-log.csv")
            continue
        if pid not in known:
            # An id the folder does not know would read as a fresh prospect, so a one character
            # slip in a real id ("b7c99e2c2" for "b7c99e2c2d") used to pass as a first touch
            # (2026-09-22 QA pass). Every real prospect is in prospects.csv or pipeline.csv.
            out.append(f"FAIL entry {e}: prospect_id {n.get('prospect_id')!r} is in neither "
                       "pipeline.csv nor prospects.csv, so the one message rule cannot be "
                       "checked. Copy the id exactly from pipeline.csv")
            continue
        row = pipe.get(pid) or {}
        stage = (row.get("stage") or "").strip().upper()
        try:
            touches = int((row.get("touches") or "0").strip() or 0)
        except ValueError:
            touches = 0
        prior = sent.get(pid, [])
        what = "a connection request" if kind == "connect" else "a message"
        if stage == "DEAD":
            out.append(f"FAIL entry {e}: prospect {pid} is DEAD. Never contacted again, on any channel")
        elif stage in ZALO_STAGES:
            out.append(f"FAIL entry {e}: prospect {pid} is at {stage}: the prospect replied, so the "
                       f"thread is Zalo's and Astra types nothing into it, {what} included")
        elif prior:
            first = prior[0]
            more = f", plus {len(prior) - 1} more" if len(prior) > 1 else ""
            label = (first.get("stage") or "").strip()
            if label.upper() == "CONNECT":
                label = "a connection request that carried a note,"
            out.append(f"FAIL entry {e}: prospect {pid} already got its one message "
                       f"({label} {(first.get('timestamp_et') or '').strip()} "
                       f"on {(first.get('channel') or '').strip()}{more}) and has not replied. "
                       f"{ONE_MESSAGE}: nothing more, on any channel, {what} included")
        elif stage in HAD_ITS_MESSAGE or touches > 0:
            out.append(f"FAIL entry {e}: prospect {pid} is at {stage or 'FOUND'}, touches {touches}, "
                       f"in pipeline.csv, so it already had its one message. {ONE_MESSAGE}")
    return out


def diversity_failures(openers, label=None):
    """How many notes may open the same way: half the population, floor 2."""
    shapes = {}
    for n in openers: shapes.setdefault(shape(n["text"]), []).append(n.get("entry"))
    cap = max(2, -(-len(openers) // 2))
    where = f" on {label}" if label else ""
    out = [f"FAIL batch: {len(ents)} notes open the same way ({s!r}){where}: entries {ents}; cap is {cap}"
           for s, ents in shapes.items() if len(ents) > cap]
    return out, shapes


def main(argv=None):
    ap = argparse.ArgumentParser(description="The batch gate: copy laws plus the one message rule.")
    ap.add_argument("notes", nargs="?", default="notes.json")
    ap.add_argument("--folder", help="the working folder holding pipeline.csv and sent-log.csv "
                    "(default: the nearest one at or above notes.json)")
    ap.add_argument("--no-history", action="store_true",
                    help="copy checks only; exits 2 on a copy pass, because it is not a send gate")
    ap.add_argument("--fixture", action="store_true",
                    help="allow a history folder inside this skill (the test fixtures); exits 2 "
                    "on a pass, because a fixture is not a send gate")
    args = ap.parse_args(argv)
    notes = json.load(open(args.notes))
    if not isinstance(notes, list) or not all(isinstance(n, dict) for n in notes):
        print("FAIL: notes.json must be a list of objects, one per entry"); sys.exit(1)
    failed = 0
    for n in notes:
        r = check(n)
        tag = "PASS" if not r else "FAIL"
        failed += bool(r)
        kind = f", {note_kind(n)}" if note_kind(n) != "message" else ""
        print(f"{tag} entry {n.get('entry')} ({n.get('channel')}, {n.get('variant')}{kind}, "
              f"{len(n.get('text') or '')} chars)" + ("" if not r else ": " + "; ".join(r)))
    for r in one_message_batch(notes) + joke_row_cap(notes):
        failed += 1; print(r)
    # The history check is the half of the one message rule a single note cannot show: has
    # this prospect already been messaged? It is ON unless --no-history says otherwise, and a
    # run without it cannot print ALL PASS or exit 0.
    folder = None
    if not args.no_history:
        folder = args.folder or find_folder(args.notes)
        if not folder:
            failed += 1
            print(f"FAIL batch: no pipeline.csv at or above {os.path.dirname(os.path.abspath(args.notes))}, "
                  "so the one message rule cannot be checked. Lint the batch's notes.json inside "
                  "the working folder, or pass --folder <working folder>")
        elif not args.fixture and os.path.realpath(folder).startswith(os.path.realpath(SKILL_DIR) + os.sep):
            failed += 1
            print(f"FAIL batch: the history folder {folder} is inside the skill itself (a template "
                  "or a test fixture), not the working folder, so nothing real was checked")
        else:
            try:
                pipe, sent, known = load_history(folder)
            except ValueError as e:
                failed += 1; print(f"FAIL batch: {e}")
            else:
                for r in history_failures(notes, pipe, sent, known):
                    failed += 1; print(r)
    # Opener diversity is about how a first touch OPENS, so it reads every message. A connect
    # entry has no text and is not in this population.
    openers = [n for n in notes if note_kind(n) == "message" and (n.get("text") or "").strip()]
    over, shapes = diversity_failures(openers)
    for line in over:
        failed += 1; print(line)
    # The cap also runs PER CHANNEL, because the whole file cap is diluted by the other
    # channels: five byte identical group posts in a batch that also carries ten LinkedIn
    # notes passed a cap of eight, which is exactly the saturation failure the groups channel
    # is warned about (2026-09-14 QA pass). Only shapes the whole file check did not already
    # name are reported, so nothing is printed twice.
    named = {line.split("(")[1].split(")")[0] for line in over}
    per_ch = {}
    for n in openers: per_ch.setdefault(note_channel(n), []).append(n)
    for chan, group in sorted(per_ch.items(), key=lambda kv: str(kv[0])):
        if len(per_ch) < 2: break
        more, _ = diversity_failures(group, label=str(chan))
        for line in more:
            if line.split("(")[1].split(")")[0] in named: continue
            failed += 1; print(line)
    tail = f"{len(notes)} notes, {len(openers)} openers, {len(shapes)} opener shapes"
    if failed:
        print(f"{failed} FAILURE(S): {tail}"); sys.exit(1)
    if args.no_history:
        print(f"COPY PASS, HISTORY NOT CHECKED (--no-history): {tail}. Not a send gate: lint "
              "it inside the working folder to check the one message rule"); sys.exit(2)
    if args.fixture:
        print(f"FIXTURE PASS: {tail}. Checked against {folder} in --fixture mode. Not a send "
              "gate"); sys.exit(2)
    people = len({pid_of(n.get('prospect_id')) for n in notes if family(n.get('variant', '')) != 'group'})
    print(f"ALL PASS: {tail}. One message rule checked against {folder}: {people} prospects, "
          "none already messaged, none replied or dead"); sys.exit(0)


if __name__ == "__main__":
    main()
