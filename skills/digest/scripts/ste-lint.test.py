#!/usr/bin/env python3
"""Tests for ste-lint.py. Run: python3 ~/.claude/skills/digest/scripts/ste-lint.test.py"""
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "ste-lint.py")
spec = importlib.util.spec_from_file_location("ste_lint", SCRIPT)
ste = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ste)

passed = failed = 0


def rules(text, **opts):
    return [f["rule"] for f in ste.lint(text, opts)["findings"]]


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL %s %s" % (name, detail))


def words(n, first="The"):
    return " ".join([first] + ["word"] * (n - 1)) + "."


# 1. clean short text
r = ste.lint("The page sends the form to the API. The API makes a session.")
check("01 clean text", r["clean"] and r["stats"]["sentences"] == 2, r)

# 2. description limit is 25 words
check("02a 25-word description passes", rules(words(25)) == [], rules(words(25)))
check("02b 26-word description flagged", rules(words(26)) == ["sentence-length"], rules(words(26)))

# 3. step (imperative) limit is 20 words
check("03a 20-word step passes", rules(words(20, "Open")) == [], rules(words(20, "Open")))
r = ste.lint(words(21, "Open"))
check("03b 21-word step flagged as step", [f.get("kind") for f in r["findings"]] == ["step"], r["findings"])

# 4. passive voice
check("04 simple passive", "passive" in rules("The event is sent by the cron job."))

# 5. passive with an adverb in the gap
check("05 passive with adverb", "passive" in rules("The contact was automatically created."))

# 6. not passive: existential "there is", and adjectives that end in -ed
check("06a there is + -ed", "passive" not in rules("There is limited time today."))
check("06b colour word red", "passive" not in rules("The light is red."))

# 7. irregular participle
check("07 irregular participle", "passive" in rules("The link was shown to him."))

# 8. get-passive
check("08 get-passive", "passive" in rules("The contact gets created in GHL."))

# 9. plain-word table with a suggestion
r = ste.lint("We utilize the API.")
pw = [f for f in r["findings"] if f["rule"] == "plain-word"]
check("09 plain word utilize", len(pw) == 1 and pw[0]["suggestion"] == "use", r["findings"])

# 10. phrasal verb
check("10 phrasal verb kicked off", "plain-word" in rules("We kicked off the run today."))

# 11. long word
check("11 long word", "long-word" in rules("We need internationalization support."))

# 12. code spans are not graded as words
check("12 code span ignored", rules("The `onboarding_internationalization_dispatcher` job runs.") == [])

# 13. paragraph limit (4 sentences, 60 words)
para = " ".join(["The job runs now."] * 5)
check("13a five sentences flagged", rules(para) == ["paragraph"], rules(para))
check("13b four sentences pass", rules(" ".join(["The job runs now."] * 4)) == [])

# 14. dashes: em, en, spaced hyphen flagged; compound hyphen is fine
check("14a em dash", rules("The page works — mostly.") == ["dash"])
check("14b en dash range", rules("Slots run 1–4 PM.") == ["dash"])
check("14c spaced hyphen", rules("The page works - mostly.") == ["dash"])
check("14d compound hyphen ok", rules("The opt-in page is a one-time form.") == [])
check("14e list marker is not a dash", rules("- The page works.\n- The API works.") == [])

# 15. fenced code is ignored entirely
fenced = "Run this.\n\n```\nThis — is a very long line " + "word " * 40 + "\n```\n"
check("15 fenced code ignored", rules(fenced) == [], rules(fenced))

# 16. decimals, domains and file names do not split sentences
r = ste.lint("It took 49.2 s on blackumbrella.app/trial and bu-trial-page.md today.")
check("16 no false split", r["stats"]["sentences"] == 1, r["stats"])

# 17. URL counts as one word
r = ste.lint("Open https://operatorbase.app/onboard/abc/def/ghi/jkl now.")
check("17 url is one word", r["stats"]["max_words"] == 3, r["stats"])

# 18. headings are not graded as sentences
r = ste.lint("# A heading that is written in a passive way and is very long indeed for a heading line\n\nThe job runs.")
check("18 heading skipped", r["clean"] and r["stats"]["sentences"] == 1, r)

# 19. list items are separate units, so a long list is not one paragraph
lst = "\n".join("%d. The job runs now and then stops." % i for i in range(1, 9))
check("19 list items separate", rules(lst) == [], rules(lst))

# 20. thresholds are configurable
check("20 custom desc max", rules("The job runs every minute on the server.", desc_max=5) == ["sentence-length"])

# 21. CLI: exit 1 and valid JSON when flagged
p = subprocess.run([sys.executable, SCRIPT, "-", "--json"], input="We utilize the API.", capture_output=True, text=True)
try:
    data = json.loads(p.stdout)
    ok = p.returncode == 1 and data["clean"] is False and data["counts"].get("plain-word") == 1
except ValueError:
    ok = False
check("21 cli json exit 1", ok, (p.returncode, p.stdout[:200]))

# 22. CLI: exit 0 on clean stdin, text mode says CLEAN
p = subprocess.run([sys.executable, SCRIPT], input="The job runs.", capture_output=True, text=True)
check("22 cli clean exit 0", p.returncode == 0 and "CLEAN" in p.stdout, (p.returncode, p.stdout))

# 23. CLI: missing file is exit 2
p = subprocess.run([sys.executable, SCRIPT, "/nonexistent/ste-lint-missing.md"], capture_output=True, text=True)
check("23 cli missing file exit 2", p.returncode == 2, (p.returncode, p.stderr))

# 24. abbreviations do not split sentences
r = ste.lint("Use a plain verb, e.g. start, not commence a task.")
check("24 e.g. no split", r["stats"]["sentences"] == 1, r["stats"])

# 25. quoted text is cited, not authored: word and voice checks skip it, length still counts
check("25a quoted counter-example skipped", rules('Write "use", not "utilize the data that is sent".') == [], rules('Write "use", not "utilize the data that is sent".'))
check("25b unquoted still flagged", "plain-word" in rules("We utilize the data."))
check("25c quoted words still count for length", rules('The ' + '"' + "word " * 30 + '"' + " ends.") == ["sentence-length"])

# 26. YAML frontmatter is metadata, not prose (dashes in it are still flagged)
fm = "---\nname: x\ndescription: " + "word " * 40 + "\n---\n\nThe job runs.\n"
check("26a frontmatter skipped", rules(fm) == [], rules(fm))
check("26b dash in frontmatter flagged", rules("---\ndescription: a \u2014 b\n---\nThe job runs.\n") == ["dash"])

# 27. Telegram-style short lines (no blank lines) are separate paragraphs
tg = "Done.\nThe page is live.\n3 of 3 checks pass.\nThe bell works.\nNext: your call.\n"
check("27 telegram lines are not one paragraph", rules(tg) == [], rules(tg))
# 28. a markdown line that wraps mid-sentence still joins
r = ste.lint("The job runs every minute and\nsends the event to GHL.")
check("28 wrapped line joins", r["stats"]["sentences"] == 1, r["stats"])
# 29. a sentence that starts with a lowercase name still splits
r = ste.lint("The run ended at noon today. npm ci ran clean on the first try in the new worktree.")
check("29 lowercase start splits", r["stats"]["sentences"] == 2, r["stats"])
# 30. "No." ends a sentence; "No. 5" does not
check("30a is No. splits", ste.lint("The answer is No. The job runs.")["stats"]["sentences"] == 2)
check("30b No. 5 stays", ste.lint("See No. 5 in the list.")["stats"]["sentences"] == 1)
# 31. adjectives that look like participles, and "get started", are not passive
check("31a unchanged", "passive" not in rules("The rest of the template was unchanged."))
check("31b getting started", "passive" not in rules("Getting started is easy."))
check("31c real passive still caught", "passive" in rules("The template was changed by the worker."))
# 32. long technical words with no plain synonym are allowed
check("32 authentication allowed", rules("The authentication step runs first.") == [])

# QA round 2 regressions
status = ("Trial page: live since 1 Oct\nBell notices: live, PR #166, System tab only\n"
          "GHL workflow: v7 published\nGap: Submitted URL holds no workflow\nNext: your call\n")
check("33 status lines without end punctuation", "sentence-length" not in rules(status), rules(status))
r = ste.lint("The page posts the form to\nOperator Base on the server.")
check("34 wrap after a joining word joins", r["stats"]["sentences"] == 1, r["stats"])
r = ste.lint("Open the setup link at https://operatorbase.app/onboard/abc. Then the client answers the questions.")
check("35 URL keeps the period out", r["stats"]["sentences"] == 2 and r["clean"], (r["stats"], r["findings"]))
r = ste.lint("He said \u201cthe job runs.\u201d The next step starts.")
check("36 curly closing quote splits", r["stats"]["sentences"] == 2, r["stats"])
r = ste.lint("The U.S. run took 5 minutes today.")
check("37 dotted acronym does not split", r["stats"]["sentences"] == 1, r["stats"])
check("38a state words are not passive", rules("The fix is done. The PR is merged. The flag is enabled.") == [])
check("38b state word with by is passive", "passive" in rules("The PR is merged by the bot."))

# QA round 3 regressions
st = ("trial-flow.txt: lint clean, 13 lines, no dash\ntrial-flow.png: 1080x3247, clean render\n"
      "send.py: 2 messages sent, ids 21511 and 21512\naaaa1111: v7 published, tag after Create contact\n")
check("39 lowercase label lines are separate", "sentence-length" not in rules(st), rules(st))
r = ste.lint("The page sends the form, the SMS and the email, etc. The API then makes the session in the agency.")
check("40 etc. at a sentence end splits", r["stats"]["sentences"] == 2, r["stats"])
check("41 e.g. before a capital does not split", ste.lint("Use a short label, e.g. GHL or OB, in the text.")["stats"]["sentences"] == 1)

print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
