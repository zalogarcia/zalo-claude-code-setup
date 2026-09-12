#!/usr/bin/env python3
"""Tests for note-lint.py. Run: python3 note-lint.test.py

Three jobs. One, the control family (P1, P2) still behaves exactly as it did on
2026-09-09: the approved gold notes pass and the returned rounds fail. Two, the two
arms added 2026-09-12 (N1, J1, J2) pass their own laws and fail the control's, which
is the whole reason the families exist. Three, nothing can ship without a family.

The block at the bottom is the audit of 184db72 (2026-09-12) and the re audit of that fix:
the continuation marker, the joke row cap, the channel and family lock, and the N1 length
band. It adds 32 cases. **25 of the 32 are not satisfied by the pre fix script** (17 fail its
own assertion outright; 8 more reach the right exit code for the WRONG reason, because the
old lint rejected every continuation, and their message assertion catches that). The other 7
are regression guards that were green before the fix and have to stay green: "an ask alone
with NO marker still fails", "joke parts listed out of send order in a fresh entry still
pass", "a duplicated part in a fresh entry fails", "four rows each on two jokes is at the cap
and passes", "the control still runs on facebook", "the control still runs on linkedin", "an
N1 note inside the band still passes".

Measure it, do not take the count on trust: copy this file next to
`git show HEAD:skills/bu-cold-outreach/scripts/note-lint.py` in a scratch directory, run it,
and read the failure list (34 failure lines over 23 distinct case names plus 11 message
assertions at the time of writing).
"""
import importlib.util, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("notelint", os.path.join(HERE, "note-lint.py"))
lint = importlib.util.module_from_spec(spec); spec.loader.exec_module(lint)

FAILURES = []
COUNT = 0


def case(name, note, want_ok, want_reason=None):
    """want_ok True means no reasons at all. want_reason is a substring that must appear."""
    global COUNT
    COUNT += 1
    got = lint.check(note)
    ok = not got
    if ok != want_ok:
        FAILURES.append(f"{name}: expected {'PASS' if want_ok else 'FAIL'}, got {got or 'PASS'}")
    elif want_reason and not any(want_reason in r for r in got):
        FAILURES.append(f"{name}: expected a reason containing {want_reason!r}, got {got}")


def batch_case(name, notes, want_exit):
    global COUNT
    COUNT += 1
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(notes, f); path = f.name
    r = subprocess.run([sys.executable, os.path.join(HERE, "note-lint.py"), path],
                       capture_output=True, text=True)
    os.unlink(path)
    if r.returncode != want_exit:
        FAILURES.append(f"{name}: expected exit {want_exit}, got {r.returncode}\n{r.stdout}")
    return r.stdout


def li(text, variant="C-li-P1", entry=1):
    return {"entry": entry, "channel": "linkedin", "variant": variant, "text": text}


def fb(text, variant="D-fb-P1", entry=1, part=None, sent_parts=None, joke_setup=None):
    n = {"entry": entry, "channel": "facebook", "variant": variant, "text": text}
    if part: n["part"] = part
    if sent_parts is not None: n["sent_parts"] = sent_parts
    if joke_setup is not None: n["joke_setup"] = joke_setup
    return n


def jrow(entry, joke_index=0, variant="D-fb-J1", name="Mike"):
    """A whole fresh joke prospect: setup, punchline, ask, all three approved and paired."""
    s, p = lint.APPROVED_JOKES[joke_index]
    ask = (f"Alright {name}, real question and then I'll leave the jokes alone. Would you be "
           "open to talking about the calls that come in after you close?")
    return [fb(s, variant, entry=entry, part="setup"),
            fb(p, variant, entry=entry, part="punchline"),
            fb(ask, variant, entry=entry, part="ask")]


# ---------------------------------------------------------------- the control, P1 and P2
GOLD_LI = [
    ("Hi Chris, saw Jennifer's review from June. You reached out to her yourself, almost "
     "immediately. So you're the one on the phone. I trained a demo AI setter on your "
     "website that takes those calls 24/7 and books the job. Want to try and break it?", "C-li-P1"),
    ("Hi Sharon, Nate's review says Lloyd called him back on a Saturday and walked him "
     "through the repair by text. That's Lloyd doing it by hand on his weekend. I trained a "
     "demo AI setter on your website that takes those calls 24/7 and books the job. Want to "
     "try and break it?", "D-li-P1"),
    ("Hi Jonathan, Paula's review says you were fast on her Saturday AC call. And your "
     "Facebook ad's running right now, so more of those are coming. I trained a demo AI "
     "setter on your website that answers them 24/7 and books the job. Want to try and "
     "break it?", "C-li-P1"),
    ("Hi Maria, saw Amber's review: after-hours repair, then somebody on your team called "
     "hours later to check in. That's a person doing the follow-up by hand. I built a quick "
     "demo off your website: it picks up when nobody can, day or night, and books the job. "
     "Want to try and break it?", "D-li-P2"),
    ("Hi John, Clay's review from July says he called after hours and Charles came out past "
     "10pm. So somebody at AAction's picking up at 10 at night. I trained a demo AI setter "
     "on your website that takes those calls 24/7 and books the job. Want to try and break "
     "it?", "C-li-P1"),
    ("Hi Alex, Svetlana's review says she called at 9 pm and you had it fixed the next day. "
     "Your Facebook ad's live too, so the 9 pm calls keep coming. I built a quick demo off "
     "your website: it picks up when nobody can, day or night, and books the job. Want to "
     "try and break it?", "C-li-P2"),
]
for i, (text, var) in enumerate(GOLD_LI):
    case(f"gold LinkedIn note {i + 1} passes", li(text, var, entry=i + 1), True)

GOLD_FB = [
    ("Hey Geo, saw Briana's review from last month: called Prestige, had a quote the same "
     "day. Somebody's picking up fast over there.\n\nI trained a demo AI setter on your "
     "website. It answers your calls and texts in about five seconds, 24/7, and books the "
     "job straight into your calendar. Want to try and break it? Call it, text it, throw it "
     "your weirdest customer.", "D-fb-P1"),
    ("Hey Albert and Janet, saw you're hiring an HVAC Office Manager, and Google has the "
     "office at 8 to 4 weekdays, closed weekends. So every call after 4 is landing "
     "somewhere.\n\nI trained a demo AI setter on your website: it answers calls and texts "
     "in about five seconds, 24/7, and books the job straight into your calendar. Want to "
     "try and break it? Call it, text it, throw it your weirdest customer.", "A-fb-P1"),
]
for i, (text, var) in enumerate(GOLD_FB):
    case(f"gold Facebook note {i + 1} passes", fb(text, var, entry=7 + i), True)

case("the generic note returned on 2026-09-09 still fails",
     li("Hi John, saw Atlanta AAction Air's June 2 Facebook ads. I went ahead and trained a "
        "demo AI setter on your website. It answers your calls and texts in about five "
        "seconds, 24/7, and books the job straight into your calendar. Want me to send it "
        "over?"), False, "the dare is missing")
case("the robotic note returned on 2026-09-09 still fails",
     li('Hi John, Clay\'s 2-month-old review says he called after hours and "Charles came '
        'out after 10pm" to fix his AC. I trained a demo AI setter on your website: answers '
        'calls and texts in about five seconds, 24/7, books the job into your calendar. '
        'Want to try and break it?'), False, "N-month-old")
case("a P1 row without the P1 line fails",
     li("Hi Mike, Dana's review from July says she waited two days. That's the call this "
        "catches. I built a quick demo off your website: it picks up when nobody can. Want "
        "to try and break it?", "C-li-P1"), False, "P1 row without the P1 line")
case("an em dash still fails",
     li("Hi Chris, saw Jennifer's review from June \u2014 you called her back yourself. So "
        "you're the one on the phone. I trained a demo AI setter on your website that takes "
        "those calls 24/7 and books the job. Want to try and break it?"), False, "em or en dash")

# -------------------------------------------------------------------- the N1 arm, no pitch
N1_A = ("Hi Mike, Dana's review from July says she left two messages before anyone called "
        "her back. That's the call this catches. Mind if I ask you something about it?")
N1_B = ("Hi Rachel, Google has the office closed Sundays and your site's promising emergency "
        "service any time. So somebody's phone is buzzing on a Sunday. Mind if I ask you "
        "something about it?")
case("N1 note A passes", li(N1_A, "D-li-N1"), True)
case("N1 note B passes", li(N1_B, "D-li-N1", entry=2), True)
case("the reserved C-li-N1 id lints the same way", li(N1_A, "C-li-N1"), True)
case("an N1 note carrying the dare fails",
     li("Hi Mike, Dana's review from July says she waited. That's the call this catches. "
        "Want to try and break it?", "D-li-N1"), False, "the dare is in an N1 note")
case("an N1 note carrying the pitch line fails",
     li("Hi Mike, Dana's review from July says she waited two days for a call back. I "
        "trained a demo AI setter on your website. Mind if I ask you something about it?",
        "D-li-N1"), False, "a pitch line in an N1 note")
case("an N1 note with a drifting closer fails",
     li("Hi Mike, Dana's review from July says she left two messages before anyone called "
        "her back. That's the call this catches. Can I ask you a thing?", "D-li-N1"),
     False, "an N1 note ends on")
case("an N1 note with no contraction fails",
     li("Hi Mike, Dana left two messages in July before anyone called her back. That is the "
        "call this catches. Mind if I ask you something about it?", "D-li-N1"),
     False, "no contraction")
case("an N1 note is still held to 300 characters",
     li("Hi Mike, " + "Dana's review from July says she left two messages before anyone "
        "called her back and the same thing happened to her neighbour twice that week. " * 2
        + "That's the call this catches. Mind if I ask you something about it?", "D-li-N1"),
     False, "over the linkedin limit")

# ------------------------------------------------------------------- the J arm, trade joke
SETUP, PUNCH = lint.APPROVED_JOKES[0]
ASK1 = ("Alright Mike, real question and then I'll leave the jokes alone. Would you be open "
        "to talking about the calls that come in after you close?")
ASK2 = ("Okay Mike, that's my one joke of the day. Mind if I ask you something about the "
        "calls that come in after you close?")
case("an approved joke setup passes", fb(SETUP, "D-fb-J1", part="setup"), True)
case("an approved punchline passes", fb(PUNCH, "D-fb-J1", part="punchline"), True)
case("the J1 ask passes", fb(ASK1, "D-fb-J1", part="ask"), True)
case("the J2 ask passes", fb(ASK2, "D-fb-J2", part="ask"), True)
case("every approved joke in gold-notes.md lints clean",
     fb(lint.APPROVED_JOKES[4][1], "D-fb-J2", part="punchline"), True)
case("a joke note with no part fails", fb(SETUP, "D-fb-J1"), False, "needs part")
case("an unapproved setup fails",
     fb("Why did the HVAC guy cross the road?", "D-fb-J1", part="setup"),
     False, "not one of the approved jokes")
case("a greeting in the setup fails",
     fb("Hey Mike, why don't ducts keep secrets?", "D-fb-J1", part="setup"),
     False, "a greeting in the joke setup")
case("a digit in a joke note fails",
     fb("Only 1 with a degree.", "D-fb-J1", part="punchline"), False, "a digit")
case("the J1 ask on a J2 row fails",
     fb(ASK1, "D-fb-J2", part="ask"), False, "does not match the fixed J2 ask")
case("an ask carrying the pitch fails",
     fb("Alright Mike, I trained a demo AI setter on your website. Would you be open to "
        "talking about the calls that come in after you close?", "D-fb-J1", part="ask"),
     False, "a pitch line in a joke note")

case("an N1 note carrying a paraphrased pitch fails",
     li("Hi Mike, Dana's review from July says she left two messages before anyone called "
        "her back. I've got something that picks up your phones and books the job. Mind if "
        "I ask you something about it?", "D-li-N1"), False, "an offer in an N1 note")
case("an N1 note whose specific carries a time and a shift still passes",
     li("Hi Dale, Google has you at 8 to 5 weekdays and Nina's review says she called at 9 "
        "pm. So that's a call landing somewhere. Mind if I ask you something about it?",
        "D-li-N1"), True)
case("an N1 bridge about a person picking up is not read as an offer",
     li("Hi Sam, Nate's review says Lloyd called him back on a Saturday. So somebody's "
        "picking up at the weekend. Mind if I ask you something about it?", "D-li-N1"), True)

# ------------------------------------------------------------------------- family plumbing
case("an unrecognised variant family fails loudly",
     li("Hi Chris, saw Jennifer's review from June. You reached out to her yourself. So "
        "you're the one on the phone. I trained a demo AI setter on your website that takes "
        "those calls 24/7 and books the job. Want to try and break it?", "C-li-P9"),
     False, "unrecognised variant family")
case("an empty variant fails loudly", li(N1_A, ""), False, "unrecognised variant family")
case("a link fails on any family", li(N1_A[:-1] + " https://blackumbrella.app?", "D-li-N1"),
     False, "a link")
case("an unfilled token fails",
     li("Hi [First], Dana's review from July says she left two messages before anyone "
        "called her back. That's the call this catches. Mind if I ask you something about "
        "it?", "D-li-N1"), False, "an unfilled token")

# ------------------------------------------------------------------------- batch level
full_batch = ([li(t, v, entry=i + 1) for i, (t, v) in enumerate(GOLD_LI)]
              + [fb(t, v, entry=7 + i) for i, (t, v) in enumerate(GOLD_FB)]
              + [li(N1_A, "D-li-N1", entry=9), li(N1_B, "D-li-N1", entry=10)]
              + [fb(SETUP, "D-fb-J1", entry=11, part="setup"),
                 fb(PUNCH, "D-fb-J1", entry=11, part="punchline"),
                 fb(ASK1, "D-fb-J1", entry=11, part="ask")])
out = batch_case("a mixed batch of control, N1 and J notes is ALL PASS", full_batch, 0)
if "ALL PASS" not in out:
    FAILURES.append(f"mixed batch: expected ALL PASS in output, got:\n{out}")

out = batch_case("a joke entry missing its ask fails the batch",
                 [fb(SETUP, "D-fb-J1", entry=11, part="setup"),
                  fb(PUNCH, "D-fb-J1", entry=11, part="punchline")], 1)
if "needs exactly one setup" not in out:
    FAILURES.append(f"incomplete joke sequence: wrong message:\n{out}")

out = batch_case("a punchline from a different joke fails the batch",
                 [fb(SETUP, "D-fb-J1", entry=11, part="setup"),
                  fb(lint.APPROVED_JOKES[3][1], "D-fb-J1", entry=11, part="punchline"),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask")], 1)
if "wrong punchline" not in out:
    FAILURES.append(f"mismatched punchline: wrong message:\n{out}")

same = ("Hi {n}, {r}'s review says he called after hours and somebody came out past 10pm. "
        "So you're picking up at night. I trained a demo AI setter on your website that "
        "takes those calls 24/7 and books the job. Want to try and break it?")
out = batch_case("three identical openers in a batch of four still trip the diversity cap",
                 [li(same.format(n=n, r=r), "C-li-P1", entry=i + 1) for i, (n, r) in
                  enumerate([("Al", "Clay"), ("Bo", "Dana"), ("Cy", "Eve")])]
                 + [li(N1_B, "D-li-N1", entry=4)], 1)
if "open the same way" not in out:
    FAILURES.append(f"diversity cap: wrong message:\n{out}")

out = batch_case("joke parts do not inflate the diversity denominator",
                 [li(same.format(n="Al", r="Clay"), "C-li-P1", entry=1),
                  li(same.format(n="Bo", r="Dana"), "C-li-P1", entry=2),
                  li(same.format(n="Cy", r="Eve"), "C-li-P1", entry=3),
                  fb(SETUP, "D-fb-J1", entry=4, part="setup"),
                  fb(PUNCH, "D-fb-J1", entry=4, part="punchline"),
                  fb(ASK1, "D-fb-J1", entry=4, part="ask")], 1)
if "open the same way" not in out:
    FAILURES.append(f"diversity with joke parts: expected the cap to trip on 3 of 4 openers:\n{out}")

same_ask = [dict(li(same.format(n=n, r=r), "C-li-P1", entry=i + 1), part="ask")
            for i, (n, r) in enumerate([("Al", "Clay"), ("Bo", "Dana"), ("Cy", "Eve"), ("Di", "Fay")])]
out = batch_case("a stray part field on control notes cannot dodge the diversity check",
                 same_ask, 1)
if "open the same way" not in out:
    FAILURES.append(f"part field dodge: the diversity check was skipped:\n{out}")

# ------------------------------------------------------- the audit of 184db72, 2026-09-12
# 1. The continuation marker. A sequence interrupted by the daily cap or by a session ending
# is finished in a LATER batch under that day's approval (SKILL.md Step 2b). Before the
# marker the lint demanded all three parts every session, so the only ways to ship a
# continuation were to strand the row or to pad the batch with text that already went out.
CONT_SETUP, CONT_PUNCH = lint.APPROVED_JOKES[0]

out = batch_case("a continuation carrying only the ask passes",
                 [fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup", "punchline"], joke_setup=CONT_SETUP)], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"ask only continuation: expected ALL PASS, got:\n{out}")

out = batch_case("a continuation carrying only the punchline passes",
                 [fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline",
                     sent_parts=["setup"], joke_setup=CONT_SETUP)], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"punchline only continuation: expected ALL PASS, got:\n{out}")

out = batch_case("a continuation carrying the punchline and the ask passes",
                 [fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline",
                     sent_parts=["setup"], joke_setup=CONT_SETUP),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup"], joke_setup=CONT_SETUP)], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"punchline plus ask continuation: expected ALL PASS, got:\n{out}")

out = batch_case("an ask alone with NO marker still fails",
                 [fb(ASK1, "D-fb-J1", entry=11, part="ask")], 1)
if "needs exactly one setup" not in out:
    FAILURES.append(f"unmarked ask only: wrong message:\n{out}")

out = batch_case("a continuation that skips the punchline fails",
                 [fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup"], joke_setup=CONT_SETUP)], 1)
if "from 'punchline' on" not in out:
    FAILURES.append(f"skipped punchline: wrong message:\n{out}")

out = batch_case("a continuation punchline from a different joke fails",
                 [fb(lint.APPROVED_JOKES[3][1], "D-fb-J1", entry=11, part="punchline",
                     sent_parts=["setup"], joke_setup=CONT_SETUP)], 1)
if "wrong punchline" not in out:
    FAILURES.append(f"cross joke continuation: wrong message:\n{out}")

out = batch_case("a continuation with no joke_setup fails",
                 [fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline",
                     sent_parts=["setup"])], 1)
if "no joke_setup" not in out:
    FAILURES.append(f"continuation without joke_setup: wrong message:\n{out}")

out = batch_case("sent_parts that is not a prefix of the sequence fails",
                 [fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["punchline"], joke_setup=CONT_SETUP)], 1)
if "must be a prefix" not in out:
    FAILURES.append(f"non prefix marker: wrong message:\n{out}")

out = batch_case("a marker claiming all three parts went out fails",
                 [fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup", "punchline", "ask"], joke_setup=CONT_SETUP)], 1)
if "nothing is left to send" not in out:
    FAILURES.append(f"exhausted marker: wrong message:\n{out}")

out = batch_case("two notes of one entry disagreeing about sent_parts fails",
                 [fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline",
                     sent_parts=["setup"], joke_setup=CONT_SETUP),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup", "punchline"], joke_setup=CONT_SETUP)], 1)
if "disagrees with itself about sent_parts" not in out:
    FAILURES.append(f"inconsistent marker: wrong message:\n{out}")

out = batch_case("a fresh entry whose joke_setup contradicts its own setup fails",
                 [fb(CONT_SETUP, "D-fb-J1", entry=11, part="setup",
                     joke_setup=lint.APPROVED_JOKES[3][0]),
                  fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline",
                     joke_setup=lint.APPROVED_JOKES[3][0]),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     joke_setup=lint.APPROVED_JOKES[3][0])], 1)
if "does not match the setup in this batch" not in out:
    FAILURES.append(f"contradictory joke_setup: wrong message:\n{out}")

# Regression guard, green before the fix and after it: the ORDER the notes are listed in is
# not a law, only which parts are present. The send order is a sending rule (the batch runs
# in passes), and the first cut of this fix failed 5 of the 6 orderings of a valid triple.
out = batch_case("joke parts listed out of send order in a fresh entry still pass",
                 [fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline"),
                  fb(CONT_SETUP, "D-fb-J1", entry=11, part="setup"),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask")], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"out of order parts: expected ALL PASS, got:\n{out}")

out = batch_case("a duplicated part in a fresh entry fails",
                 [fb(CONT_SETUP, "D-fb-J1", entry=11, part="setup"),
                  fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline"),
                  fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline"),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask")], 1)
if "needs exactly one setup" not in out:
    FAILURES.append(f"duplicated part: wrong message:\n{out}")

out = batch_case("a continuation listing its two parts out of order still passes",
                 [fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup"], joke_setup=CONT_SETUP),
                  fb(CONT_PUNCH, "D-fb-J1", entry=11, part="punchline",
                     sent_parts=["setup"], joke_setup=CONT_SETUP)], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"out of order continuation: expected ALL PASS, got:\n{out}")

case("joke_setup naming a joke nobody approved fails",
     fb(ASK1, "D-fb-J1", part="ask", sent_parts=["setup", "punchline"],
        joke_setup="Why did the HVAC guy cross the road?"),
     False, "joke_setup is not one of the approved jokes")
case("a continuation marker on a control note fails",
     dict(li(GOLD_LI[0][0], "C-li-P1"), sent_parts=["setup"]),
     False, "not a joke note")
case("a joke_setup on an N1 note fails",
     dict(li(N1_A, "D-li-N1"), joke_setup=lint.APPROVED_JOKES[0][0]),
     False, "not a joke note")

# 2. The joke row cap. "No joke goes to more than 4 rows in one day" was prose only: the
# generic opener cap permits 5 of 10 identical, so 10 rows on two jokes passed clean.
cap_ok = (jrow(1, 0, name="Al") + jrow(2, 0, name="Bo") + jrow(3, 0, name="Cy")
          + jrow(4, 0, name="Di") + jrow(5, 3, name="Ed") + jrow(6, 3, name="Fi")
          + jrow(7, 3, name="Gus") + jrow(8, 3, name="Hal"))
out = batch_case("four rows each on two jokes is at the cap and passes", cap_ok, 0)
if "ALL PASS" not in out:
    FAILURES.append(f"joke cap boundary: expected ALL PASS, got:\n{out}")

cap_trip = cap_ok + jrow(9, 0, name="Ira") + jrow(10, 3, name="Jo")
out = batch_case("five rows on one joke trips the joke row cap", cap_trip, 1)
if "cap is 4" not in out:
    FAILURES.append(f"joke row cap: wrong message:\n{out}")

# A continuation types that joke's punchline at a stranger today exactly like a fresh row
# does, so it counts against the cap. Counting only setups left the whole continuation path
# uncapped: 10 continuation rows on one joke passed clean (re audit of this fix, 2026-09-12).
cont_row = [fb(CONT_PUNCH, "D-fb-J1", entry=9, part="punchline",
               sent_parts=["setup"], joke_setup=CONT_SETUP)]
out = batch_case("a continuation is the fifth row on its joke and trips the cap",
                 cap_ok + cont_row, 1)
if "cap is 4" not in out:
    FAILURES.append(f"continuation not counted against the cap:\n{out}")

ten_conts = []
for i, n in enumerate(["Al", "Bo", "Cy", "Di", "Ed", "Fi", "Gus", "Hal", "Ira", "Jo"]):
    ask = (f"Alright {n}, real question and then I'll leave the jokes alone. Would you be "
           "open to talking about the calls that come in after you close?")
    ten_conts += [fb(CONT_PUNCH, "D-fb-J1", entry=20 + i, part="punchline",
                     sent_parts=["setup"], joke_setup=CONT_SETUP),
                  fb(ask, "D-fb-J1", entry=20 + i, part="ask",
                     sent_parts=["setup"], joke_setup=CONT_SETUP)]
out = batch_case("ten continuations on one joke trip the cap", ten_conts, 1)
if "cap is 4" not in out:
    FAILURES.append(f"ten continuations on one joke: wrong message:\n{out}")

out = batch_case("three continuations on one joke are under the cap and pass",
                 ten_conts[:6], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"three continuations: expected ALL PASS, got:\n{out}")

out = batch_case("a fresh row plus three continuations of the same joke is at the cap",
                 jrow(30, 0, name="Ken") + ten_conts[:6], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"fresh plus three continuations: expected ALL PASS, got:\n{out}")

# 3. Channel and family lock. Both test arms are one channel each.
case("an N1 note on facebook fails", fb(N1_A, "D-fb-N1"),
     False, "the N1 arm is linkedin only")
case("a joke setup on linkedin fails",
     {"entry": 1, "channel": "linkedin", "variant": "D-li-J1", "part": "setup",
      "text": CONT_SETUP}, False, "the J arm is facebook only")
case("a joke ask on linkedin fails",
     {"entry": 1, "channel": "linkedin", "variant": "D-li-J1", "part": "ask",
      "text": ASK1}, False, "the J arm is facebook only")
case("the control still runs on facebook", fb(GOLD_FB[0][0], "D-fb-P1"), True)
case("the control still runs on linkedin", li(GOLD_LI[0][0], "C-li-P1"), True)

out = batch_case("a J triple on linkedin fails the batch",
                 [{"entry": 1, "channel": "linkedin", "variant": "D-li-J1",
                   "part": p, "text": t} for p, t in
                  [("setup", CONT_SETUP), ("punchline", CONT_PUNCH), ("ask", ASK1)]], 1)
if "the J arm is facebook only" not in out:
    FAILURES.append(f"J on linkedin batch: wrong message:\n{out}")

# 4. The N1 length band, 120 to 240 per templates/messages.md.
LONG_N1 = ("Hi Mike, Dana's review from July says she left two messages before anyone called "
           "her back, and her neighbour had the same wait the same week on a Sunday night in "
           "the middle of a heat wave. That's the call this catches every time. Mind if I ask "
           "you something about it?")
case("an N1 note over the band fails, under the 300 character channel limit",
     li(LONG_N1, "D-li-N1"), False, "the N1 band is 120 to 240")
case("an N1 note under the band fails",
     li("Hi Mike, Dana waited two days. That's the call. Mind if I ask you something about "
        "it?", "D-li-N1"), False, "the N1 band is 120 to 240")
case("an N1 note inside the band still passes", li(N1_A, "D-li-N1"), True)

print(f"{COUNT} cases")
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES: print("  " + f)
    sys.exit(1)
print("ALL PASS")
