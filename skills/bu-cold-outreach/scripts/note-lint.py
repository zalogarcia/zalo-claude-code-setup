#!/usr/bin/env python3
"""Deterministic gate for cold DM notes (Zalo, 2026-09-09: "make sure we always get
messages that sound like texting a friend").

Input: a JSON file, a list of objects: {"entry": 3, "channel": "linkedin"|"facebook"|
"instagram", "variant": "C-li-P1", "text": "..."}.
Output: one line per note, PASS or FAIL with every reason, then the batch level
checks. Exit 1 if anything failed. Facts are not checked here; the humanizer pass
and the approval do that. This catches the machine tells that slipped through
three times on 2026-09-09.
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


def check(note):
    text = note["text"]; ch = note.get("channel", "linkedin").lower(); var = note.get("variant", "")
    low = text.lower(); reasons = []
    if re.search("[–—]", text): reasons.append("em or en dash")
    if len(text) > LIMITS.get(ch, 300): reasons.append(f"{len(text)} chars over the {ch} limit {LIMITS.get(ch, 300)}")
    if not CONTRACTION.search(text): reasons.append("no contraction: reads as machine written")
    for b in BANNED:
        if b in low: reasons.append(f"banned phrase: {b!r}")
    if DARE not in low: reasons.append("the dare is missing")
    if var.endswith("P1") and P1_LINE not in low: reasons.append("P1 row without the P1 line")
    if var.endswith("P2") and P2_LINE not in low: reasons.append("P2 row without the P2 line")
    if "!" in text: reasons.append("exclamation mark")
    if low.count("24/7") > 1: reasons.append("24/7 more than once")
    if low.count("review") > 1: reasons.append("'review' more than once")
    sents = sentences(text)
    if not 3 <= len(sents) <= 7: reasons.append(f"{len(sents)} sentences, want 3 to 7")
    pitch_idx = next((i for i, s in enumerate(sents) if P1_LINE in s.lower() or P2_LINE in s.lower()), None)
    if pitch_idx is None: reasons.append("no pitch sentence")
    elif pitch_idx < 2: reasons.append("no bridge: the pitch follows the fact with nothing in between")
    if re.search(r"\b\d+-month-old\b", low): reasons.append("N-month-old time reference")
    return reasons


def main(path):
    notes = json.load(open(path))
    failed = 0
    for n in notes:
        r = check(n)
        tag = "PASS" if not r else "FAIL"
        failed += bool(r)
        print(f"{tag} entry {n.get('entry')} ({n.get('channel')}, {n.get('variant')}, {len(n['text'])} chars)" + ("" if not r else ": " + "; ".join(r)))
    shapes = {}
    for n in notes: shapes.setdefault(shape(n["text"]), []).append(n.get("entry"))
    cap = max(2, -(-len(notes) // 2))
    for s, ents in shapes.items():
        if len(ents) > cap:
            failed += 1; print(f"FAIL batch: {len(ents)} notes open the same way ({s!r}): entries {ents}; cap is {cap}")
    print(f"{'ALL PASS' if not failed else str(failed) + ' FAILURE(S)'}: {len(notes)} notes, {len(shapes)} opener shapes")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "notes.json")
