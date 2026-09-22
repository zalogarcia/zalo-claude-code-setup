#!/usr/bin/env python3
"""Tests for note-lint.py. Run: python3 note-lint.test.py

Four jobs. One, the control family (P1, P2) still behaves exactly as it did on
2026-09-09: the approved gold notes pass and the returned rounds fail. Two, the test arms
pass their own laws and fail the control's. Three, nothing can ship without a family. Four,
added 2026-09-22 and the reason this file was restructured: the ONE MESSAGE rule (Zalo,
2026-09-22, "we should not send 4 messages with no reply... needs to be a single cold
message"; option A for LinkedIn the same evening, connection requests carry no note).

What 2026-09-22 retired, and what replaced the tests that covered it:

- The joke arm's three bubbles (setup, punchline, ask) and the continuation marker that
  finished them in a later batch (`sent_parts`, `joke_setup`). The 2026-09-12 audit block
  proved that machinery worked; it now proves the machinery is REFUSED: a `part`,
  `sent_parts` or `joke_setup` field fails on sight, two notes on one entry fail the batch,
  and the joke is one message, setup then punchline then the fixed ask, on one line.
- The N1 arm (the LinkedIn connection note with no pitch) and the 300 character invitation
  note. A connection request carries no note now, so N1 fails as retired, a `connect` entry
  with any text fails, and every LinkedIn text is a delivered message held to 420.
- Bumps. A kind other than message or connect, a stage of BUMP1, BUMP2 or SENT_CONT, and the
  follow up phrases ("last one from me") all fail.

The history half of the rule (a second message to a prospect who has not replied, on any
channel) needs pipeline.csv and sent-log.csv, so `batch_case` builds a throwaway working
folder for every batch it lints, and the fixture folder `fixtures/single-message/` holds a
hand made passing batch and a hand made refusing batch against a small pipeline and log.
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "note-lint.py")
spec = importlib.util.spec_from_file_location("notelint", LINT)
lint = importlib.util.module_from_spec(spec); spec.loader.exec_module(lint)

FAILURES = []
COUNT = 0
PIPE_HEAD = ("prospect_id,business_name,metro,tier,channel,profile_url,owner_name,stage,"
             "last_touch,next_due,angle,side_note,demo_link,demo_views_last,touches,notes")
LOG_HEAD = ("timestamp_et,channel,prospect_id,profile_url,stage,message_sha1,message_head,"
            "variant,opener_type,message_text")


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


def run_lint(args):
    r = subprocess.run([sys.executable, LINT] + args, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def working_folder(pipeline=(), log=(), known=()):
    """A throwaway working folder: pipeline.csv and sent-log.csv with the given rows,
    prospects.csv holding every pipeline id plus `known`, and the evidence/<day>/session-1/
    directory a real notes.json lives in."""
    root = tempfile.mkdtemp(prefix="bu-lint-")
    with open(os.path.join(root, "pipeline.csv"), "w") as f:
        f.write("\n".join([PIPE_HEAD] + list(pipeline)) + "\n")
    with open(os.path.join(root, "sent-log.csv"), "w") as f:
        f.write("\n".join([LOG_HEAD] + list(log)) + "\n")
    ids = [row.split(",")[0] for row in pipeline] + [str(k) for k in known]
    with open(os.path.join(root, "prospects.csv"), "w") as f:
        f.write("\n".join(["prospect_id,metro"] + [f"{i},Miami" for i in ids]) + "\n")
    ev = os.path.join(root, "evidence", "2026-09-23", "session-1")
    os.makedirs(ev)
    return root, ev


def batch_case(name, notes, want_exit, pipeline=(), log=(), autofill=True, extra=(), known=None):
    """Lint a whole batch as the gate does: inside a working folder, history on. `autofill`
    gives every note without a prospect_id its own id per entry (p<entry>), so the copy
    batches below exercise the full gate without every one of them naming prospects. Every id
    in the batch is written to prospects.csv unless `known` names the ids that exist."""
    global COUNT
    COUNT += 1
    if autofill:
        notes = [dict(n, prospect_id=n.get("prospect_id") or f"p{n.get('entry')}")
                 if lint.family(n.get("variant", "")) != "group" else n for n in notes]
    if known is None:
        known = [n.get("prospect_id") for n in notes if n.get("prospect_id")]
    root, ev = working_folder(pipeline, log, known)
    path = os.path.join(ev, "notes.json")
    with open(path, "w") as f:
        json.dump(notes, f)
    code, out = run_lint([path] + list(extra))
    shutil.rmtree(root)
    if code != want_exit:
        FAILURES.append(f"{name}: expected exit {want_exit}, got {code}\n{out}")
    return out


def li(text, variant="C-li-P1", entry=1, **extra):
    return dict({"entry": entry, "channel": "linkedin", "variant": variant, "text": text}, **extra)


def fb(text, variant="D-fb-P1", entry=1, **extra):
    return dict({"entry": entry, "channel": "facebook", "variant": variant, "text": text}, **extra)


def jtext(joke_index=0, arm="J1", name="Mike"):
    """One whole joke message: the approved setup, the punchline, then the fixed ask."""
    s, p = lint.APPROVED_JOKES[joke_index]
    if arm == "J1":
        ask = (f"Alright {name}, real question and then I'll leave the jokes alone. Would you "
               "be open to talking about the calls that come in after you close?")
    else:
        ask = (f"Okay {name}, that's my one joke of the day. Mind if I ask you something about "
               "the calls that come in after you close?")
    return f"{s} {p} {ask}"


def jrow(entry, joke_index=0, variant="D-fb-J1", name="Mike"):
    """A whole joke prospect: ONE note since 2026-09-22."""
    return [fb(jtext(joke_index, variant[-2:], name), variant, entry=entry)]


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

# ------------------------------------------------------ N1 is retired (2026-09-22, option A)
# The two notes Zalo read on 2026-09-12. A connection request carries no note now, so the arm
# has nothing left to measure, and both notes fail as retired on any channel.
N1_A = ("Hi Mike, Dana's review from July says she left two messages before anyone called "
        "her back. That's the call this catches. Mind if I ask you something about it?")
N1_B = ("Hi Rachel, Google has the office closed Sundays and your site's promising emergency "
        "service any time. So somebody's phone is buzzing on a Sunday. Mind if I ask you "
        "something about it?")
case("N1 note A now fails as retired", li(N1_A, "D-li-N1"), False, "N1 was retired 2026-09-22")
case("N1 note B now fails as retired", li(N1_B, "D-li-N1", entry=2), False, "N1 was retired")
case("the reserved C-li-N1 id fails as retired too", li(N1_A, "C-li-N1"), False, "retired")
case("an N1 id on facebook fails as retired", fb(N1_A, "D-fb-N1"), False, "retired")

# ------------------------------------------ the LinkedIn delivered lanes, O1 and I1 (2026-09-12)
# An open profile message or an InMail is a DM and carries the control shape. Since 2026-09-22
# so is the one message after an accepted connection (P1 or P2), and all three take 420.
DM_O1 = ("Hi Mike, Dana's July review says she left two messages before anyone called her back. "
         "Missed calls are the one thing an HVAC shop can't see on its own dashboard.\n\n"
         "I trained a demo AI setter on your website: it answers calls and texts in about five "
         "seconds, 24/7, and books the job straight into your calendar. Want to try and break "
         "it? Call it, text it, throw it your weirdest customer.")
case("an O1 open profile DM under 420 passes on linkedin", li(DM_O1, "D-li-O1"), True)
case("an I1 InMail under 420 passes on linkedin", li(DM_O1, "A-li-I1"), True)
case("the same text as the P1 message after the accept passes: LinkedIn is 420 now",
     li(DM_O1, "D-li-P1"), True)
case("an O1 id on facebook fails the lane lock",
     fb(DM_O1, "D-fb-O1"), False, "the O1 lane is linkedin only")
case("a LinkedIn message over 420 fails",
     li(DM_O1.replace("Call it, text it,", "Call it, text it, ring it twice at midnight, "
                      "text it from the truck, call it from a roof, then call it again,"), "D-li-P1"),
     False, "over the linkedin limit 420")

# ------------------------------------------ the J arm, trade joke, ONE message (2026-09-22)
SETUP, PUNCH = lint.APPROVED_JOKES[0]
ASK1 = ("Alright Mike, real question and then I'll leave the jokes alone. Would you be open "
        "to talking about the calls that come in after you close?")
ASK2 = ("Okay Mike, that's my one joke of the day. Mind if I ask you something about the "
        "calls that come in after you close?")
J1_MSG = f"{SETUP} {PUNCH} {ASK1}"
J2_MSG = f"{SETUP} {PUNCH} {ASK2}"
case("a J1 joke message, setup punchline and ask on one line, passes", fb(J1_MSG, "D-fb-J1"), True)
case("a J2 joke message passes", fb(J2_MSG, "D-fb-J2"), True)
for i in range(len(lint.APPROVED_JOKES)):
    for arm in ("J1", "J2"):
        case(f"approved joke {i + 1} as one {arm} message passes",
             fb(jtext(i, arm), f"D-fb-{arm}"), True)
# Zalo's screenshot, 2026-09-22: the three Sandra Zurick bubbles of 2026-09-14, as they went.
SANDRA = ["My AC and I are fighting again.", "Now it's giving me the cold shoulder.",
          "Alright Sandra, real question and then I'll leave the jokes alone. Would you be "
          "open to talking about the calls that come in after you close?"]
case("the Sandra setup alone fails: a bubble is not a message",
     fb(SANDRA[0], "D-fb-J1"), False, "not an approved joke")
case("the Sandra punchline alone fails", fb(SANDRA[1], "D-fb-J1"), False, "not an approved joke")
case("the Sandra ask alone fails", fb(SANDRA[2], "D-fb-J1"), False, "not an approved joke")
case("the three Sandra bubbles as ONE message pass", fb(" ".join(SANDRA), "D-fb-J1"), True)
case("the joke with no ask fails",
     fb(f"{SETUP} {PUNCH}", "D-fb-J1"), False, "not followed by the fixed J1 ask")
case("the joke and the ask on two lines fail: Enter would send the first line alone",
     fb(f"{SETUP} {PUNCH}\n{ASK1}", "D-fb-J1"), False, "a line break in a joke message")
case("a joke message with a part field fails, whatever the part says",
     fb(J1_MSG, "D-fb-J1", part="setup"), False, "a 'part' field")
case("an unapproved joke fails",
     fb(f"Why did the HVAC guy cross the road? To get to the other vent. {ASK1}", "D-fb-J1"),
     False, "not an approved joke")
case("a greeting before the joke fails",
     fb(f"Hey Mike, why don't ducts keep secrets? {PUNCH} {ASK1}", "D-fb-J1"),
     False, "a greeting before the joke")
case("a digit in a joke message fails",
     fb(jtext(2).replace("Only one with", "Only 1 with"), "D-fb-J1"), False, "a digit")
case("the J1 ask on a J2 row fails", fb(J1_MSG, "D-fb-J2"), False, "the fixed J2 ask")
case("a joke message carrying the pitch fails",
     fb(f"{SETUP} {PUNCH} Alright Mike, I trained a demo AI setter on your website. Would you "
        "be open to talking about the calls that come in after you close?", "D-fb-J1"),
     False, "a pitch line in a joke note")
case("a joke message carrying the dare fails",
     fb(f"{J1_MSG} Want to try and break it?", "D-fb-J1"), False, "the dare is in a joke note")

# ------------------------------------------------------------------------- family plumbing
case("an unrecognised variant family fails loudly",
     li(GOLD_LI[0][0], "C-li-P9"), False, "unrecognised variant family")
case("an empty variant fails loudly", li(GOLD_LI[0][0], ""), False, "unrecognised variant family")
case("a link fails on any family", fb(J1_MSG[:-1] + " https://blackumbrella.app?", "D-fb-J1"),
     False, "a link")
case("an unfilled token fails",
     li(GOLD_LI[0][0].replace("Hi Chris", "Hi [First]"), "C-li-P1"), False, "an unfilled token")

# ------------------------------------------------------------------------- batch level
full_batch = ([li(t, v, entry=i + 1) for i, (t, v) in enumerate(GOLD_LI)]
              + [fb(t, v, entry=7 + i) for i, (t, v) in enumerate(GOLD_FB)]
              + jrow(9, 0, "D-fb-J1", "Al") + jrow(10, 3, "D-fb-J2", "Bo"))
out = batch_case("a mixed batch of control and joke messages is ALL PASS", full_batch, 0)
if "ALL PASS" not in out or "One message rule checked" not in out:
    FAILURES.append(f"mixed batch: expected ALL PASS with the history checked, got:\n{out}")

same = ("Hi {n}, {r}'s review says he called after hours and somebody came out past 10pm. "
        "So you're picking up at night. I trained a demo AI setter on your website that "
        "takes those calls 24/7 and books the job. Want to try and break it?")
out = batch_case("three identical openers in a batch of four still trip the diversity cap",
                 [li(same.format(n=n, r=r), "C-li-P1", entry=i + 1) for i, (n, r) in
                  enumerate([("Al", "Clay"), ("Bo", "Dana"), ("Cy", "Eve")])]
                 + [li(GOLD_LI[1][0], "D-li-P1", entry=4)], 1)
if "open the same way" not in out:
    FAILURES.append(f"diversity cap: wrong message:\n{out}")

out = batch_case("a joke message is an opener like any other message",
                 [li(same.format(n="Al", r="Clay"), "C-li-P1", entry=1),
                  li(same.format(n="Bo", r="Dana"), "C-li-P1", entry=2),
                  li(same.format(n="Cy", r="Eve"), "C-li-P1", entry=3)]
                 + jrow(4, 0, "D-fb-J1", "Di"), 1)
if "open the same way" not in out:
    FAILURES.append(f"diversity with a joke message: expected the cap to trip on 3 of 4:\n{out}")

case("a stray part field on a control note fails on sight",
     dict(li(same.format(n="Al", r="Clay"), "C-li-P1"), part="ask"), False, "a 'part' field")

# ------------------------------------------ the retired multi part machinery (2026-09-22)
# The 2026-09-12 audit of 184db72 built a continuation marker so an interrupted three bubble
# joke could be finished in a later batch. Every shape it accepted is a second or third
# message to a prospect who has not replied, so every one of them is now refused.
out = batch_case("the old fresh three bubble joke entry fails the batch",
                 [fb(SETUP, "D-fb-J1", entry=11, part="setup"),
                  fb(PUNCH, "D-fb-J1", entry=11, part="punchline"),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask")], 1)
if "entry 11 carries 3 notes" not in out:
    FAILURES.append(f"three bubble entry: wrong message:\n{out}")

out = batch_case("the old ask only continuation fails",
                 [fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup", "punchline"], joke_setup=SETUP)], 1)
if "a 'sent_parts' field" not in out or "a 'joke_setup' field" not in out:
    FAILURES.append(f"ask only continuation: wrong message:\n{out}")

out = batch_case("the old punchline plus ask continuation fails",
                 [fb(PUNCH, "D-fb-J1", entry=11, part="punchline",
                     sent_parts=["setup"], joke_setup=SETUP),
                  fb(ASK1, "D-fb-J1", entry=11, part="ask",
                     sent_parts=["setup"], joke_setup=SETUP)], 1)
if "entry 11 carries 2 notes" not in out:
    FAILURES.append(f"two part continuation: wrong message:\n{out}")

case("a continuation marker on a control note fails",
     dict(li(GOLD_LI[0][0], "C-li-P1"), sent_parts=["setup"]), False, "a 'sent_parts' field")
case("a joke_setup on a control note fails",
     dict(li(GOLD_LI[0][0], "C-li-P1"), joke_setup=SETUP), False, "a 'joke_setup' field")

# The joke row cap survives the rewrite: six approved jokes against a Facebook day still
# means repeats, and no joke goes to more than 4 rows in one day.
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

# Channel and family lock. The J arm is Facebook only.
case("a joke message on linkedin fails", li(J1_MSG, "D-li-J1"), False, "the J arm is facebook only")
case("the control still runs on facebook", fb(GOLD_FB[0][0], "D-fb-P1"), True)
case("the control still runs on linkedin", li(GOLD_LI[0][0], "C-li-P1"), True)


# ============================================================== the offer law (2026-09-14)
# From research/ai-agents-sales-2026-09-12.md: what is SOLD is the outcome, an answered call
# and a booked job, never the technology as a product category. The first block is the
# conflict guard and it is the reason this section exists at all: Zalo wrote and approved
# P1_LINE himself on 2026-09-08 and it contains the words "AI setter", so a law written at
# the level of VOCABULARY would fail every note he has ever approved. The law is the FRAME.


def grp(text, variant="MIA-fg-G1", entry=1, channel="facebook_groups"):
    return {"entry": entry, "channel": channel, "variant": variant, "text": text}


case("the owner approved P1 line survives the offer law",
     li(GOLD_LI[0][0], "C-li-P1"), True)
case("the owner approved P2 line survives the offer law",
     li(GOLD_LI[3][0], "D-li-P2"), True)
case("the approved Facebook control survives the offer law",
     fb(GOLD_FB[0][0], "D-fb-P1"), True)

TECH_OPENER = ("Hi Mike, Dana's review from July says she waited two days. That's the call "
               "this catches. I help businesses with AI receptionists. I trained a demo AI "
               "setter on your website that takes those calls 24/7 and books the job. Want "
               "to try and break it?")
case("the tech as a product category fails in the opener",
     li(TECH_OPENER, "D-li-P1"), False, "the tech as a product category")
case("the reason names the frame and not the word",
     li(TECH_OPENER, "D-li-P1"), False, "Sell the outcome")
case("we build AI agents fails",
     fb("Hey Mike, saw Dana's review from July. That's the call this catches.\n\nWe build AI "
        "agents for home service. I trained a demo AI setter on your website. It answers "
        "your calls and texts in about five seconds, 24/7, and books the job straight into "
        "your calendar. Want to try and break it?", "D-fb-P1"),
     False, "'ai agent'")
case("our AI solution fails",
     fb("Hey Mike, saw Dana's review from July. That's the call this catches.\n\nOur AI "
        "solution is the thing here. I trained a demo AI setter on your website that picks "
        "up and books the job. Want to try and break it?", "D-fb-P1"),
     False, "the tech as a product category")
case("voice AI fails",
     li("Hi Mike, Dana's review from July says she waited two days. That's voice AI's whole "
        "job. I trained a demo AI setter on your website that takes those calls 24/7 and "
        "books the job. Want to try and break it?", "D-li-P1"),
     False, "'voice ai'")
case("artificial intelligence fails",
     li("Hi Mike, Dana's review from July says she waited two days. That's artificial "
        "intelligence for you. I trained a demo AI setter on your website that takes those "
        "calls 24/7 and books the job. Want to try and break it?", "D-li-P1"),
     False, "'artificial intelligence'")
case("the offer law reaches an open profile message too",
     li("Hi Mike, Dana's July review says she waited two days. That's the call this catches. "
        "I trained a demo AI setter on your website, our AI receptionist, and it answers and "
        "books the job. Want to try and break it?", "D-li-O1"),
     False, "the tech as a product category")
case("the offer law reaches the joke arm too",
     fb(f"{SETUP} {PUNCH} Alright Mike, real question and then I'll leave the AI receptionist "
        "jokes alone. Would you be open to talking about the calls that come in after you "
        "close?", "D-fb-J1"), False, "the tech as a product category")

# The positive half. P1_LINE and P2_LINE are fixed HEADS and their tails are drafted per row,
# so a note can carry the approved head and still stop selling an outcome.
case("a pitch note whose tail drops the booked job fails",
     li("Hi Mike, Dana's review from July says she waited two days. That's the call this "
        "catches. I trained a demo AI setter on your website that picks up 24/7. Want to "
        "try and break it?", "D-li-P1"), False, "no booked job in the offer")
case("a pitch note whose tail drops the answered call fails",
     li("Hi Mike, Dana's review from July says she waited two days. That's the call this "
        "catches. I trained a demo AI setter on your website and it books the job. Want to "
        "try and break it?", "D-li-P1"), False, "no answered call in the offer")
# Every note Zalo has approved already carries both halves, which is what makes the positive
# check a law about his own copy rather than a new constraint on it.
for i, (text, var) in enumerate(GOLD_LI + GOLD_FB):
    COUNT += 1
    low = text.lower()
    if not any(a in low for a in lint.OUTCOME_ANSWER) or not lint.OUTCOME_BOOK_RE.search(text):
        FAILURES.append(f"gold note {i + 1} does not name both halves of the outcome: {text[:60]!r}")

# ------------------------------------------------- the arithmetic bridge guard (2026-09-14)
# The bridge may hand him the SHAPE of his own math, inside what the hours or the review
# already show. It may never assert a number about his results. The lint cannot read the
# fact, so it catches an invented rate and an ROI claim outright, and a money amount or a
# percentage only when it shares a sentence with a result.
case("a money amount in a bridge fails",
     li("Hi Mike, Google has you closed at 5. That's $400 a month of calls landing in "
        "voicemail. I trained a demo AI setter on your website that takes those calls 24/7 "
        "and books the job. Want to try and break it?", "D-li-P1"),
     False, "a money amount")
case("a percentage in a bridge fails",
     li("Hi Mike, Google has you closed at 5. That's 30% of your calls dying there. I "
        "trained a demo AI setter on your website that takes those calls 24/7 and books the "
        "job. Want to try and break it?", "D-li-P1"), False, "a percentage")
case("a missed call rate we invented for him fails",
     li("Hi Mike, Google has you closed at 5. That's 12 calls a week going to voicemail. I "
        "trained a demo AI setter on your website that takes those calls 24/7 and books the "
        "job. Want to try and break it?", "D-li-P1"), False, "a rate we made up for him")
case("an ROI claim in message one fails",
     li("Hi Mike, Google has you closed at 5. One recovered job pays for the year. I "
        "trained a demo AI setter on your website that takes those calls 24/7 and books the "
        "job. Want to try and break it?", "D-li-P1"), False, "an ROI claim")
case("hours arithmetic inside the posted hours passes",
     li("Hi Mike, Google has the office closed at 5 and open at 8. So that's fifteen hours a "
        "day the phone's on somebody. I trained a demo AI setter on your website that takes "
        "those calls 24/7 and books the job. Want to try and break it?", "D-li-P1"), True)
case("counting what the review itself says passes",
     li("Hi Mike, Dana's review from July says she left two messages before anyone called "
        "back. That's two calls you already know about. I trained a demo AI setter on your "
        "website that takes those calls 24/7 and books the job. Want to try and break it?",
        "D-li-P1"), True)
case("24/7 is not a result claim", li(GOLD_LI[0][0], "C-li-P1"), True)
case("five seconds is not a result claim", fb(GOLD_FB[0][0], "D-fb-P1"), True)

# ------------------------------------------- G1, the Facebook group post (channel NOT STARTED)
G1_A = ("Be the only HVAC company in Miami whose phone gets answered after 5 pm. Mine picks "
        "up in about five seconds, day or night, and books the job into the calendar. It's "
        "sitting there right now: 305 555 0142. Want to try and break it?")
G1_B = ("Plumbers in Tampa, your phone rings at 9 on a Friday night and it's going to "
        "voicemail. Mine answers in five seconds and books the job into the calendar. Want "
        "to try and break it? Call it or text it: 813 555 0117.")
case("group post A passes", grp(G1_A), True)
case("group post B passes", grp(G1_B, entry=2), True)
case("a group post on facebook fails the channel lock",
     grp(G1_A, channel="facebook"), False, "the G1 arm is facebook_groups only")
case("a control DM on facebook_groups fails the reverse lock",
     grp(GOLD_FB[0][0], variant="D-fb-P1"), False, "takes G1 posts only")
case("a group post with no demo number fails",
     grp(G1_A.replace("305 555 0142", "the number in my bio")), False, "no demo number")
case("a group post carrying the per prospect demo claim fails",
     grp("Every HVAC shop in Miami loses the 6 pm call. I trained a demo AI setter on your "
         "website that picks up and books the job. It's live at 305 555 0142. Want to try "
         "and break it?"), False, "there is no 'your website' in a group")
case("a group post addressed to one person by name fails",
     grp("Hey Mike, your phone's going to voicemail after 5. Mine picks up in five seconds "
         "and books the job into the calendar. Try it at 305 555 0142. Want to try and "
         "break it?"), False, "not addressed to one person by name")
case("a group post addressed to the room passes",
     grp("Hey HVAC owners, your phone's going to voicemail after 5. Mine picks up in five "
         "seconds and books the job into the calendar. It's live at 305 555 0142. Want to "
         "try and break it?"), True)
case("a group post with a link fails",
     grp(G1_A + " https://blackumbrella.app"), False, "a link")
case("a group post with no dare fails",
     grp(G1_A.replace("Want to try and break it?", "Give it a go.")), False, "the dare is missing")
case("a group post that never names the booked job fails",
     grp("Be the only HVAC company in Miami whose phone gets answered after 5 pm. Mine picks "
         "up in about five seconds, day or night. It's sitting there right now: 305 555 "
         "0142. Want to try and break it?"), False, "no booked job in the offer")
case("a group post selling the tech as a category fails",
     grp("Miami HVAC owners, I've got an AI receptionist that picks up after 5 and books the "
         "job into the calendar. It's live at 305 555 0142. Want to try and break it?"),
     False, "the tech as a product category")
case("a group post over the 600 character limit fails",
     grp(G1_A + " " + G1_B + " " + G1_A), False, "over the facebook_groups limit 600")
case("a group post with no contraction fails",
     grp("Be the only HVAC company in Miami whose phone gets answered after 5 pm. Mine picks "
         "up in about five seconds, day or night, and books the job into the calendar. The "
         "number is 305 555 0142. Want to try and break it?"), False, "no contraction")

# Identical copy across groups is the saturation failure the sweep names by hand (one
# creator's post copied word for word by another). The opener diversity cap already bounds
# it, and the group family is in that population by design.
out = batch_case("five identical group posts fail the diversity cap",
                 [grp(G1_A, entry=i) for i in range(1, 6)], 1)
if "notes open the same way" not in out:
    FAILURES.append(f"identical group posts: wrong message:\n{out}")
out = batch_case("a mixed batch of two distinct group posts passes",
                 [grp(G1_A, entry=1), grp(G1_B, entry=2)], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"two distinct group posts: expected ALL PASS, got:\n{out}")

case("an unknown family still fails and the message lists G1",
     li(GOLD_LI[0][0], "C-li-Z9"), False, "O1, I1 or G1")


# ================================================ the 2026-09-14 QA pass, one case per finding
# Every case below is a defect the QA audit reproduced against the live corpus, not a
# hypothetical. The two HIGH ones are false positives against copy that ALREADY WENT OUT,
# which is the failure class this lint exists to prevent, so they are guarded first.

# HIGH 1. Quoting HIS OWN advertised price is approved opener type 3, and two notes carrying
# one were sent on 2026-09-10. A flat ban on "$" failed both. Real text, from sent-log.csv.
SENT_0910_MAGGIE = ("Hi Maggie, saw your $83-off drain cleaning offer plus a free camera "
                    "inspection; Google lists a 5pm close. So somebody's got to handle the "
                    "evening calls. I trained a demo AI setter on your website that takes "
                    "those calls 24/7 and books the job. Want to try and break it?")
SENT_0910_GEORGE = ("Hi George, your $50 referral offer runs through Sept 30, but Google "
                    "lists a 6pm close. That's a reason to catch calls after 6. I built a "
                    "quick demo off your website: it picks up when nobody can, day or night, "
                    "and books the job. Want to try and break it?")
case("a sent note quoting his own $83 promo still passes", li(SENT_0910_MAGGIE, "C-li-P1"), True)
case("a sent note quoting his own $50 promo still passes", li(SENT_0910_GEORGE, "C-li-P2"), True)
case("the specificity law's own $79 tune up example passes",
     li("Hi Mike, your $79 tune up ad's running right now, and Google says you close at 5. "
        "So that ad money keeps ringing after hours. I trained a demo AI setter on your "
        "website that takes those calls 24/7 and books the job. Want to try and break it?",
        "C-li-P1"), True)
case("a 0% interest ad quoted from his own page passes",
     li("Hi Mike, your 0% Interest For 60 Months ad's running and Google says you close at "
        "5. So that ad money keeps ringing after hours. I trained a demo AI setter on your "
        "website that takes those calls 24/7 and books the job. Want to try and break it?",
        "C-li-P1"), True)

BRIDGE = ("Hi Mike, Google has you closed at 5. %s I trained a demo AI setter on your "
          "website that takes those calls 24/7 and books the job. Want to try and break it?")
case("a money amount NEXT TO a result still fails",
     li(BRIDGE % "That's $400 a month of calls landing in voicemail.", "D-li-P1"),
     False, "a money amount next to a result")
case("8k of installs fails", li(BRIDGE % "That's 8k of installs sitting in voicemail.",
     "D-li-P1"), False, "a money amount next to a result")
case("eight grand a month of jobs fails",
     li(BRIDGE % "That's eight grand a month of jobs in voicemail.", "D-li-P1"),
     False, "a money amount next to a result")

# HIGH 2. "our ai" is inside "your air", and this is an HVAC skill: prospects.csv carries
# 3,016 businesses with "Air" in the name. Word boundaries, not substrings.
case("a note quoting 'your air conditioning' passes",
     li("Hi Dana, Marcus's review says your air conditioning tech was out there past 10 on a "
        "Sunday. So somebody's picking up at 10 at night. I trained a demo AI setter on your "
        "website that takes those calls 24/7 and books the job. Want to try and break it?",
        "D-li-P1"), True)
case("a note naming 'your Air Texas' line passes",
     li("Hi Charles, Google has your Air Texas line closing at 7 weekdays. So somebody's "
        "still getting those calls. I trained a demo AI setter on your website that takes "
        "those calls 24/7 and books the job. Want to try and break it?", "D-li-P1"), True)
case("'we do air conditioning too' is not the tech as a category",
     fb("Hey Mike, saw Dana's review from July. That's the call this catches.\n\nWe do air "
        "conditioning work ourselves, so I know the phones. I trained a demo AI setter on "
        "your website. It answers your calls and texts in about five seconds, 24/7, and "
        "books the job straight into your calendar. Want to try and break it?", "D-fb-P1"),
     True)
case("'Our AI does the rest' still fails",
     li(BRIDGE % "Our AI does the rest.", "D-li-P1"), False, "'our ai'")
case("the plural 'AI agents' still fails",
     li(BRIDGE % "We build AI agents for home service.", "D-li-P1"), False, "'ai agent'")
case("the plural 'AI receptionists' still fails",
     li(BRIDGE % "I sell AI receptionists.", "D-li-P1"), False, "the tech as a product category")

# MEDIUM 3. The invented rate has to survive the register the skill teaches, which spells
# numbers out, and the "hundreds OF calls" and one adjective shapes.
for bad in ["So that's about thirty calls a month you're missing.",
            "So that's hundreds of calls a week going to voicemail.",
            "So that's dozens of jobs every month sitting in voicemail.",
            "So that's 30 missed calls a month right there.",
            "So that's 40 calls a week."]:
    case(f"invented rate fails: {bad[:34]}", li(BRIDGE % bad, "D-li-P1"),
         False, "a rate we made up for him")
case("arithmetic on the posted hours still passes",
     li(BRIDGE % "So that's fifteen hours a day where that phone's on somebody.", "D-li-P1"), True)
case("counting what the review says still passes",
     li(BRIDGE % "That's two calls you already know about, and she's the one who wrote it "
        "down.", "D-li-P1"), True)

# MEDIUM 4. The group greeting rule: the room is not a person.
GPOST = ("%s your phone's going to voicemail after 5. Mine picks up in five seconds and "
         "books the job into the calendar. It's live at 305 555 0142. Want to try and break "
         "it?")
for head in ["Hey everyone,", "Hey folks,", "Hi all,", "Hey HVAC owners,", "Contractors,"]:
    case(f"a group post addressed to the room passes: {head}", grp(GPOST % head), True)
for head in ["Hi Mike,", "Hi Mike.", "Hey Mike and Dana,", "Mike,"]:
    case(f"a group post addressed to a person fails: {head}", grp(GPOST % head),
         False, "not addressed to one person by name")

# MEDIUM 6. The whole file diversity cap is diluted by the other channels, so it also runs
# per channel: five identical group posts inside a normal LinkedIn batch used to pass.
MIXED = [grp(G1_A, entry=i) for i in range(1, 6)] + [
    li(t, v, entry=10 + i) for i, (t, v) in enumerate(GOLD_LI)]
out = batch_case("five identical group posts inside a LinkedIn batch fail per channel", MIXED, 1)
if "on facebook_groups" not in out:
    FAILURES.append(f"mixed batch: expected a per channel diversity failure, got:\n{out}")
out = batch_case("a mixed batch with distinct group posts passes",
                 [grp(G1_A, entry=1), grp(G1_B, entry=2)] +
                 [li(t, v, entry=10 + i) for i, (t, v) in enumerate(GOLD_LI)], 0)
if "ALL PASS" not in out:
    FAILURES.append(f"mixed batch, distinct posts: expected ALL PASS, got:\n{out}")

# LOW. Channel aliases: sent-log.csv writes the short codes, and an unknown channel used to
# take LinkedIn's 300 silently.
case("the short channel code 'li' is the linkedin channel",
     {"entry": 1, "channel": "li", "variant": "C-li-P1", "text": GOLD_LI[0][0]}, True)
case("the short channel code 'fb' is the facebook channel and gets its 420",
     {"entry": 1, "channel": "fb", "variant": "D-fb-P1", "text": GOLD_FB[0][0]}, True)
case("an unrecognised channel fails instead of silently taking 300",
     {"entry": 1, "channel": "whatsapp", "variant": "C-li-P1", "text": GOLD_LI[0][0]},
     False, "unrecognised channel")

# LOW. The booking half of the outcome is a shape, not a fixed string list.
for tail in ["books it straight into your calendar", "gets the job on your calendar",
             "books you the job"]:
    case(f"the booked job reads as booked: {tail}",
         li("Hi Mike, Dana waited two days. That's the call this catches. I trained a demo "
            "AI setter on your website. It answers your calls and " + tail + ". Want to try "
            "and break it?", "D-li-P1"), True)

# LOW. The outcome check reads the OFFER, not the whole note: the fact clause used to satisfy
# it while the pitch itself was pure product speak.
case("a fact clause cannot satisfy the outcome check for the offer",
     li("Hi Dana, Dana's review says nobody answers the phone after 5 and she books the job "
        "elsewhere. So that's a lost customer. I trained a demo AI setter on your website, "
        "the same stack the big franchises run. Want to try and break it?", "D-li-P1"),
     False, "no answered call in the offer")


# ============================================ the 2026-09-14 QA pass, round two
# Round one's fixes introduced their own gaps, and a mutation run found three mechanisms
# with ZERO coverage: emptying ROOM_WORDS, cutting RESULT_NOUN down to "calls" and dropping
# the second name from BARE_NAME all left the suite green. These cases close that.

# ROOM_WORDS: addressing the room is the normal shape for a group post, and it has to be
# the ALLOWLIST doing the work, not the shape of the string.
for head in ["Hey everyone,", "Hey folks,", "Hi all,", "Hi guys,", "Hey team,",
             "Alright,", "Okay,", "Look,", "Honestly,", "Hey Tampa,", "Hey Miami,",
             "Plumbers,", "Contractors,", "Morning,"]:
    case(f"the room is not a person: {head}", grp(GPOST % head), True)
for head in ["Hi Dana,", "Hey Dana and Mike,", "Dana,", "Dana and Mike,", "Morning Dana,",
             "Hello Dana."]:
    case(f"a person is a person: {head}", grp(GPOST % head),
         False, "not addressed to one person by name")

# RESULT_NOUN: one case per noun class, because the sentence scoping is only as good as
# this list and a mutation cutting it to "calls" survived the suite.
for noun, claim in [("callers", "Thirty percent of your callers hang up before anyone picks up."),
                    ("business", "That turns into $30,000 of business a year for you."),
                    ("work", "That's $25,000 of work you never see."),
                    ("appointments", "Those are $8,000 of appointments going to the next guy."),
                    ("table", "You're leaving $40,000 on the table every year."),
                    ("door", "Roughly 12k a month walks past your front door."),
                    ("clients", "That's 40% of your clients calling somebody else."),
                    ("voicemail", "That's $8,000 of installs sitting in voicemail.")]:
    case(f"an invented result claim on {noun!r} fails", li(BRIDGE % claim, "D-li-P1"),
         False, "next to a result")
case("a spelled out percentage is still a percentage",
     li(BRIDGE % "Thirty percent of your callers give up.", "D-li-P1"),
     False, "a percentage next to a result")

# F-6: the group post's offer is everything after its opener, so a quoted review in the
# opener cannot satisfy the outcome check. Same bug that was fixed for the pitch family.
case("a review quoted in a group post opener cannot satisfy the offer",
     grp("Plumbers in Tampa, the Google review says nobody answers the phone after 5 and she "
         "books the job somewhere else. Mine is a front desk that never sleeps. It's at 813 "
         "555 0117. Want to try and break it?", "TPA-fg-G1"),
     False, "no answered call in the offer")

# F-5: linkedin_dm is the limit the O1 and I1 lanes borrow, not a channel a note may declare.
# Declaring it bought a 420 character invitation note.
LONG_INVITE = ("Hi Mike, Dana's review from July says she left two messages before anyone "
               "called her back and the same thing happened to her neighbour that week on a "
               "Sunday night. That's the call this catches every time. I trained a demo AI "
               "setter on your website that takes those calls 24/7 and books the job. Want "
               "to try and break it? Call it, text it, throw it your weirdest customer.")
# 2026-09-22: there is no invitation note any more (option A), so the same text is the one
# LinkedIn message after the accept and takes the 420 DM limit.
case("a LinkedIn message between 300 and 420 passes now that there is no invitation note",
     li(LONG_INVITE, "C-li-P1"), True)
case("declaring the internal linkedin_dm limit as a channel fails",
     {"entry": 1, "channel": "linkedin_dm", "variant": "C-li-P1", "text": LONG_INVITE},
     False, "unrecognised channel")

# F-8: the answered half has to match the passive, which is how the offer law's own
# replacement column phrases it.
case("'your phone gets answered' reads as the answered call",
     li("Hi Mike, Dana waited two days. That's the call this catches. I trained a demo AI "
        "setter on your website: your phone gets answered after 5 and it books the job. "
        "Want to try and break it?", "D-li-P1"), True)
case("'schedules the job' reads as the booked job",
     li("Hi Mike, Dana waited two days. That's the call this catches. I trained a demo AI "
        "setter on your website that answers the phone and schedules the job. Want to try "
        "and break it?", "D-li-P1"), True)

# F-4: BANNED is the list common() reads, so appending to it has to work. A plain phrase
# gets substring matching; a tech phrase gets word boundaries.
COUNT += 1
if "ai receptionist" not in lint.BANNED or "leverage" not in lint.BANNED:
    FAILURES.append("BANNED no longer carries both halves of the ban list")
COUNT += 1
if lint.TECH_SET != set(lint.TECH_AS_CATEGORY):
    FAILURES.append("TECH_SET has drifted from TECH_AS_CATEGORY")

# F-7: the diversity buckets and check() have to normalise the channel the same way, or an
# omitted channel key splits one population in two and hides a saturation.
# Four byte identical LinkedIn openers, two of them with the `channel` key omitted, beside
# five distinct Facebook openers. The whole file cap is 5 and 4 is under it, so only the per
# channel pass can see this; when the omitted key bucketed separately it split 4 into 2 and
# 2 and the saturation disappeared entirely.
NOCH = [{"entry": i, "variant": "C-li-P1", "text": GOLD_LI[0][0]} for i in (1, 2)]
WITHCH = [li(GOLD_LI[0][0], "C-li-P1", entry=i) for i in (3, 4)]
OTHER = [fb(t, "D-fb-" + v[-2:], entry=20 + i) for i, (t, v) in enumerate(GOLD_LI[1:])]
out = batch_case("an omitted channel key does not split the diversity population",
                 NOCH + WITHCH + OTHER, 1)
if "on linkedin" not in out:
    FAILURES.append(f"omitted channel key: expected the linkedin population to fail, got:\n{out}")
COUNT += 1
if lint.note_channel({}) != "linkedin" or lint.note_channel({"channel": "LI"}) != "linkedin":
    FAILURES.append("note_channel does not normalise a missing or upper case channel")

# ================================ the one message rule, per note (Zalo, 2026-09-22)
# Refusal 2: a bump, a takeaway or a continuation, whatever the batch calls it.
for kind in ["bump", "bump1", "bump2", "takeaway", "continuation", "followup", "follow_up"]:
    case(f"kind {kind!r} fails", fb(GOLD_FB[0][0], "D-fb-P1", kind=kind), False, f"kind {kind!r}")
for stage in ["BUMP1", "BUMP2", "SENT_CONT", "bump2"]:
    case(f"stage {stage!r} fails", fb(GOLD_FB[0][0], "D-fb-P1", stage=stage), False,
         f"stage {stage!r}")
case("stage SENT is the one message and passes", fb(GOLD_FB[0][0], "D-fb-P1", stage="SENT"), True)
case("kind message said out loud passes", fb(GOLD_FB[0][0], "D-fb-P1", kind="message"), True)
for phrase in ["Last one from me, Chris.", "Just following up on this.",
               "Following up on my note.", "Bumping this up.",
               "In case you missed my last message.", "Circling back on this."]:
    case(f"the follow up phrase fails in any note: {phrase}",
         li(phrase + " " + GOLD_LI[0][0], "C-li-P1"), False, "banned phrase")

# Connection requests: LinkedIn only, NO note (option A, Zalo, 2026-09-22 about 17:10 ET).
case("a connect entry with no text passes", li("", "D-li-P1", kind="connect"), True)
case("a connect entry with the text key missing passes",
     {"entry": 1, "channel": "linkedin", "variant": "D-li-P2", "kind": "connect"}, True)
case("a connect entry with a whitespace only text passes: nothing is typed",
     li("   ", "D-li-P1", kind="connect"), True)
case("a connect entry carrying a note fails",
     li("Hi Rae, saw the Sunday review. Mind if I connect?", "D-li-P1", kind="connect"),
     False, "a connection note")
case("a connect entry carrying the old control note fails",
     li(GOLD_LI[0][0], "C-li-P1", kind="connect"), False, "a connection note")
case("a connect entry on facebook fails",
     fb("", "D-fb-P1", kind="connect"), False, "connection requests are LinkedIn only")
case("a connect entry naming the O1 lane fails",
     li("", "D-li-O1", kind="connect"), False, "<tier>-li-P1 or <tier>-li-P2")
case("a connect entry naming the retired N1 fails",
     li("", "D-li-N1", kind="connect"), False, "<tier>-li-P1 or <tier>-li-P2")

# ================================ the one message rule, batch and history (2026-09-22)
# Refusals 1 and 3 against a small pipeline and log. `stage` column order is the real one.
PIPE = [
    "fresh1,Fixture Air,Miami,D,fb,,Mike,FOUND,,,D-fb-J1,,,,0,",
    "sent1,Fixture Drains,Miami,D,fb,,Sandra,SENT,2026-09-22,,D-fb-J1,,,,1,",
    "cold1,Fixture Pipes,Houston,D,fb,,Frank,COLD,2026-09-15,,D-fb-J2,,,,1,",
    "rep1,Fixture Flow,Tampa,D,fb,,Heather,REPLIED,2026-09-15,,D-fb-J2,,,,1,",
    "dead1,Fixture Stop,Tampa,D,fb,,Ron,DEAD,2026-09-15,,D-fb-P1,,,,1,",
    "touched1,Fixture Legacy,Tampa,D,fb,,Lee,FOUND,,,D-fb-P1,,,,1,",
    "noted1,Fixture Ducts,Phoenix,C,li,,Maggie,FOUND,,,C-li-P1,,,,0,",
    "bare1,Fixture Plumbing,Tampa,C,li,,Chris,FOUND,,,C-li-P1,,,,0,",
    "friend1,Fixture Cooling,Orlando,D,fb,,Dan,FOUND,,,D-fb-P2,,,,0,",
    "nochan1,Fixture Nowhere,Miami,D,li,,Pat,NO_CHANNEL,2026-09-14,,D-li-O1,,,,1,",
]
LOG = [
    '2026-09-22 10:00,fb,sent1,u,SENT,aa,My AC,D-fb-J1,joke,"My AC and I are fighting again."',
    '2026-09-22 10:03,fb,sent1,u,SENT_CONT,dd,Now it,D-fb-J1,joke,"Now it\'s giving me the cold shoulder."',
    '2026-09-10 16:21,li,noted1,u,CONNECT,bb,Hi Maggie,C-li-P1,review,"Hi Maggie, the note text"',
    '2026-09-23 09:00,li,bare1,u,CONNECT,,,C-li-P1,,',
    '2026-09-14 09:10,fb,friend1,u,FRIEND,,,D-fb-P2,,',
    '2026-09-14 12:00,li,nochan1,u,SENT,cc,Hi Pat,D-li-O1,review,"Hi Pat, the message"',
]


def hb(name, notes, want_exit, *want, extra=()):
    out = batch_case(name, notes, want_exit, pipeline=PIPE, log=LOG, autofill=False, extra=extra,
                     known=["prospectsonly1"])
    for w in want:
        if w not in out:
            FAILURES.append(f"{name}: expected {w!r} in:\n{out}")
    return out


J_FRESH = jtext(1, "J1", "Mike")
hb("a single joke message to a fresh prospect passes",
   [fb(J_FRESH, "D-fb-J1", prospect_id="fresh1")], 0, "ALL PASS", "One message rule checked")
hb("a prospect in prospects.csv and not in the pipeline yet passes",
   [fb(J_FRESH, "D-fb-J1", prospect_id="prospectsonly1")], 0, "ALL PASS")
hb("an id the folder does not know is refused, not read as a fresh prospect",
   [fb(J_FRESH, "D-fb-J1", prospect_id="brandnew")], 1, "is in neither pipeline.csv nor prospects.csv")
hb("a real id with one character dropped is refused (2026-09-22 QA repro)",
   [fb(J_FRESH, "D-fb-J1", prospect_id="sent")], 1, "is in neither pipeline.csv nor prospects.csv")
hb("a real id with the owner's name appended is refused",
   [fb(J_FRESH, "D-fb-J1", prospect_id="sent1 (Sandra)")], 1, "is in neither pipeline.csv nor prospects.csv")
hb("the one message after a note-less connection is accepted passes (option A)",
   [li(GOLD_LI[0][0], "C-li-P1", prospect_id="bare1")], 0, "ALL PASS")
hb("the one message after an accepted friend request passes",
   [fb(GOLD_FB[0][0], "D-fb-P1", prospect_id="friend1")], 0, "ALL PASS")
hb("a connect entry with no note to a fresh prospect passes",
   [li("", "D-li-P1", kind="connect", prospect_id="fresh1")], 0, "ALL PASS")
hb("a second message to a SENT prospect fails",
   [fb(jtext(3, "J2", "Sandra"), "D-fb-J2", prospect_id="sent1")], 1,
   "already got its one message", "plus 1 more")
hb("a bump to a no reply prospect fails on the kind AND on the history",
   [fb("Last one from me, Sandra. If the after hours calls are already handled, I'll leave "
       "you to it. If they aren't, you know where I am.", "D-fb-J1", kind="bump2",
       prospect_id="sent1")], 1, "kind 'bump2'", "banned phrase: 'last one from me'",
   "already got its one message")
hb("a bump given an innocent kind still fails on the history",
   [fb(jtext(4, "J1", "Sandra"), "D-fb-J1", prospect_id="sent1")], 1,
   "already got its one message")
hb("a second message on ANOTHER channel fails",
   [li(DM_O1, "D-li-O1", prospect_id="sent1")], 1, "already got its one message")
hb("a message to a COLD prospect fails",
   [fb(J_FRESH, "D-fb-J1", prospect_id="cold1")], 1, "is at COLD")
hb("a message after a connection that carried a note fails: the note was the one message",
   [li(GOLD_LI[0][0], "C-li-P1", prospect_id="noted1")], 1,
   "a connection request that carried a note")
hb("a message to a NO_CHANNEL prospect that already had its message fails",
   [fb(J_FRESH, "D-fb-J1", prospect_id="nochan1")], 1, "already got its one message")
hb("pipeline touches with an empty log still fail",
   [fb(J_FRESH, "D-fb-J1", prospect_id="touched1")], 1, "touches 1")
hb("a message to a replied prospect fails: the thread is Zalo's",
   [fb(J_FRESH, "D-fb-J1", prospect_id="rep1")], 1, "the thread is Zalo's")
hb("a message to a DEAD prospect fails",
   [fb(J_FRESH, "D-fb-J1", prospect_id="dead1")], 1, "is DEAD")
hb("a connection request to a prospect already messaged fails",
   [li("", "D-li-P1", kind="connect", prospect_id="sent1")], 1,
   "a connection request included")
hb("one prospect in two entries on two channels fails",
   [fb(J_FRESH, "D-fb-J1", entry=1, prospect_id="fresh1"),
    li(GOLD_LI[0][0], "C-li-P1", entry=2, prospect_id="fresh1")], 1, "is in 2 entries")
hb("two notes on one entry fail",
   [fb(J_FRESH, "D-fb-J1", entry=1, prospect_id="fresh1"),
    fb(ASK1, "D-fb-J1", entry=1, prospect_id="fresh1")], 1, "entry 1 carries 2 notes")
hb("two notes with no entry number on one prospect fail",
   [{"channel": "facebook", "variant": "D-fb-J1", "text": J_FRESH, "prospect_id": "fresh1"},
    {"channel": "facebook", "variant": "D-fb-J2", "text": jtext(3, "J2"), "prospect_id": "fresh1"}],
   1, "is in 2 entries")
hb("a note with no prospect_id fails when the history is checked",
   [fb(J_FRESH, "D-fb-J1")], 1, "no prospect_id")
hb("a group post needs no prospect_id", [grp(G1_A)], 0, "ALL PASS")
out = hb("--no-history exits 2, prints COPY PASS and never ALL PASS",
         [fb(J_FRESH, "D-fb-J1", prospect_id="sent1")], 2, "COPY PASS",
         extra=["--no-history"])
if "ALL PASS" in out:
    FAILURES.append(f"--no-history printed ALL PASS:\n{out}")

# The gate has to find the log or refuse. A notes.json outside any working folder fails; the
# same file with --folder pointing at a working folder is checked against it.
COUNT += 1
loose = tempfile.mkdtemp(prefix="bu-lint-loose-")
loose_path = os.path.join(loose, "notes.json")
with open(loose_path, "w") as f:
    json.dump([fb(J_FRESH, "D-fb-J1", prospect_id="sent1")], f)
code, out = run_lint([loose_path])
if code != 1 or "no pipeline.csv" not in out:
    FAILURES.append(f"no working folder: expected exit 1 and 'no pipeline.csv', got {code}:\n{out}")
COUNT += 1
root, _ = working_folder(PIPE, LOG)
code, out = run_lint([loose_path, "--folder", root])
if code != 1 or "already got its one message" not in out:
    FAILURES.append(f"--folder: expected the history refusal, got {code}:\n{out}")
COUNT += 1
os.remove(os.path.join(root, "sent-log.csv"))
code, out = run_lint([loose_path, "--folder", root])
if code != 1 or "cannot read" not in out:
    FAILURES.append(f"missing sent-log.csv: expected 'cannot read', got {code}:\n{out}")
COUNT += 1
with open(os.path.join(root, "sent-log.csv"), "w") as f:
    f.write("timestamp_et,channel,profile_url\n")
code, out = run_lint([loose_path, "--folder", root])
if code != 1 or "has no prospect_id" not in out:
    FAILURES.append(f"sent-log.csv without its columns: expected a column failure, got {code}:\n{out}")
COUNT += 1
os.remove(os.path.join(root, "prospects.csv"))
with open(os.path.join(root, "sent-log.csv"), "w") as f:
    f.write(LOG_HEAD + "\n")
code, out = run_lint([loose_path, "--folder", root])
if code != 1 or "prospects.csv" not in out:
    FAILURES.append(f"missing prospects.csv: expected a failure naming it, got {code}:\n{out}")
shutil.rmtree(root)
# A folder inside the skill (its templates/ or a fixture) is not the working folder.
COUNT += 1
code, out = run_lint([loose_path, "--folder", os.path.join(HERE, "..", "templates")])
if code != 1 or "inside the skill itself" not in out:
    FAILURES.append(f"--folder templates: expected the inside-the-skill refusal, got {code}:\n{out}")
shutil.rmtree(loose)

# A note-less CONNECT logged with the sha1 of the empty string is still a request with no
# note, so the one message after the accept is allowed.
hb_log = LOG + ['2026-09-23 09:05,li,fresh1,u,CONNECT,da39a3ee5e6b4b0d3255bfef95601890afd80709,,D-li-P1,,']
out = batch_case("a CONNECT logged with the empty string's sha1 is not a note",
                 [li(GOLD_LI[0][0], "C-li-P1", prospect_id="fresh1")], 0,
                 pipeline=PIPE, log=hb_log, autofill=False)
if "ALL PASS" not in out:
    FAILURES.append(f"empty sha1 CONNECT: expected ALL PASS, got:\n{out}")

# The real template headers carry the columns the history check reads, and a header written
# with spaces after the commas loads too.
COUNT += 1
for name in ("pipeline.csv", "sent-log.csv"):
    head, _ = lint.read_csv(os.path.join(HERE, "..", "templates", name))
    if "prospect_id" not in head or "stage" not in head:
        FAILURES.append(f"templates/{name} lacks prospect_id or stage: {head}")
COUNT += 1
root, _ = working_folder()
with open(os.path.join(root, "pipeline.csv"), "w") as f:
    f.write(PIPE_HEAD.replace(",", ", ") + "\n" + PIPE[1] + "\n")
pipe_rows = lint.load_history(root)[0]
if pipe_rows.get("sent1", {}).get("stage") != "SENT":
    FAILURES.append(f"a spaced header did not load by column name: {pipe_rows}")
shutil.rmtree(root)

# A byte order mark on the header and an upper case id in the batch change nothing: the id
# still matches, so the second message is still refused.
COUNT += 1
root, _ = working_folder(PIPE, LOG)
with open(os.path.join(root, "pipeline.csv")) as f:
    body = f.read()
with open(os.path.join(root, "pipeline.csv"), "w", encoding="utf-8-sig") as f:
    f.write(body)
bom_path = os.path.join(root, "evidence", "2026-09-23", "session-1", "notes.json")
with open(bom_path, "w") as f:
    json.dump([fb(J_FRESH, "D-fb-J1", prospect_id="  SENT1 ")], f)
code, out = run_lint([bom_path])
if code != 1 or "already got its one message" not in out:
    FAILURES.append(f"BOM header plus an upper case id: expected the history refusal, got {code}:\n{out}")
shutil.rmtree(root)

# The hand made batches in fixtures/single-message/: one that passes, one that trips every
# refusal. These are the files to run by hand when you want to see the gate work.
FX = os.path.join(HERE, "fixtures", "single-message")
COUNT += 1
code, out = run_lint([os.path.join(FX, "notes-pass.json"), "--fixture"])
if code != 2 or "FIXTURE PASS" not in out:
    FAILURES.append(f"fixtures/single-message/notes-pass.json --fixture: expected exit 2 FIXTURE PASS, got {code}:\n{out}")
COUNT += 1
code, out = run_lint([os.path.join(FX, "notes-pass.json")])
if code != 1 or "inside the skill itself" not in out:
    FAILURES.append(f"fixtures/single-message/notes-pass.json without --fixture: expected the inside-the-skill refusal, got {code}:\n{out}")
COUNT += 1
code, out = run_lint([os.path.join(FX, "notes-refuse.json"), "--fixture"])
for want in ["entry 1 carries 2 notes", "kind 'bump2'", "banned phrase: 'last one from me'",
             "prospect fx-sent-fb already got its one message",
             "prospect fx-sent-cross already got its one message",
             "a connection request that carried a note",
             "prospect fx-cold is at COLD", "a connection note",
             "prospect fx-replied is at REPLIED", "prospect fx-dead is DEAD",
             "a 'sent_parts' field"]:
    if want not in out:
        FAILURES.append(f"fixtures/single-message/notes-refuse.json: missing {want!r}:\n{out}")
if code != 1:
    FAILURES.append(f"fixtures/single-message/notes-refuse.json: expected exit 1, got {code}")
COUNT += 1
code, out = run_lint([os.path.join(HERE, "fixtures", "new-families.json"), "--no-history"])
if code != 2 or "COPY PASS" not in out:
    FAILURES.append(f"fixtures/new-families.json: expected exit 2 COPY PASS, got {code}:\n{out}")


print(f"{COUNT} cases")
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES: print("  " + f)
    sys.exit(1)
print("ALL PASS")
