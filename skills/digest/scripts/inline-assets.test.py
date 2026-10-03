#!/usr/bin/env python3
"""Tests for inline-assets.py. Run: python3 ~/.claude/skills/digest/scripts/inline-assets.test.py"""
import base64
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "inline-assets.py")
T = tempfile.mkdtemp(prefix="digest-inline-test-")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL %s %s" % (name, detail))


def w(name, data, mode="w"):
    p = os.path.join(T, name)
    with open(p, mode) as fh:
        fh.write(data)
    return p


png = b"\x89PNG\r\n\x1a\nfake"
w("d.png", png, "wb")
w("kit.css", "body{background:url(bg.png)} .x{color:red}</style>")
w("bg.png", b"\x89PNGbg", "wb")
w("kit.js", "var s='</script>'; window.ok=1;")
page = w("p.html", '<meta name="viewport" content="width=device-width">'
         '<link rel="stylesheet" href="kit.css"><img src="d.png" alt="flow">'
         '<img src="http://127.0.0.1:9/a.png"><a href="d.png">link</a><script src="kit.js"></script>')
out = os.path.join(T, "out.html")
r = subprocess.run([sys.executable, SCRIPT, page, out], capture_output=True, text=True)
html = open(out).read() if os.path.exists(out) else ""
check("01 exit 0 and count", r.returncode == 0 and "4 files inlined" in r.stdout, r.stdout + r.stderr)
check("02 img became a data uri", 'src="data:image/png;base64,%s"' % base64.b64encode(png).decode() in html)
check("03 stylesheet inlined", "<style>" in html and ".x{color:red}" in html and 'href="kit.css"' not in html)
check("04 css url inlined", "url(data:image/png;base64," in html)
check("05 script inlined and escaped", "window.ok=1" in html and "<\\/script>'" in html and 'src="kit.js"' not in html)
check("06 remote img left for page-check", 'src="http://127.0.0.1:9/a.png"' in html)
check("07 plain link untouched", '<a href="d.png">' in html)
check("08 closing style tag in css escaped", "<\\/style>" in html)
bad = w("bad.html", '<img src="nope.png">')
r = subprocess.run([sys.executable, SCRIPT, bad], capture_output=True, text=True)
check("09 missing file exits 1, file untouched", r.returncode == 1 and "nope.png" in r.stderr and open(bad).read() == '<img src="nope.png">')
r = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True)
check("10 no args exits 2", r.returncode == 2)
r = subprocess.run(["node", os.path.join(HERE, "page-check.mjs"), out, os.path.join(T, "o.png")], capture_output=True, text=True)
check("11 inlined page passes page-check except the remote img", r.returncode == 1 and "external img src: http://127.0.0.1:9/a.png" in r.stderr and "points at a file" not in r.stderr, r.stderr)

# QA round 3 regressions
os.makedirs(os.path.join(T, "css"), exist_ok=True)
w("css/kit2.css", "body{background:url(bg2.png)}")
w("css/bg2.png", b"\x89PNG-css-bg", "wb")
w("bg2.png", b"\x89PNG-page-decoy", "wb")
w("print.css", ".a{display:none}")
w("latin.css", "a:after{content:'\xe9'}".encode("latin-1"), "wb")
p2 = w("p2.html", '<meta name="viewport" content="width=device-width"><link rel="stylesheet" href="css/kit2.css"><link rel="stylesheet" href="print.css" media="print">'
       '<img data-src="lazy.png" src=d.png srcset="d.png 1x, d.png 2x"><div style="background:url(d.png)">x</div>'
       '<!-- <img src="old.png"> -->')
o2 = os.path.join(T, "o2.html")
r = subprocess.run([sys.executable, SCRIPT, p2, o2], capture_output=True, text=True)
h2 = open(o2).read() if os.path.exists(o2) else ""
check("12 css url resolves against the stylesheet folder", r.returncode == 0 and base64.b64encode(b"\x89PNG-css-bg").decode() in h2
      and base64.b64encode(b"\x89PNG-page-decoy").decode() not in h2, r.stdout + r.stderr)
check("13 media kept", '<style media="print">' in h2)
check("14 unquoted src inlined, data-src untouched", 'data-src="lazy.png"' in h2 and 'src=d.png' not in h2 and h2.count("data:image/png") >= 4)
check("15 srcset candidates inlined", "srcset=\"data:image/png;base64," in h2 and " 2x" in h2)
check("16 style attribute url inlined", "style=\"background:url(data:image/png" in h2)
check("17 comment left alone", "<!-- <img src=\"old.png\"> -->" in h2)
p3 = w("p3.html", '<link rel="stylesheet" href="latin.css">')
r = subprocess.run([sys.executable, SCRIPT, p3, os.path.join(T, "o3.html")], capture_output=True, text=True)
check("18 non-utf8 is a clean error, nothing written", r.returncode == 1 and "UTF-8" in r.stderr and "Traceback" not in r.stderr
      and not os.path.exists(os.path.join(T, "o3.html")), r.stderr)
r = subprocess.run(["node", os.path.join(HERE, "page-check.mjs"), o2, os.path.join(T, "o2.png")], capture_output=True, text=True)
check("19 inlined page passes page-check", r.returncode == 0, r.stdout + r.stderr)

print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
