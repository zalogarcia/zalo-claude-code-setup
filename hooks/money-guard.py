#!/usr/bin/env python3
r"""PreToolUse guard: routes to live Stripe money operations, other than the
one sanctioned wrapper.

Why this exists
---------------
2026-08-30. A customer refund revealed that the live Stripe secret key was in
the `env` block of ~/.claude/settings.local.json, so every session, every
subagent and every unattended background worker inherited the ability to move
real money. The refund (one $7.00 charge; ids deliberately not written down,
this repo mirrors publicly) was correct and intended, but it was issued by
running

    python3 /tmp/stripe-refund.py

which is the whole lesson: a hook that inspects command text would have seen an
interpreter and a path. The Stripe call was inside the file.

So be honest about what this file is. Three layers were built; they are not
equal:

  1. CUSTODY — the real control. The key is out of the environment and lives
     only in ~/.config/stripe/live-key (mode 600, dir 700). Code that never
     receives the key cannot spend money, no matter what it runs.
  2. ~/.claude/scripts/stripe-money.py — the only reader of that file. Re-reads
     every object before touching it, asserts amount/customer/state, sends an
     Idempotency-Key, refuses above $200 without an explicit confirmation, and
     appends to ~/.claude/logs/stripe-actions.jsonl.
  3. THIS HOOK — a backstop. It closes the obvious routes (raw curl at
     api.stripe.com, the `stripe` CLI, inline SDK calls, reading the key file,
     a key pasted inline). It is a tripwire on the paths an agent would
     actually take, NOT a sandbox.

What it BLOCKS
--------------
  * api.stripe.com with a mutating method or a request body, and any of the
    money-moving paths regardless of method (/v1/refunds, /refund, payment
    intent cancel, subscription DELETE/cancel, credit notes, invoice void,
    charge capture, customer DELETE, and also payouts / transfers / topups,
    which move money and were not on the original list).
  * the `stripe` CLI, deny-by-default: only an explicit read-only verb set is
    allowed through.
  * inline SDK mutations in a `-c` / `-e` one-liner or an interpreter heredoc
    (stripe.Refund.create, refunds.create, subscriptions.del, ...).
  * a literal sk_live / rk_live anywhere in the command, including inside a
    heredoc body. Absolute: there is no shape in which an agent should be
    typing a live key.
  * any reference to the key file (`live-key`, or a glob over .config/stripe).
    Absolute for the same reason.
  * printing or piping a STRIPE_*_KEY environment variable.

What it ALLOWS
--------------
  * `stripe-money.py` invocations — but only when the wrapper is the thing
    actually being executed, not merely mentioned in a string.
  * read-only GETs to api.stripe.com on non-money paths.
  * everything unrelated.

Obfuscation resistance (same shape as tmux-peer-guard.py)
---------------------------------------------------------
  shlex tokenising with punctuation_chars so `;` and `&&` split correctly even
  unspaced; per-segment checks so `echo hi; curl ...` cannot launder a call;
  `bash -c "..."` unwrapped one level; env-assignment and wrapper prefixes
  (env/sudo/nohup/xargs/time/caffeinate) stripped; `-X POST` / `-XPOST` /
  `--request=POST` all recognised; heredoc bodies dropped for prose but SCANNED
  when the heredoc feeds an interpreter; unparseable quoting fails closed.

LIMITS, stated plainly rather than half-guarded
------------------------------------------------
  * It cannot see inside a script file. `python3 /tmp/x.py` is opaque. This is
    the exact route the 2026-08-30 refund took.
  * It cannot see through base64/eval, variable indirection for the binary
    name, or a curl config file (`curl -K /tmp/cfg`) that carries the URL.
  * It is defeated by anything that already holds the key.
  Layer 1 is what makes those survivable. Do not upgrade this hook's status in
  your head just because it blocked something.

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import json
import os
import re
import shlex
import sys

WRAPPER = "stripe-money.py"
WRAPPER_PATH = "/Users/zalo/.claude/scripts/stripe-money.py"
KEY_FILE_HINT = "~/.config/stripe/live-key"

OPERATORS = {"&&", "||", ";", "|", "&", "\n", "(", ")"}
WRAPPERS = {"env", "sudo", "nohup", "command", "xargs", "time", "caffeinate",
            "exec", "doas", "stdbuf", "setsid"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
INTERPRETERS = SHELLS | {"python", "python3", "python2", "node", "nodejs",
                         "deno", "bun", "ruby", "perl", "php", "osascript"}
NET_TOOLS = {"curl", "wget", "http", "https", "httpie", "xh", "hurl", "nc", "ncat"}
# Commands that could carry a secret off the box or onto disk.
EXFIL_HEADS = {"echo", "printf", "print", "cat", "tee", "base64", "xxd", "od",
               "openssl", "pbcopy", "mail", "sendmail", "printenv"} | NET_TOOLS | INTERPRETERS

HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# A live key pasted anywhere. Case-insensitive so a shouted SK_LIVE_ in a doc
# is caught too; there is no legitimate reason for either.
KEY_LITERAL_RE = re.compile(r"(?:sk|rk)_live", re.IGNORECASE)

# The key file. `live-key` alone is specific enough that false positives are
# effectively nil, and it survives `cd ~/.config/stripe && cat live-key`.
KEY_PATH_RE = re.compile(r"live-key|(?:\.)?config/stripe/[*?]", re.IGNORECASE)

STRIPE_ENV_RE = re.compile(r"\$\{?STRIPE_[A-Za-z0-9_]*", re.IGNORECASE)

# Paths that move money or destroy access, regardless of HTTP method.
MONEY_PATHS = [
    (r"/v1/refunds", "creates a refund"),
    (r"/refunds?\b", "refund endpoint"),
    (r"/v1/payment_intents/[^/\s\"']+/cancel", "cancels a payment intent"),
    (r"/v1/payment_intents/[^/\s\"']+/capture", "captures a payment intent"),
    (r"/v1/credit_notes", "issues a credit note"),
    (r"/v1/invoices/[^/\s\"']+/void", "voids an invoice"),
    (r"/v1/charges/[^/\s\"']+/capture", "captures a charge"),
    (r"/v1/payouts", "moves money to a bank account"),
    (r"/v1/transfers", "moves money to a connected account"),
    (r"/v1/topups", "moves money into the Stripe balance"),
    (r"/v1/subscriptions/[^/\s\"']+/cancel", "cancels a subscription"),
]
MONEY_PATH_RES = [(re.compile(p, re.IGNORECASE), why) for p, why in MONEY_PATHS]

SUBSCRIPTION_PATH_RE = re.compile(r"/v1/subscriptions", re.IGNORECASE)
CUSTOMER_PATH_RE = re.compile(r"/v1/customers", re.IGNORECASE)

MUTATING_METHODS = {"POST", "DELETE", "PUT", "PATCH"}
DATA_FLAGS = ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii",
              "--data-urlencode", "--json", "-F", "--form", "-T", "--upload-file")

# `stripe` CLI: deny-by-default. Only these first-words are read-only enough.
STRIPE_CLI_SAFE_FIRST = {
    "get", "listen", "logs", "login", "logout", "config", "version", "--version",
    "-v", "help", "--help", "-h", "open", "status", "community", "docs",
    "completion", "samples", "resources", "whoami", "feedback", "upgrade",
    "trigger", "fixtures",
}
STRIPE_CLI_SAFE_SECOND = {"list", "retrieve", "search"}

# Inline SDK mutations, node and python spellings.
SDK_PATTERNS = [
    (r"\brefunds?\s*\.\s*create\b", "creates a refund (SDK)"),
    (r"\bRefunds?\s*\.\s*create\b", "creates a refund (SDK)"),
    (r"\bsubscriptions?\s*\.\s*(?:del|delete|cancel)\b", "cancels a subscription (SDK)"),
    (r"\bSubscriptions?\s*\.\s*(?:delete|cancel)\b", "cancels a subscription (SDK)"),
    (r"\bpayment_?[Ii]ntents?\s*\.\s*cancel\b", "cancels a payment intent (SDK)"),
    (r"\bPaymentIntents?\s*\.\s*cancel\b", "cancels a payment intent (SDK)"),
    (r"\bcredit_?[Nn]otes?\s*\.\s*create\b", "issues a credit note (SDK)"),
    (r"\bCreditNotes?\s*\.\s*create\b", "issues a credit note (SDK)"),
    (r"\binvoices?\s*\.\s*void", "voids an invoice (SDK)"),
    (r"\bInvoices?\s*\.\s*void", "voids an invoice (SDK)"),
    (r"\bcharges?\s*\.\s*capture\b", "captures a charge (SDK)"),
    (r"\bCharges?\s*\.\s*capture\b", "captures a charge (SDK)"),
    (r"\bpayouts?\s*\.\s*create\b", "creates a payout (SDK)"),
    (r"\bPayouts?\s*\.\s*create\b", "creates a payout (SDK)"),
    (r"\btransfers?\s*\.\s*create\b", "creates a transfer (SDK)"),
    (r"\bTransfers?\s*\.\s*create\b", "creates a transfer (SDK)"),
    (r"\bcustomers?\s*\.\s*(?:del|delete)\b", "deletes a customer (SDK)"),
    (r"\bCustomers?\s*\.\s*delete\b", "deletes a customer (SDK)"),
]
SDK_RES = [(re.compile(p), why) for p, why in SDK_PATTERNS]

BLOCK_FOOTER = f"""
The one sanctioned path for live Stripe money operations:

  python3 {WRAPPER_PATH} show --charge ch_...
  python3 {WRAPPER_PATH} show --subscription sub_...
  python3 {WRAPPER_PATH} refund --charge ch_... --expect-amount <cents> --dry-run
  python3 {WRAPPER_PATH} refund --charge ch_... --expect-amount <cents> \\
      [--expect-customer cus_...] [--reason requested_by_customer] [--i-confirm <cents>]
  python3 {WRAPPER_PATH} cancel-subscription --subscription sub_... \\
      --expect-customer cus_... --i-confirm sub_...

It re-reads the object from Stripe before acting, asserts the amount and
customer you claimed, sends an Idempotency-Key, refuses at/above $200.00
without --i-confirm, treats already-done as a clean no-op, and appends to
~/.claude/logs/stripe-actions.jsonl. Always run it with --dry-run first.

Be clear about what this hook is. It reads COMMAND TEXT ONLY, so it
cannot see inside a script file. On 2026-08-30 a real refund was issued by
`python3 /tmp/stripe-refund.py`, and a hook like this one would have seen an
interpreter and a path, nothing else. The control that actually protects the
money is CUSTODY: the live key is no longer in any environment, it lives only
in {KEY_FILE_HINT} (mode 600), and {WRAPPER} is the only
thing that reads it. This hook just closes the easy routes.

There is no in-band override. If a money operation genuinely needs to happen
and the wrapper cannot express it, say so and let Zalo run it in his own
terminal. Do not rewrite the command to get around this guard — report the
block."""


def deny(reason, extra=None):
    lines = [f"BLOCKED (money-guard): {reason}"]
    if extra:
        lines += ["", extra]
    lines.append(BLOCK_FOOTER)
    print("\n".join(lines), file=sys.stderr)
    sys.exit(2)


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def split_heredocs(command):
    """Return (text_without_bodies, [shell bodies], [source-code bodies]).

    Prose that merely MENTIONS a Stripe endpoint (a brief, a rules file, this
    hook's own docstring) must not be read as a call — that is the mistake
    npm-install-guard already paid for, so ordinary heredoc bodies are dropped.
    But a heredoc piped INTO an interpreter is direct execution, so it is kept.

    The two kinds are kept apart on purpose. A body fed to sh/bash IS shell and
    gets the full segment treatment. A body fed to python/node is source code
    in another language, and re-segmenting it as shell produces nonsense — this
    hook's own first version denied a patch script because the Python line
    `"stripe" in low` tokenised into a segment whose head was the word
    `stripe`. Source bodies get the text rules only.
    """
    lines = command.splitlines()
    kept, shell_bodies, code_bodies, i = [], [], [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        m = HEREDOC_RE.search(line)
        i += 1
        if not m:
            continue
        delim = m.group(2)
        body = []
        while i < len(lines) and lines[i].strip() != delim:
            body.append(lines[i])
            i += 1
        if i < len(lines):
            i += 1  # consume the terminator
        kind = heredoc_target(line)
        if kind == "shell":
            shell_bodies.append("\n".join(body))
        elif kind == "code":
            code_bodies.append("\n".join(body))
    return "\n".join(kept), shell_bodies, code_bodies


def heredoc_target(line):
    """'shell' | 'code' | None — what is this heredoc being fed to?"""
    try:
        toks = tokenize(line)
    except ValueError:
        return "shell"  # cannot tell -> treat as executed shell, fail closed
    for seg in split_segments(toks):
        seg = strip_prefixes(seg)
        if not seg:
            continue
        head = os.path.basename(seg[0])
        if head in SHELLS:
            return "shell"
        if head in INTERPRETERS:
            return "code"
    return None


def tokenize(text):
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def split_segments(tokens):
    out, cur = [], []
    for tok in tokens:
        if tok in OPERATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        out.append(cur)
    return out


def segments(command, depth=0):
    """Shell command -> list of token lists, one per sub-command."""
    out = []
    for line in command.splitlines():
        if not line.strip():
            continue
        try:
            tokens = tokenize(line)
        except ValueError:
            # Unbalanced quoting. Do not sail past it; fall back to a naive
            # split so the checks still see the words.
            tokens = line.split()
        out.extend(split_segments(tokens))

    # `bash -c "..."` is shell, so unwrap it. `python3 -c "..."` is NOT shell
    # and is deliberately not re-segmented: its payload stays a single token,
    # which means the endpoint and SDK text rules still see every character of
    # it, without a Python string being mistaken for a shell command.
    if depth < 2:
        for seg in list(out):
            if (len(seg) >= 3 and os.path.basename(seg[0]) in SHELLS
                    and seg[1].startswith("-") and "c" in seg[1]):
                out.extend(segments(seg[2], depth + 1))
    return out


def strip_prefixes(seg):
    """Drop leading FOO=bar assignments and wrapper commands."""
    i = 0
    while i < len(seg) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i])
                            or os.path.basename(seg[i]) in WRAPPERS):
        i += 1
    return seg[i:]


def is_wrapper_invocation(seg):
    """True only when stripe-money.py is the thing being EXECUTED.

    Deliberately not "the token appears somewhere": a comment or a string
    mentioning the wrapper inside `python3 -c "..."` must not launder a call.
    """
    seg = strip_prefixes(seg)
    if not seg:
        return False
    head = os.path.basename(seg[0])
    if head == WRAPPER:
        return True
    if head in INTERPRETERS:
        for tok in seg[1:]:
            if tok.startswith("-"):
                continue
            return os.path.basename(tok) == WRAPPER
    return False


def http_method(seg):
    """Effective HTTP method of a curl-ish segment."""
    method = None
    forced_get = False
    for i, tok in enumerate(seg):
        low = tok.lower()
        if tok in ("-X", "--request") and i + 1 < len(seg):
            method = seg[i + 1].upper()
        elif tok.startswith("--request="):
            method = tok.split("=", 1)[1].upper()
        elif tok.startswith("-X") and len(tok) > 2:
            method = tok[2:].upper()
        elif low in ("-g", "--get"):
            forced_get = True
        elif low in ("--head", "-i", "--include"):
            pass
    if method:
        return method
    if forced_get:
        return "GET"
    for tok in seg:
        if tok in DATA_FLAGS or any(tok.startswith(f + "=") for f in DATA_FLAGS):
            return "POST"  # curl implies POST when a body is present
    return "GET"


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_key_literal(raw):
    if KEY_LITERAL_RE.search(raw):
        deny(
            "the command contains a literal live Stripe key prefix (sk_live / rk_live)",
            "A live key must never appear in a command line: it lands in shell history, in\n"
            "the transcript, and in `ps` while it runs. If you are auditing for leaked keys,\n"
            "use the Grep tool (not Bash) — it does not go through this hook. If a key needs\n"
            "to be rotated or re-stored, Zalo does that in his own terminal.",
        )


def check_key_path(raw):
    if KEY_PATH_RE.search(raw):
        deny(
            f"the command references the live key file ({KEY_FILE_HINT})",
            f"{WRAPPER} is the only thing that reads that file, and it finds the path itself —\n"
            "it never takes it as an argument, so no legitimate command needs to name it.\n"
            "Nothing else should read it: a key that has been cat'ed into a transcript or a\n"
            "variable is a key that has left custody.",
        )


def check_stripe_env(seg, raw_seg):
    head = os.path.basename(seg[0]) if seg else ""
    # `$STRIPE_API_KEY` anywhere, or a bare STRIPE_* name handed to printenv/env.
    referenced = bool(STRIPE_ENV_RE.search(raw_seg))
    named = head in ("printenv", "env") and bool(
        re.search(r"\bSTRIPE_[A-Za-z0-9_]*", raw_seg))
    if not (referenced or named):
        return
    redirects = any(t in (">", ">>") for t in seg)
    if named or head in EXFIL_HEADS or redirects:
        deny(
            f"the command would print or pipe a STRIPE_* environment variable (`{head or 'redirect'}`)",
            "The live key is deliberately no longer in the environment. Reading it back out\n"
            "of one — or writing it to a file — recreates exactly the exposure this setup\n"
            "was built to remove.",
        )


ENV_DUMP_RE = re.compile(r"(?:^|[;&|(]|\s)\s*(?:env|printenv|set|export)\s*\|", re.MULTILINE)

# BSD flag bundles without a leading dash: `ps auxe`, `ps axe`, `ps ewww`.
PS_BSD_ENV_RE = re.compile(r"^[acefjlmrsuvwxSH]*e[acefjlmrsuvwxSH]*$")


def check_ps_env(seg):
    """`ps -E` prints every process's full ENVIRONMENT to its own user.

    Found empirically on 2026-08-30: with the key still in settings.local.json,
    six long-lived MCP server processes carried STRIPE_API_KEY in their
    environment, and `ps -ww -E -o command` handed it to anything that asked.
    Removing the key from settings.local.json does not clear those — they hold
    it until they are restarted — so this route has to be closed on its own.
    It is also a general secret-dumper: every token on the box, not just
    Stripe's.

    `-e` (all processes) and `-ef` are NOT this: on macOS/BSD only capital -E,
    or a dash-less BSD bundle containing `e`, means "print the environment".
    """
    if not seg or os.path.basename(seg[0]) != "ps":
        return
    for tok in seg[1:]:
        env_flag = (tok == "--environment"
                    or (tok.startswith("-") and not tok.startswith("--") and "E" in tok)
                    or (not tok.startswith("-") and PS_BSD_ENV_RE.fullmatch(tok)))
        if env_flag:
            deny(f"`ps {tok}` dumps the full ENVIRONMENT of every process on the box",
                 "On 2026-08-30 that included the live Stripe key, held by six long-lived\n"
                 "MCP server processes that inherited it at session start. It also exposes\n"
                 "every other token on this machine. If you need to know whether a variable\n"
                 "is set, test it in your own shell without printing it:\n"
                 '  [ -n "$SOME_VAR" ] && echo set || echo unset')


def check_env_grep(text):
    """`env | grep -i stripe` — the segment splitter cannot see this, because
    `env` is also a wrapper prefix and strips to an empty segment."""
    low = text.lower()
    if ENV_DUMP_RE.search(text) and "stripe" in low and (
            "grep" in low or "rg" in low.split()):
        deny("the command dumps the environment and greps it for Stripe",
             "If this is a check that the key is GONE from the environment, that is what\n"
             f"`python3 {WRAPPER_PATH} show --charge ch_...` proves positively: it works\n"
             "because it reads the key file, not the environment.")


def check_stripe_cli(seg):
    if not seg or os.path.basename(seg[0]) != "stripe":
        return
    args = [t for t in seg[1:] if not t.startswith("-")]
    flags_only = [t for t in seg[1:] if t.startswith("-")]
    if not args:
        if any(f in ("--version", "-v", "--help", "-h") for f in flags_only) or not flags_only:
            return
        return
    first = args[0].lower()
    if first in STRIPE_CLI_SAFE_FIRST:
        return
    if len(args) >= 2 and args[1].lower() in STRIPE_CLI_SAFE_SECOND:
        return
    verb = args[1].lower() if len(args) >= 2 else ""
    detail = f"`stripe {first} {verb}`".strip().rstrip("`") + "`"
    deny(f"the Stripe CLI is being used for a non-read-only operation: {detail}",
         "The CLI talks to the live account with whatever key it is configured with, and\n"
         "nothing about that invocation is asserted, bounded, idempotent or logged.\n"
         "(Read-only CLI verbs — get / list / retrieve / logs / listen — are allowed.)")


def check_endpoints(seg, raw_seg, host_present):
    """Mutating HTTP at Stripe, from a segment that can actually make requests."""
    head = os.path.basename(seg[0]) if seg else ""
    is_net = head in NET_TOOLS or head in INTERPRETERS
    seg_host = "api.stripe.com" in raw_seg.lower()
    # A path rule only fires from something that can execute a request, or when
    # the Stripe host is present somewhere in the command (variable indirection
    # like B=https://api.stripe.com; curl $B/v1/refunds).
    if not (is_net or seg_host or (host_present and head in NET_TOOLS)):
        return
    if not (seg_host or host_present or "stripe" in raw_seg.lower()):
        return

    method = http_method(seg)

    for pattern, why in MONEY_PATH_RES:
        if pattern.search(raw_seg):
            deny(f"the command hits a Stripe endpoint that {why} ({pattern.pattern})",
                 f"HTTP method read as {method}. Money-moving endpoints are blocked here at\n"
                 "any method, because a GET that looks harmless in review is one edited\n"
                 "character away from a POST.")

    if SUBSCRIPTION_PATH_RE.search(raw_seg) and (
            method == "DELETE" or "cancel" in raw_seg.lower()):
        deny("the command cancels or deletes a Stripe subscription",
             "Canceling access is not recoverable by re-running anything, which is why the\n"
             "wrapper requires --i-confirm repeating the subscription id.")

    if CUSTOMER_PATH_RE.search(raw_seg) and method == "DELETE":
        deny("the command DELETEs a Stripe customer",
             "Deleting a customer cancels their subscriptions and is irreversible. The\n"
             "wrapper deliberately does not implement it: it needs a human.")

    if seg_host and method in MUTATING_METHODS:
        deny(f"a mutating {method} request to api.stripe.com",
             "Any write to the live Stripe API is a money operation until proven otherwise.\n"
             "Read-only GETs to api.stripe.com are allowed; this was not one.")


def check_money_paths_text(text):
    """Endpoint rules applied to a blob of source code (an interpreter heredoc
    body), where there are no shell segments to walk."""
    for pattern, why in MONEY_PATH_RES:
        if pattern.search(text):
            deny(f"executed code hits a Stripe endpoint that {why} "
                 f"({pattern.pattern})",
                 "This was inside a heredoc piped to an interpreter, which is execution,\n"
                 "not documentation.")
    low = text.lower()
    if SUBSCRIPTION_PATH_RE.search(text) and ("delete" in low or "cancel" in low):
        deny("executed code cancels or deletes a Stripe subscription")
    if CUSTOMER_PATH_RE.search(text) and "delete" in low:
        deny("executed code DELETEs a Stripe customer")


def check_sdk(text):
    if "stripe" not in text.lower():
        return
    for pattern, why in SDK_RES:
        m = pattern.search(text)
        if m:
            deny(f"an inline Stripe SDK call that {why}: `{m.group(0)}`",
                 "Nothing about an inline SDK call is asserted, bounded, idempotent or\n"
                 "logged. If the wrapper cannot express what you need, that is a\n"
                 "conversation to have, not a one-liner to write.")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

PS_INVOCATION_RE = re.compile(r"(?:^|[;&|(`]|\s)ps\s+[-a-zA-Z]")


def relevant(command):
    """Cheap gate. `ps` is in here because a process-environment dump is a
    route to the key that never mentions Stripe by name."""
    low = command.lower()
    return ("stripe" in low or KEY_LITERAL_RE.search(command)
            or KEY_PATH_RE.search(command) or PS_INVOCATION_RE.search(command))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on a payload we cannot read
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = str(tool_input.get("command") or "")
    if not command.strip() or not relevant(command):
        return 0

    # 1. Absolute rules, scanned over the RAW text including heredoc bodies.
    #    A key or the key path written into a file is exactly as bad as one
    #    passed to a command.
    check_key_literal(command)
    check_key_path(command)

    # 2. Everything else: prose in a heredoc is not a call, but a heredoc fed
    #    to an interpreter is.
    stripped, shell_bodies, code_bodies = split_heredocs(command)
    host_present = any("api.stripe.com" in t.lower()
                       for t in [stripped] + shell_bodies + code_bodies)

    # Source fed to a non-shell interpreter: text rules only. Segmenting Python
    # or JS as if it were shell is what produced this hook's one real false
    # positive during development.
    for body in code_bodies:
        check_sdk(body)
        check_money_paths_text(body)

    # Shell (the command itself, plus any heredoc fed to sh/bash): full walk.
    for text in [stripped] + shell_bodies:
        check_sdk(text)
        check_env_grep(text)
        for seg in segments(text):
            seg = strip_prefixes(seg)
            if not seg:
                continue
            raw_seg = " ".join(seg)
            if is_wrapper_invocation(seg):
                continue
            check_stripe_cli(seg)
            check_endpoints(seg, raw_seg, host_present)
            check_stripe_env(seg, raw_seg)
            check_ps_env(seg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
