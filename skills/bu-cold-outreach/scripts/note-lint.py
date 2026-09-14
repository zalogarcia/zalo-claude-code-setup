#!/usr/bin/env python3
"""Deterministic gate for cold DM notes (Zalo, 2026-09-09: "make sure we always get
messages that sound like texting a friend").

Input: a JSON file, a list of objects: {"entry": 3, "channel": "linkedin"|"facebook"|
"instagram", "variant": "C-li-P1", "text": "...", "part": "setup"|"punchline"|"ask",
"sent_parts": ["setup"], "joke_setup": "..."}.
`part` is required on the joke arm (J1, J2) and ignored everywhere else: the batch
diversity check keys on the variant family, not on the presence of that field, so a
stray `part` on a control note cannot drop it out of the count.
`sent_parts` and `joke_setup` are the continuation marker, joke arm only, and a note
outside that arm carrying either is a bug and fails. See check_joke_sequences.
Output: one line per note, PASS or FAIL with every reason, then the batch level
checks. Exit 1 if anything failed. Facts are not checked here; the humanizer pass
and the approval do that. This catches the machine tells that slipped through
three times on 2026-09-09.

Four variant families. Three were split out 2026-09-12 when the test arms were added, the
fourth 2026-09-14 with the Facebook groups channel. The family is read off the end of the
variant id, and the laws that belong to one family are not applied to another:

  P1, P2  the control. The four part message one. Dare required, fixed "what we do"
          line required, bridge required. Unchanged from 2026-09-09.
  N1      the LinkedIn note with no pitch. Dare and pitch line must be ABSENT, the
          note ends on the fixed permission question.
  J1, J2  the Facebook trade joke opener. Three parts per prospect, each an approved
          fixed string, no digits, no pitch, no dare.
  G1      the Facebook group post. Nobody addressed by name, no per prospect demo
          claim, the dare and the demo number required. Channel NOT STARTED.

Three families are channel locked, so the channel is checked against the family: an N1 note
only lints on linkedin, a J note only on facebook (both added 2026-09-12 after the audit
found a J triple on linkedin and an N1 on facebook linting clean), and a G1 post only on
facebook_groups.

The offer law runs across ALL of them (added 2026-09-14): the tech as a product category is
banned everywhere, and every family that carries an offer has to name the outcome.

Tests: python3 ~/.claude/skills/bu-cold-outreach/scripts/note-lint.test.py
"""
import json, re, sys

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
LIMITS = {"linkedin": 300, "linkedin_dm": 420, "facebook": 420, "instagram": 420,
          "facebook_groups": 600}
# `sent-log.csv` writes the short channel codes and the batch files have used both, so a note
# arriving as "fb" used to fall through to the 300 character LinkedIn default in silence. The
# aliases make the two vocabularies one, and an unrecognised channel now fails instead of
# quietly taking a limit that belongs to another channel (2026-09-14 QA pass).
CHANNEL_ALIASES = {"li": "linkedin", "fb": "facebook", "ig": "instagram",
                   "fbg": "facebook_groups", "facebook messenger": "facebook",
                   "facebook_messenger": "facebook"}
# The channels a note may declare. `linkedin_dm` is in LIMITS but is NOT one of them: it is
# the limit the O1 and I1 lanes borrow, and a note declaring it would buy a 420 character
# invitation note (2026-09-14 QA pass, second round).
CHANNELS = {"linkedin", "facebook", "instagram", "facebook_groups"}
# The two LinkedIn lanes that deliver on send (open profile message O1, InMail I1, added
# 2026-09-12) are DMs, not invitation notes: they carry the Facebook control shape and its
# 420 limit, and they exist on LinkedIn only.
DM_LANES = {"O1": "linkedin_dm", "I1": "linkedin_dm"}
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

# The N1 arm exists to measure a note with NO offer in it, so an offer in any wording is
# the one thing it cannot carry. The two exact pitch lines are not enough: a paraphrase
# passes them and the arm quietly stops being the thing being measured.
NOPITCH_CLAIMS = ["demo", "ai setter", "books the job", "book the job",
                  "picks up when nobody", "answers your calls"]

# The N1 arm's closer is fixed copy. The arm measures the accept gate, so the question
# is not a per row rewrite: a drifting closer would destroy the measurement.
N1_CLOSER = "mind if i ask you something about it?"

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
J_ASKS = {
    "J1": re.compile(r"^Alright .{1,40}, real question and then I'll leave the jokes alone\. "
                     r"Would you be open to talking about the calls that come in after you close\?$"),
    "J2": re.compile(r"^Okay .{1,40}, that's my one joke of the day\. Mind if I ask you "
                     r"something about the calls that come in after you close\?$"),
}
J_PARTS = ("setup", "punchline", "ask")
# No joke goes to more than this many rows in one day (templates/messages.md). Six approved
# jokes against a Facebook ceiling of 10 makes this a cap, not a ban, and before it was a
# number in the lint it was prose only: 10 rows running two jokes five times each passed.
J_ROW_CAP = 4
FAMILIES = {"P1": "pitch", "P2": "pitch", "N1": "nopitch", "J1": "joke", "J2": "joke",
            "O1": "pitch", "I1": "pitch", "G1": "group"}
# G1, the Facebook group post (added 2026-09-14, channel NOT STARTED, see config.md). It is
# a post in a local business or trade group, not a DM: nobody is addressed by name, there is
# no "your website" to have trained a demo on, and what carries it is the outcome opener plus
# the dare plus the demo number. It lints so that the offer law is mechanical on this channel
# from its first draft rather than prose only, and nothing on it ships until Zalo opens the
# channel and the demo agent passes the interrupt gate in SKILL.md.
DEMO_NUMBER = re.compile(r"\b(?:\+?1[ .\-]?)?\(?\d{3}\)?[ .\-]?\d{3}[ .\-]?\d{4}\b")
# Both test arms are one channel each, by design: N1 measures the LinkedIn accept gate and
# the J arm is a Facebook personal profile opener. A family on the wrong channel is not a
# variant of the arm, it is a different experiment nobody approved.
ARM_CHANNEL = {"nopitch": ("linkedin", "N1", "an"), "joke": ("facebook", "J", "a"),
               "group": ("facebook_groups", "G1", "a")}
# messages.md: the N1 note is 3 to 5 sentences and 120 to 240 characters. The band is part of
# the arm, because the thing being measured is a SHORT no pitch card.
N1_BAND = (120, 240)


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


def common(text, ch, low, limit_key=None):
    """The checks every family gets, whatever it is."""
    reasons = []
    key = limit_key or ch
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


def check_nopitch(text, low):
    """N1: the note whose only job is the accept."""
    reasons = []
    if not CONTRACTION.search(text): reasons.append("no contraction: reads as machine written")
    if DARE in low: reasons.append("the dare is in an N1 note: that is the control, not this arm")
    if P1_LINE in low or P2_LINE in low: reasons.append("a pitch line in an N1 note")
    for c in NOPITCH_CLAIMS:
        if c in low: reasons.append(f"an offer in an N1 note: {c!r}. The pitch belongs in the follow up")
    if "24/7" in low: reasons.append("24/7 in an N1 note: the pitch belongs in the follow up")
    if not low.rstrip().endswith(N1_CLOSER): reasons.append(f"an N1 note ends on {N1_CLOSER!r}")
    if low.count("review") > 1: reasons.append("'review' more than once")
    if not N1_BAND[0] <= len(text) <= N1_BAND[1]:
        reasons.append(f"{len(text)} chars, the N1 band is {N1_BAND[0]} to {N1_BAND[1]}")
    sents = sentences(text)
    if not 3 <= len(sents) <= 5: reasons.append(f"{len(sents)} sentences, want 3 to 5")
    if re.search(r"\b\d+-month-old\b", low): reasons.append("N-month-old time reference")
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


def sent_prefix(note):
    """Read and validate the continuation marker. Returns (parts already sent, reasons).

    `sent_parts` is an assertion about what already left the keyboard on an earlier day, so
    it has to be a PREFIX of setup, punchline, ask in that order: there is no state in which
    a punchline went out and its setup did not. An all three marker leaves nothing to send.
    """
    raw = note.get("sent_parts")
    if raw is None:
        return [], []
    if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
        return [], [f"sent_parts must be a list of part names, got {raw!r}"]
    if list(raw) != list(J_PARTS[:len(raw)]):
        return [], [f"sent_parts must be a prefix of {list(J_PARTS)} in order, got {raw}"]
    if len(raw) >= len(J_PARTS):
        return list(raw), ["sent_parts says all three parts went out, so nothing is left to send"]
    return list(raw), []


def check_joke(text, low, var, part, note=None):
    """J1 and J2: fixed copy, three parts, no fact and no offer by design."""
    note = note or {}
    reasons = []
    js = note.get("joke_setup")
    if js is not None and str(js).strip() not in [s for s, _ in APPROVED_JOKES]:
        reasons.append("joke_setup is not one of the approved jokes in gold-notes.md")
    if part not in J_PARTS:
        return reasons + [f"a joke note needs part setup, punchline or ask, got {part!r}"]
    if re.search(r"\d", text): reasons.append("a digit: the joke arm carries no numbers at all")
    if DARE in low: reasons.append("the dare is in a joke note")
    if P1_LINE in low or P2_LINE in low: reasons.append("a pitch line in a joke note")
    if "24/7" in low: reasons.append("24/7 in a joke note")
    if part == "setup":
        if re.match(r"(?i)^\s*(hi|hey|hello|yo)\b", text):
            reasons.append("a greeting in the joke setup: the name arrives in the ask")
        if text.strip() not in [s for s, _ in APPROVED_JOKES]:
            reasons.append("the setup is not one of the approved jokes in gold-notes.md")
    elif part == "punchline":
        if text.strip() not in [p for _, p in APPROVED_JOKES]:
            reasons.append("the punchline is not one of the approved jokes in gold-notes.md")
    elif part == "ask":
        if not CONTRACTION.search(text): reasons.append("no contraction: reads as machine written")
        pattern = J_ASKS.get(var[-2:].upper())
        if pattern is None or not pattern.match(text.strip()):
            reasons.append(f"the ask does not match the fixed {var[-2:].upper()} ask")
    return reasons


def check(note):
    text = note["text"]; raw_ch = (note.get("channel") or "linkedin").lower()
    ch = note_channel(note); var = note.get("variant", "")
    low = text.lower()
    fam = family(var)
    lane = (var or "")[-2:].upper()
    reasons = common(text, ch, low, DM_LANES.get(lane) if ch == "linkedin" else None)
    if ch not in CHANNELS:
        reasons.append(f"unrecognised channel {raw_ch!r}: expected one of {sorted(CHANNELS)}")
    if fam is None:
        reasons.append(f"unrecognised variant family in {var!r}: expected P1, P2, N1, J1, J2, O1, I1 or G1")
        fam = "pitch"
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
    if fam != "joke" and (note.get("sent_parts") is not None or note.get("joke_setup") is not None):
        reasons.append("sent_parts or joke_setup on a note that is not a joke note")
    if fam == "pitch":
        reasons += check_pitch(text, low, var)
    elif fam == "nopitch":
        reasons += check_nopitch(text, low)
    elif fam == "joke":
        reasons += check_joke(text, low, var, note.get("part"), note)
    elif fam == "group":
        reasons += check_group(text, low)
    return reasons


def check_joke_sequences(notes):
    """A joke prospect is the sequence setup, punchline, ask, in that order, one note each,
    the setup and punchline from the SAME approved joke and the ask in this row's phrasing.

    A FRESH entry carries all three, unchanged from 2026-09-12. An entry whose earlier parts
    already went out on an earlier day is a CONTINUATION: it declares what was delivered in
    `sent_parts` and carries a contiguous run of what is left, starting at the next part.
    That is how SKILL.md Step 2b finishes an interrupted sequence under today's approval.
    Without the marker the lint demanded all three parts every session, which left exactly
    two ways to ship a continuation: strand the row, so the arm's 20 send count drifts, or
    pad the batch with text that already went out, which makes the lint stop checking the
    messages that are about to be typed. Added 2026-09-12 after the audit of 184db72.

    The marker is an assertion about `sent-log.csv`, not a fact this script can read, so a
    continuation must also name its joke in `joke_setup`: without it a punchline arriving a
    day after its setup could be paired with a different joke and nothing would notice.
    """
    reasons = []
    groups = {}
    for n in notes:
        if family(n.get("variant", "")) == "joke":
            groups.setdefault(n.get("entry"), []).append(n)
    setups_today = {}
    for entry, parts in sorted(groups.items(), key=lambda kv: str(kv[0])):
        got = [p.get("part") for p in parts]
        markers = sorted({json.dumps(p.get("sent_parts")) for p in parts})
        if len(markers) != 1:
            reasons.append(f"FAIL batch: joke entry {entry} disagrees with itself about sent_parts: {', '.join(markers)}")
            continue
        sent, bad = sent_prefix(parts[0])
        if bad:
            reasons.append(f"FAIL batch: joke entry {entry}: " + "; ".join(bad))
            continue
        # WHICH parts are present is the law: the whole remainder on a fresh entry, a
        # contiguous run from the next unsent part on a continuation, each exactly once. The
        # ORDER the notes are listed in is NOT a law, because the send order is a sending
        # rule (the batch runs in passes) and the 2026-09-12 fix must not fail a fresh entry
        # the 2026-09-09 lint passed.
        tail = list(J_PARTS[len(sent):])
        want = set(tail) if not sent else set(tail[:len(got)])
        dupes = sorted(x for x in set(got) if got.count(x) != 1)
        if not got or dupes or set(got) != want:
            if not sent:
                reasons.append(f"FAIL batch: joke entry {entry} needs exactly one setup, one punchline and one ask, got {got}")
            else:
                reasons.append(f"FAIL batch: joke entry {entry} already sent {sent}, so it carries {tail} from {tail[0]!r} on, one note each, got {got}")
            continue
        declared = sorted({(p.get("joke_setup") or "").strip() for p in parts})
        if len(declared) != 1:
            reasons.append(f"FAIL batch: joke entry {entry} disagrees with itself about joke_setup: {declared}")
            continue
        named = declared[0]
        setup = next((p["text"].strip() for p in parts if p.get("part") == "setup"), None)
        if sent and not named:
            reasons.append(f"FAIL batch: joke entry {entry} declares sent_parts {sent} and no joke_setup, so its punchline cannot be checked against its own setup")
            continue
        if setup is not None and named and named != setup:
            reasons.append(f"FAIL batch: joke entry {entry} joke_setup does not match the setup in this batch")
            continue
        opener = setup if setup is not None else named
        punch = next((p["text"].strip() for p in parts if p.get("part") == "punchline"), None)
        if punch is not None and (opener, punch) not in APPROVED_JOKES:
            reasons.append(f"FAIL batch: joke entry {entry} pairs a setup with the wrong punchline")
        if len({p.get("variant") for p in parts}) != 1:
            reasons.append(f"FAIL batch: joke entry {entry} mixes variant ids across its parts")
        # The repetition cap counts every ROW carrying this joke today, continuation included:
        # a continuation types that joke's punchline at a stranger today exactly like a fresh
        # row does, and counting only the setups left the whole continuation path uncapped
        # (10 continuation rows on one joke passed clean, found in the re audit of this fix).
        if opener:
            setups_today[opener] = setups_today.get(opener, 0) + 1
    for joke, n in sorted(setups_today.items()):
        if n > J_ROW_CAP:
            reasons.append(f"FAIL batch: the joke {joke!r} goes to {n} rows today, cap is {J_ROW_CAP} (templates/messages.md). Continuations count")
    return reasons


def diversity_failures(openers, label=None):
    """How many notes may open the same way: half the population, floor 2."""
    shapes = {}
    for n in openers: shapes.setdefault(shape(n["text"]), []).append(n.get("entry"))
    cap = max(2, -(-len(openers) // 2))
    where = f" on {label}" if label else ""
    out = [f"FAIL batch: {len(ents)} notes open the same way ({s!r}){where}: entries {ents}; cap is {cap}"
           for s, ents in shapes.items() if len(ents) > cap]
    return out, shapes


def main(path):
    notes = json.load(open(path))
    failed = 0
    for n in notes:
        r = check(n)
        tag = "PASS" if not r else "FAIL"
        failed += bool(r)
        part = f", {n['part']}" if n.get("part") else ""
        print(f"{tag} entry {n.get('entry')} ({n.get('channel')}, {n.get('variant')}{part}, {len(n['text'])} chars)" + ("" if not r else ": " + "; ".join(r)))
    for r in check_joke_sequences(notes):
        failed += 1; print(r)
    # Opener diversity is about how a first touch OPENS, so it reads the opener of each
    # prospect: the whole note on the control and the N1 arm, the setup on the joke arm. A
    # joke CONTINUATION opened on an earlier day, so it has no opener today and is not in
    # this population; what bounds a day of continuations is J_ROW_CAP above, which counts
    # them. Fewer openers only ever lowers the cap below, so this can never loosen it.
    openers = [n for n in notes if family(n.get("variant", "")) != "joke" or n.get("part") == "setup"]
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
    print(f"{'ALL PASS' if not failed else str(failed) + ' FAILURE(S)'}: {len(notes)} notes, {len(openers)} openers, {len(shapes)} opener shapes")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "notes.json")
