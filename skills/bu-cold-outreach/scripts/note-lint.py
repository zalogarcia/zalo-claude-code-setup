#!/usr/bin/env python3
"""Deterministic gate for cold DM notes (Zalo, 2026-09-09: "make sure we always get
messages that sound like texting a friend").

Input: a JSON file, a list of objects: {"entry": 3, "channel": "linkedin"|"facebook"|
"instagram", "variant": "C-li-P1", "text": "...", "part": "setup"|"punchline"|"ask"}.
`part` is required on the joke arm (J1, J2) and ignored everywhere else: the batch
diversity check keys on the variant family, not on the presence of that field, so a
stray `part` on a control note cannot drop it out of the count.
Output: one line per note, PASS or FAIL with every reason, then the batch level
checks. Exit 1 if anything failed. Facts are not checked here; the humanizer pass
and the approval do that. This catches the machine tells that slipped through
three times on 2026-09-09.

Three variant families, split out 2026-09-12 when the two test arms were added. The
family is read off the end of the variant id, and the laws that belong to one family
are not applied to another:

  P1, P2  the control. The four part message one. Dare required, fixed "what we do"
          line required, bridge required. Unchanged from 2026-09-09.
  N1      the LinkedIn note with no pitch. Dare and pitch line must be ABSENT, the
          note ends on the fixed permission question.
  J1, J2  the Facebook trade joke opener. Three parts per prospect, each an approved
          fixed string, no digits, no pitch, no dare.

Tests: python3 ~/.claude/skills/bu-cold-outreach/scripts/note-lint.test.py
"""
import json, re, sys

CONTRACTION = re.compile(r"(?i)\b\w+'s\s+(picking|running|live|on|not|going|been|still|already|just|coming|landing|doing|sitting|open|closed|out|in|at|the|a|an)\b|\b(that's|it's|you're|they're|we're|i'm|i've|you've|we've|there's|here's|what's|who's|somebody's|someone's|nobody's|ad's|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|can't|won't|wouldn't|couldn't|shouldn't|i'll|you'll|we'll|he's|she's|let's|you'd|i'd|we'd)\b")
BANNED = [
    "that is a person", "that is you", "that is your", "that is someone", "that is somebody",
    "caught my eye", "i noticed", "i came across", "hope you", "i hope", "reach out to you",
    "leverage", "streamline", "seamless", "solution", "cutting-edge", "game changer",
    "game-changer", "month-old", "i wanted to", "quick question", "just checking",
    "touching base", "circle back", "excited to", "passionate", "delighted", "kindly",
    "i would love", "i'd love to", "let me know if", "feel free", "don't hesitate",
    "website: answers",
]
DARE = "want to try and break it?"
P1_LINE = "trained a demo ai setter on your website"
P2_LINE = "built a quick demo off your website"
LIMITS = {"linkedin": 300, "facebook": 420, "instagram": 420}
LINK = re.compile(r"(?i)https?://|\bwww\.")
# Figure dash, en dash, em dash, horizontal bar, written as escapes so this file is
# itself free of the characters it bans.
DASH = re.compile("[\u2012\u2013\u2014\u2015]")

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
FAMILIES = {"P1": "pitch", "P2": "pitch", "N1": "nopitch", "J1": "joke", "J2": "joke"}


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
    if DASH.search(text): reasons.append("em or en dash")
    if len(text) > LIMITS.get(ch, 300): reasons.append(f"{len(text)} chars over the {ch} limit {LIMITS.get(ch, 300)}")
    for b in BANNED:
        if b in low: reasons.append(f"banned phrase: {b!r}")
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
    if re.search(r"\b\d+-month-old\b", low): reasons.append("N-month-old time reference")
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
    sents = sentences(text)
    if not 3 <= len(sents) <= 5: reasons.append(f"{len(sents)} sentences, want 3 to 5")
    if re.search(r"\b\d+-month-old\b", low): reasons.append("N-month-old time reference")
    return reasons


def check_joke(text, low, var, part):
    """J1 and J2: fixed copy, three parts, no fact and no offer by design."""
    reasons = []
    if part not in J_PARTS:
        return [f"a joke note needs part setup, punchline or ask, got {part!r}"]
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
    text = note["text"]; ch = note.get("channel", "linkedin").lower(); var = note.get("variant", "")
    low = text.lower()
    fam = family(var)
    reasons = common(text, ch, low)
    if fam is None:
        reasons.append(f"unrecognised variant family in {var!r}: expected P1, P2, N1, J1 or J2")
        fam = "pitch"
    if fam == "pitch":
        reasons += check_pitch(text, low, var)
    elif fam == "nopitch":
        reasons += check_nopitch(text, low)
    elif fam == "joke":
        reasons += check_joke(text, low, var, note.get("part"))
    return reasons


def check_joke_sequences(notes):
    """A joke prospect is three parts that belong together: one setup, one punchline from
    the SAME approved joke, and one ask in this row's phrasing."""
    reasons = []
    groups = {}
    for n in notes:
        if family(n.get("variant", "")) == "joke":
            groups.setdefault(n.get("entry"), []).append(n)
    for entry, parts in sorted(groups.items(), key=lambda kv: str(kv[0])):
        got = [p.get("part") for p in parts]
        missing = [p for p in J_PARTS if got.count(p) != 1]
        if missing:
            reasons.append(f"FAIL batch: joke entry {entry} needs exactly one setup, one punchline and one ask, got {got}")
            continue
        setup = next(p["text"].strip() for p in parts if p.get("part") == "setup")
        punch = next(p["text"].strip() for p in parts if p.get("part") == "punchline")
        if (setup, punch) not in APPROVED_JOKES:
            reasons.append(f"FAIL batch: joke entry {entry} pairs a setup with the wrong punchline")
        if len({p.get("variant") for p in parts}) != 1:
            reasons.append(f"FAIL batch: joke entry {entry} mixes variant ids across its parts")
    return reasons


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
    # prospect: the whole note on the control and the N1 arm, the setup on the joke arm.
    openers = [n for n in notes if family(n.get("variant", "")) != "joke" or n.get("part") == "setup"]
    shapes = {}
    for n in openers: shapes.setdefault(shape(n["text"]), []).append(n.get("entry"))
    cap = max(2, -(-len(openers) // 2))
    for s, ents in shapes.items():
        if len(ents) > cap:
            failed += 1; print(f"FAIL batch: {len(ents)} notes open the same way ({s!r}): entries {ents}; cap is {cap}")
    print(f"{'ALL PASS' if not failed else str(failed) + ' FAILURE(S)'}: {len(notes)} notes, {len(openers)} openers, {len(shapes)} opener shapes")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "notes.json")
