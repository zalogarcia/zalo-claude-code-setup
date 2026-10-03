#!/usr/bin/env python3
"""ste-lint: check text against the digest skill's STE-lite card (80% of ASD-STE100).

Usage:
  ste-lint.py [FILE | -] [--json] [--step-max N] [--desc-max N]
              [--para-sentences N] [--para-words N] [--long-word N]

Reads FILE, or stdin when FILE is "-" or absent. Markdown aware: fenced code,
inline code, URLs and table rows are not graded as prose.

Flags (each one is a finding):
  sentence-length  a step (imperative) over --step-max words (default 20), or a
                   description over --desc-max words (default 25)
  passive          a "be/get + past participle" phrase (likely passive voice)
  plain-word       a word or phrase on the plain-word table, with the suggestion
  long-word        a plain word of --long-word letters or more (default 14)
                   (passive, plain-word and long-word skip text inside double quotes:
                   a quoted example is cited, not authored)
  paragraph        a paragraph or list item over --para-sentences sentences
                   (default 4) or --para-words words (default 60)
  dash             an em dash, en dash, or a spaced hyphen used as a dash

Exit codes: 0 clean, 1 flagged, 2 usage or read error.
The rules card this enforces: ~/.claude/skills/digest/ste-card.md
"""
import argparse
import json
import re
import sys

DEFAULTS = {"step_max": 20, "desc_max": 25, "para_sentences": 4, "para_words": 60, "long_word": 14}

# First words that make a sentence an instruction (STE "procedural" text).
IMPERATIVES = {
    "add", "apply", "ask", "attach", "book", "build", "call", "change", "check", "choose",
    "click", "close", "commit", "confirm", "connect", "copy", "create", "delete", "deploy",
    "disable", "do", "drop", "edit", "enable", "enter", "find", "fix", "give", "go",
    "install", "keep", "let", "load", "make", "mark", "merge", "move", "open", "paste",
    "pick", "press", "publish", "pull", "push", "put", "read", "record", "remove", "rename",
    "replace", "reply", "restart", "review", "run", "save", "select", "send", "set", "sign",
    "start", "stop", "submit", "switch", "take", "tap", "tell", "test", "turn", "type",
    "update", "upload", "use", "verify", "wait", "write",
}

BE_FORMS = {"am", "is", "are", "was", "were", "be", "been", "being",
            "isn't", "aren't", "wasn't", "weren't", "isnt", "arent", "wasnt", "werent"}
GET_FORMS = {"get", "gets", "got", "gotten", "getting"}
# Words allowed between the auxiliary and the participle ("is not sent", "was automatically made").
GAP_WORDS = {"not", "never", "also", "just", "only", "already", "still", "now", "then",
             "often", "always", "usually", "first", "then", "all", "both", "each", "fully"}
IRREGULAR_PARTICIPLES = {
    "begun", "bought", "bound", "broken", "brought", "built", "caught", "chosen", "cut",
    "done", "drawn", "driven", "eaten", "fallen", "fed", "felt", "forgotten", "found",
    "given", "gone", "gotten", "held", "hidden", "hit", "kept", "known", "laid", "led",
    "left", "lost", "made", "meant", "met", "paid", "put", "read", "run", "said", "seen",
    "sent", "set", "shown", "shut", "sold", "spent", "split", "stolen", "struck", "stuck",
    "taken", "taught", "thought", "thrown", "told", "torn", "understood", "won", "worn",
    "written",
}
# Words that end in "ed" but are not past participles.
ED_NOT_PARTICIPLE = {"red", "need", "speed", "seed", "feed", "bed", "shed", "embed", "indeed",
                     "exceed", "proceed", "succeed", "breed", "greed", "weed", "deed", "heed",
                     "steed", "naked", "wicked", "rugged", "crooked", "sacred", "hundred",
                     "kindred", "ragged", "beloved", "shred", "sled", "bled",
                     # adjectives that look like participles
                     "unchanged", "interested", "supposed", "experienced", "detailed", "advanced",
                     "complicated", "sophisticated", "tired", "excited", "dedicated"}
# Status words that describe a state, not an action: "The PR is merged." (passive only with "by").
STATE_WORDS = {"done", "merged", "enabled", "disabled", "closed", "finished", "fixed", "deployed", "shipped",
               "published", "paused", "blocked", "stuck", "broken", "connected", "installed"}
# Long technical words that have no shorter plain word.
TECH_LONG_WORDS = {"authentication", "authorization", "authorisation", "infrastructure",
                   "implementation", "troubleshooting", "administrators", "configurations"}

# Plain-word table: regex (lowercase, word bounded) -> suggestion.
PLAIN_WORDS = [
    (r"utili[sz](e|es|ed|ing|ation)", "use"),
    (r"facilitat(e|es|ed|ing)", "help"),
    (r"commenc(e|es|ed|ing)", "start"),
    (r"terminat(e|es|ed|ing)", "end, stop"),
    (r"approximately", "about"),
    (r"additional(ly)?", "more, also"),
    (r"subsequent(ly)?", "then, later, next"),
    (r"prior to", "before"),
    (r"in order to", "to"),
    (r"numerous", "many"),
    (r"demonstrat(e|es|ed|ing)", "show"),
    (r"endeavou?r(s|ed|ing)?", "try"),
    (r"ascertain(s|ed|ing)?", "find, learn"),
    (r"leverag(e|es|ed|ing)", "use"),
    (r"functionality", "feature"),
    (r"methodology", "method"),
    (r"nevertheless|nonetheless", "but, still"),
    (r"notwithstanding", "despite"),
    (r"consequently", "so"),
    (r"pertaining to|with regard to|in regards? to", "about"),
    (r"in the event that", "if"),
    (r"at this point in time", "now"),
    (r"sufficient(ly)?", "enough"),
    (r"initiat(e|es|ed|ing)", "start"),
    (r"modification(s)?", "change"),
    (r"optimal", "best"),
    (r"assist(s|ed|ing|ance)?", "help"),
    (r"obtain(s|ed|ing)?", "get"),
    (r"possess(es|ed|ing)?", "have"),
    (r"remainder", "rest"),
    (r"retain(s|ed|ing)?", "keep"),
    (r"transmit(s|ted|ting)?", "send"),
    (r"inquir(e|es|ed|ing)", "ask"),
    (r"henceforth", "from now on"),
    (r"thereby", "so"),
    (r"aforementioned", "this, that"),
    (r"expedit(e|es|ed|ing)", "speed up"),
    (r"finaliz(e|es|ed|ing)", "finish"),
    (r"mitigat(e|es|ed|ing)", "reduce"),
    (r"necessitat(e|es|ed|ing)", "need"),
    (r"preliminary", "first"),
    (r"streamlin(e|es|ed|ing)", "simplify"),
    (r"substantial(ly)?", "large, much"),
    (r"in a nutshell", "in short"),
    (r"at the end of the day", "finally"),
    (r"low[- ]hanging fruit", "easy win"),
    (r"move the needle", "make a difference"),
    (r"circle back", "return to"),
    (r"touch base", "talk"),
    (r"deep dive", "close look"),
    (r"game[- ]changer", "big change"),
    (r"kick(s|ed|ing)? off", "start"),
    (r"figur(e|es|ed|ing) out", "find, learn"),
    (r"look(s|ed|ing)? into", "check"),
    (r"carr(y|ies|ied|ying) out", "do"),
    (r"c[oa]m(e|es|ing)? up with", "make, find"),
    (r"get(s|ting)? rid of|got rid of", "remove"),
    (r"put(s|ting)? off", "delay"),
    (r"point(s|ed|ing)? out", "show, say"),
    (r"wrap(s|ped|ping)? up", "finish"),
    (r"end(s|ed|ing)? up", "become, result"),
    (r"r[ua]n(s|ning)? into", "meet, hit"),
]
PLAIN_RES = [(re.compile(r"\b(?:%s)\b" % pat), pat, sug) for pat, sug in PLAIN_WORDS]

DASH_CHARS = {"—": "em dash", "–": "en dash", "―": "horizontal bar",
              "‒": "figure dash"}
ABBREVIATIONS = ["e.g.", "i.e.", "etc.", "vs.", "Mr.", "Mrs.", "Dr.", "approx.", "a.m.", "p.m.", "cf.",
                 "Fig.", "fig.", "Inc.", "Ltd.", "St."]
SENTENCE_END_ABBREVIATIONS = {"etc.", "a.m.", "p.m."}
# A status line led by a short label ("trial-flow.png: 1080x3247", "npm ci: clean") is its own line.
LABEL_RE = re.compile(r"^\S+(?:\s\S+){0,3}:\s")
END_RE = re.compile(r"[.!?:][\"')\]\u201d]*$")

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
TABLE_RE = re.compile(r"^\s*\|")
ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# A URL stops before trailing sentence punctuation, so "at https://x.y/abc. Then" still splits.
URL_RE = re.compile(r"(?:https?://|www\.)\S+?(?=[.,;:!?)\]\"'\u201d\u2019]*(?:\s|$))")
# Any sentence end followed by a space splits, even before a lowercase name ("npm ci ran").
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])([\"')\]\u201d\u2019]*)\s+(?=\S)")
ACRONYM_RE = re.compile(r"(?:[A-Za-z]\.){2,}$")  # U.S., a.m.: not a sentence end before a lowercase word
JOIN_WORDS = {"and", "or", "but", "to", "the", "a", "an", "of", "with", "for", "in", "on", "at", "by",
              "from", "that", "which", "is", "are", "was", "were", "as", "than", "into", "via"}
SPACED_HYPHEN_RE = re.compile(r"(?<=\S) -{1,2} (?=\S)")
QUOTED_RE = re.compile(r"\"[^\"]*\"|\u201c[^\u201d]*\u201d")


def parse_units(text):
    """Split markdown into gradable units: (kind, first_line_no, text).

    kind is one of heading, table, item, para. Fenced code is dropped.
    """
    units = []
    cur = None  # [kind, line_no, [lines]]
    in_fence = False

    def flush():
        nonlocal cur
        if cur is not None:
            units.append((cur[0], cur[1], " ".join(cur[2]).strip()))
            cur = None

    lines = text.splitlines()
    front_end = 0
    if lines and lines[0].strip() == "---":  # YAML frontmatter is metadata, not prose
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                front_end = i + 1
                break
    for no, line in enumerate(lines, start=1):
        if no <= front_end:
            continue
        if FENCE_RE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            flush()
            continue
        stripped = re.sub(r"^\s*>\s?", "", line)
        if HEADING_RE.match(stripped):
            flush()
            units.append(("heading", no, HEADING_RE.sub("", stripped).strip()))
            continue
        if TABLE_RE.match(stripped):
            flush()
            units.append(("table", no, stripped.strip()))
            continue
        m = ITEM_RE.match(stripped)
        if m:
            flush()
            cur = ["item", no, [stripped[m.end():].strip()]]
            continue
        if cur is not None:
            # A line break after a finished sentence starts a new paragraph: Telegram shows every
            # line break. A markdown line that wraps mid-sentence, or an indented line, continues.
            prev = cur[2][-1]
            last_word = (prev.split() or [""])[-1].lower()
            starts_new = END_RE.search(prev) or LABEL_RE.match(stripped.strip()) or (
                not re.match(r"[a-z]", stripped.strip()) and not prev.endswith(",") and last_word not in JOIN_WORDS)
            if starts_new and not re.match(r"^\s{2,}\S", line):
                flush()
                cur = ["para", no, [stripped.strip()]]
            else:
                cur[2].append(stripped.strip())
        else:
            cur = ["para", no, [stripped.strip()]]
    flush()
    return units


def normalize(text):
    """Prose view of a unit: code spans and URLs become one-word placeholders."""
    t = INLINE_CODE_RE.sub(" CODESPAN ", text)
    t = LINK_RE.sub(r"\1", t)
    t = URL_RE.sub(" URLTOKEN ", t)
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"\1", t)
    for abbr in ABBREVIATIONS:
        bare = abbr.replace(".", "")
        if abbr in SENTENCE_END_ABBREVIATIONS:  # "..., etc. The API" still ends the sentence
            t = re.sub(re.escape(abbr) + r"(?!\s+[A-Z])", bare, t)
        else:
            t = t.replace(abbr, bare)
    t = re.sub(r"\bNo\.(?=\s*\d)", "No", t)  # "No. 5" is a number; "is No." ends a sentence
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(prose):
    out, start = [], 0
    for m in SENT_SPLIT_RE.finditer(prose):
        left = prose[start:m.start()] + m.group(1)
        words = left.split()
        last = words[-1].rstrip("\"')]\u201d\u2019") if words else ""
        if ACRONYM_RE.search(last) and prose[m.end():m.end() + 1].islower():
            continue
        out.append(left.strip())
        start = m.end()
    out.append(prose[start:].strip())
    return [s for s in out if s]


def words_of(sentence):
    return [w for w in sentence.split() if re.search(r"[A-Za-z0-9]", w)]


def clean_word(w):
    return re.sub(r"^[^\w']+|[^\w']+$", "", w)


def is_step(sentence):
    ws = words_of(sentence)
    return bool(ws) and clean_word(ws[0]).lower() in IMPERATIVES


def find_passive(sentence):
    toks = [clean_word(w).lower().replace("’", "'") for w in sentence.split()]
    hits = []
    for i, tok in enumerate(toks):
        if tok not in BE_FORMS and tok not in GET_FORMS:
            continue
        if i > 0 and toks[i - 1] == "there":
            continue  # "there is limited time" is existential, not passive
        j = i + 1
        while j < len(toks) and j - i <= 3 and (toks[j] in GAP_WORDS or (toks[j].endswith("ly") and len(toks[j]) > 3)):
            j += 1
        if j >= len(toks):
            continue
        w = toks[j]
        participle = w in IRREGULAR_PARTICIPLES or (
            w.endswith("ed") and len(w) > 3 and w not in ED_NOT_PARTICIPLE and w.isalpha())
        state = w in STATE_WORDS and (j + 1 >= len(toks) or toks[j + 1] != "by")  # "is done", not "is done by X"
        if participle and not state and not (tok in GET_FORMS and w == "started"):  # "get started" is an idiom
            hits.append(" ".join(toks[i:j + 1]))
    return hits


def check_dashes(raw_line, no, findings):
    line = INLINE_CODE_RE.sub("", raw_line)
    line = URL_RE.sub("", line)
    for ch, name in DASH_CHARS.items():
        n = line.count(ch)
        if n:
            findings.append({"rule": "dash", "line": no, "count": n,
                             "message": "%s x%d: use a comma, colon, period, parentheses or 'to'" % (name, n),
                             "excerpt": raw_line.strip()[:120]})
    body = ITEM_RE.sub("", line, count=1)
    body = TABLE_RE.sub("", body)
    if SPACED_HYPHEN_RE.search(body) and not re.match(r"^\s*\|", line):
        findings.append({"rule": "dash", "line": no, "count": len(SPACED_HYPHEN_RE.findall(body)),
                         "message": "spaced hyphen used as a dash: use a comma, colon or period",
                         "excerpt": raw_line.strip()[:120]})


def lint(text, opts=None):
    o = dict(DEFAULTS)
    o.update(opts or {})
    findings = []
    stats = {"sentences": 0, "words": 0, "max_words": 0}

    # Dashes are checked line by line on the raw text, outside fenced code.
    in_fence = False
    for no, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            check_dashes(line, no, findings)

    for kind, no, raw in parse_units(text):
        if kind in ("heading", "table"):
            continue
        prose = normalize(raw)
        sentences = split_sentences(prose)
        unit_words = 0
        for s in sentences:
            ws = words_of(s)
            n = len(ws)
            unit_words += n
            stats["sentences"] += 1
            stats["words"] += n
            stats["max_words"] = max(stats["max_words"], n)
            step = is_step(s)
            limit = o["step_max"] if step else o["desc_max"]
            if n > limit:
                findings.append({"rule": "sentence-length", "line": no, "words": n, "limit": limit,
                                 "kind": "step" if step else "description",
                                 "message": "%d words, limit %d (%s): split it" % (n, limit, "step" if step else "description"),
                                 "excerpt": s[:120]})
            # Quoted text is cited, not authored: the word and voice checks skip it.
            unquoted = QUOTED_RE.sub(" QUOTED ", s)
            for phrase in find_passive(unquoted):
                findings.append({"rule": "passive", "line": no, "phrase": phrase,
                                 "message": "'%s' looks passive: say who does it" % phrase,
                                 "excerpt": s[:120]})
            low = unquoted.lower()
            flagged_words = set()
            for rx, pat, sug in PLAIN_RES:
                for m in rx.finditer(low):
                    flagged_words.update(m.group(0).split())
                    findings.append({"rule": "plain-word", "line": no, "word": m.group(0), "suggestion": sug,
                                     "message": "'%s': use %s" % (m.group(0), sug), "excerpt": s[:120]})
            for w in words_of(unquoted):
                cw = clean_word(w)
                if (len(cw) >= o["long_word"] and cw.isalpha() and cw.lower() not in flagged_words
                        and cw.lower() not in TECH_LONG_WORDS
                        and cw not in ("CODESPAN", "URLTOKEN", "QUOTED") and not re.search(r"[a-z][A-Z]", cw)
                        and not cw.isupper()):
                    findings.append({"rule": "long-word", "line": no, "word": cw,
                                     "message": "'%s' (%d letters): use a shorter, plainer word" % (cw, len(cw)),
                                     "excerpt": s[:120]})
        if len(sentences) > o["para_sentences"] or unit_words > o["para_words"]:
            findings.append({"rule": "paragraph", "line": no, "sentences": len(sentences), "words": unit_words,
                             "message": "%s has %d sentences, %d words (limits %d sentences, %d words): split it"
                                        % ("list item" if kind == "item" else "paragraph", len(sentences), unit_words,
                                           o["para_sentences"], o["para_words"]),
                             "excerpt": raw[:120]})

    findings.sort(key=lambda f: (f["line"], f["rule"]))
    counts = {}
    for f in findings:
        counts[f["rule"]] = counts.get(f["rule"], 0) + 1
    avg = round(stats["words"] / stats["sentences"], 1) if stats["sentences"] else 0.0
    return {"clean": not findings, "findings": findings, "counts": counts,
            "stats": {"sentences": stats["sentences"], "avg_words": avg, "max_words": stats["max_words"]},
            "limits": o}


def render_text(result, name):
    out = []
    for f in result["findings"]:
        out.append("L%-4d %-16s %s | %s" % (f["line"], f["rule"], f["message"], f.get("excerpt", "")))
    st, lim = result["stats"], result["limits"]
    tail = "%d sentences, avg %.1f words, max %d (limits: step %d, description %d)" % (
        st["sentences"], st["avg_words"], st["max_words"], lim["step_max"], lim["desc_max"])
    if result["clean"]:
        out.append("ste-lint: CLEAN %s: %s" % (name, tail))
    else:
        by = ", ".join("%s %d" % kv for kv in sorted(result["counts"].items()))
        out.append("ste-lint: %d findings in %s (%s): %s" % (len(result["findings"]), name, by, tail))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint text against the STE-lite card.")
    ap.add_argument("file", nargs="?", default="-")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--step-max", type=int, default=DEFAULTS["step_max"])
    ap.add_argument("--desc-max", type=int, default=DEFAULTS["desc_max"])
    ap.add_argument("--para-sentences", type=int, default=DEFAULTS["para_sentences"])
    ap.add_argument("--para-words", type=int, default=DEFAULTS["para_words"])
    ap.add_argument("--long-word", type=int, default=DEFAULTS["long_word"])
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if a.file == "-":
            text, name = sys.stdin.read(), "stdin"
        else:
            with open(a.file, encoding="utf-8") as fh:
                text, name = fh.read(), a.file
    except (OSError, UnicodeDecodeError) as e:
        print("ste-lint: cannot read %s: %s" % (a.file, e), file=sys.stderr)
        return 2
    opts = {"step_max": a.step_max, "desc_max": a.desc_max, "para_sentences": a.para_sentences,
            "para_words": a.para_words, "long_word": a.long_word}
    result = lint(text, opts)
    if a.json:
        result["file"] = name
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result, name))
    return 0 if result["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
