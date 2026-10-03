#!/usr/bin/env python3
"""Tests for pick-format.py. Run: python3 ~/.claude/skills/digest/scripts/pick-format.test.py"""
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "pick-format.py")
spec = importlib.util.spec_from_file_location("pick_format", SCRIPT)
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
    else:
        failed += 1
        print("FAIL %s: got %r, want %r" % (name, got, want))


v = lambda **kw: pf.pick(**kw)["verdict"]

check("01 status is text", v(lines=20, parts=5, links=4, kind="status"), "text")
check("02 yes or no is text", v(lines=8, kind="yesno"), "text")
check("03 one fact is text", v(lines=7, findings=9, kind="fact"), "text")
check("04 under 6 lines is text even with a flow", v(lines=5, parts=5, links=4), "text")
check("05 connected flow adds a diagram", v(lines=20, parts=7, links=6), "text+diagram")
check("06 before and after adds a diagram", v(lines=10, before_after=True), "text+diagram")
check("07 timeline of 4 adds a diagram", v(lines=12, steps=4, timeline=True), "text+diagram")
check("08 timeline of 2 is text", v(lines=12, steps=2, timeline=True), "text")
check("09 3 parts 1 link is text", v(lines=12, parts=3, links=1), "text")
check("10 nine findings add a page", v(lines=30, findings=9, kind="audit"), "text+html")
check("11 five findings is text", v(lines=30, findings=5, kind="audit"), "text")
check("12 table of 8 rows adds a page", v(lines=15, rows=8, kind="compare"), "text+html")
check("13 table of 6 rows is text", v(lines=15, rows=6, kind="compare"), "text")
check("14 plan of 10 steps adds a page", v(lines=25, steps=10, kind="plan"), "text+html")
check("15 plan of 7 steps is text", v(lines=25, steps=7, kind="plan"), "text")
check("16 revisit adds a page", v(lines=10, revisit=True), "text+html")
check("17 40-line report adds a page", v(lines=40, kind="report"), "text+html")
r = pf.pick(lines=30, parts=5, links=4, findings=8)
check("18 both shapes is one page with the diagram inside", (r["verdict"], r["embed_diagram"]), ("text+html", True))
check("19 repeats-text vetoes the extra", v(lines=20, parts=7, links=6, repeats_text=True), "text")
check("20 demo topic picks the diagram", v(lines=18, parts=7, links=7, findings=1), "text+diagram")

p = subprocess.run([sys.executable, SCRIPT, "--lines", "18", "--parts", "7", "--links", "7", "--json"],
                   capture_output=True, text=True)
try:
    got = (p.returncode, json.loads(p.stdout)["verdict"])
except ValueError:
    got = (p.returncode, p.stdout)
check("21 cli json", got, (0, "text+diagram"))
p = subprocess.run([sys.executable, SCRIPT, "--parts", "3"], capture_output=True, text=True)
check("22 cli missing --lines is exit 2", p.returncode, 2)
p = subprocess.run([sys.executable, SCRIPT, "--lines", "-1"], capture_output=True, text=True)
check("23 cli negative count is exit 2", p.returncode, 2)
p = subprocess.run([sys.executable, SCRIPT, "--lines", "3"], capture_output=True, text=True)
check("24 cli text mode", (p.returncode, p.stdout.split(":")[0]), (0, "text"))

print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
