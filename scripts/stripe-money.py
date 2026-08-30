#!/usr/bin/env python3
r"""The ONLY sanctioned path for moving money in Zalo's live Stripe account.

Why this exists
---------------
2026-08-30: a customer refund revealed that the live secret key was sitting in
the `env` block of ~/.claude/settings.local.json, which means every Claude
session, every subagent and every unattended background worker inherited the
ability to move real money. The refund itself was correct and intended
(one $7.00 charge; the ids are deliberately not written down here, this repo
mirrors publicly) but it was issued by running

    python3 /tmp/stripe-refund.py

and that is the part that mattered: a PreToolUse Bash hook inspecting command
text would have seen `python3` and a path, nothing else. Pattern matching on
command strings is a tripwire, not a control.

The three layers, honestly labelled
-----------------------------------
  1. CUSTODY (the real control) — the key lives ONLY in
     ~/.config/stripe/live-key, mode 600 inside a 700 directory, and is NOT in
     any process environment. Code that never receives the key cannot spend
     money, whether or not any hook sees it.
  2. THIS SCRIPT — the one reader of that file. Every mutation is preceded by
     a fresh read of the object from Stripe, asserted against what the caller
     said they expected, bounded by a dollar ceiling, idempotent, and logged.
  3. ~/.claude/hooks/money-guard.py — blocks the OTHER routes (raw curl at
     api.stripe.com, the `stripe` CLI, inline SDK calls, reading the key
     file). It is a backstop. It cannot see inside a script file, so it is
     explicitly NOT the thing keeping the money safe. Layer 1 is.

Design rules this file obeys
----------------------------
  * Never act on an object it has not just read. Every mutating operation
    re-fetches the object and asserts id / amount / customer / state before
    doing anything.
  * Idempotency-Key on every mutation, derived deterministically from the
    operation and the object id, so a retry or a double invocation cannot
    produce a second refund inside Stripe's 24h idempotency window. After
    that window the pre-read "already refunded" check is what protects.
  * Already-done is a clean no-op with exit 0, never an error path. Nobody
    should ever be tempted to "force" it.
  * Full refunds only. Partial state is ambiguous, so it refuses and asks a
    human. `--expect-amount` asserts the CHARGE TOTAL, in cents, exactly.
  * Exactly one object id per invocation. Globs, comma lists and repeated
    flags are refused, so there is no shape in which this becomes a batch.
  * The key is never printed, never written to the log, never placed in argv
    and never placed in the environment. It reaches curl through `-K -`
    (config on stdin), so it is invisible to `ps` and to any process listing.
  * HTTP goes through curl, not urllib: this box's system python has no usable
    CA bundle (CERTIFICATE_VERIFY_FAILED on every https call). Do not "fix"
    that by disabling verification.

Exit codes
----------
  0  action performed, or already-done no-op, or dry-run, or read-only show
  1  REFUSED — an assertion failed, a ceiling was hit, a confirmation was
     missing, or an argument was malformed. Nothing was sent to Stripe.
  2  ERROR — could not read the key, could not reach Stripe, Stripe returned
     an error, or the response did not match what was asked for.

Usage
-----
  stripe-money.py show --charge ch_xxx
  stripe-money.py show --subscription sub_xxx
  stripe-money.py refund --charge ch_xxx --expect-amount 700 [--dry-run]
                         [--expect-customer cus_xxx] [--reason requested_by_customer]
                         [--i-confirm <cents>]          # required at/above $200.00
  stripe-money.py cancel-subscription --subscription sub_xxx \
                         --expect-customer cus_xxx --i-confirm sub_xxx [--dry-run]
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

KEY_PATH = os.path.expanduser("~/.config/stripe/live-key")
LOG_PATH = os.path.expanduser("~/.claude/logs/stripe-actions.jsonl")
API_BASE = "https://api.stripe.com/v1"

# Refunds at or above this refuse without an explicit --i-confirm that repeats
# the exact amount. $200.00.
REFUND_CEILING_CENTS = 20000

HTTP_TIMEOUT = 25

VALID_REASONS = {"duplicate", "fraudulent", "requested_by_customer"}

ID_PATTERNS = {
    "charge": re.compile(r"^ch_[A-Za-z0-9]{8,}$"),
    "subscription": re.compile(r"^sub_[A-Za-z0-9]{8,}$"),
    "customer": re.compile(r"^cus_[A-Za-z0-9]{8,}$"),
}

# Anything that hints at more than one object, or at shell interpretation
# reaching in here. Presence of any of these in an id argument is a refusal.
SUSPICIOUS = set("*?[]{}(),;&|<>$`'\"\\ \t\n")

SECRET_RE = re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{6,}")

EXIT_OK, EXIT_REFUSED, EXIT_ERROR = 0, 1, 2

_KEY_CACHE = None


# --------------------------------------------------------------------------
# output / logging — everything user-visible passes through scrub()
# --------------------------------------------------------------------------

def scrub(text):
    """Remove anything key-shaped, plus the exact live key if we hold it."""
    out = SECRET_RE.sub("[REDACTED-STRIPE-KEY]", str(text))
    if _KEY_CACHE:
        out = out.replace(_KEY_CACHE, "[REDACTED-STRIPE-KEY]")
    return out


def say(*parts):
    print(scrub(" ".join(str(p) for p in parts)))


def err(*parts):
    print(scrub(" ".join(str(p) for p in parts)), file=sys.stderr)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def audit(entry):
    """Append one JSON line to the audit log. Never raises into the caller."""
    try:
        d = os.path.dirname(LOG_PATH)
        os.makedirs(d, mode=0o700, exist_ok=True)
        entry = dict(entry)
        entry.setdefault("ts", now_iso())
        entry.setdefault("pid", os.getpid())
        line = scrub(json.dumps(entry, sort_keys=True, default=str))
        # A key-shaped string surviving scrub() would be a bug; belt and braces.
        if SECRET_RE.search(line) or (_KEY_CACHE and _KEY_CACHE in line):
            line = json.dumps({"ts": now_iso(), "outcome": "log_suppressed",
                               "detail": "entry contained key-shaped text"})
        with open(LOG_PATH, "a") as fh:
            fh.write(line + "\n")
        os.chmod(LOG_PATH, 0o600)
    except Exception as exc:  # logging must never break the operation
        err(f"warning: could not write audit log ({exc.__class__.__name__})")


def refuse(reason, entry=None, hint=None):
    e = dict(entry or {})
    e["outcome"] = "refused"
    e["detail"] = reason
    audit(e)
    err(f"REFUSED: {reason}")
    if hint:
        err("")
        err(hint)
    sys.exit(EXIT_REFUSED)


def fail(reason, entry=None):
    e = dict(entry or {})
    e["outcome"] = "error"
    e["detail"] = reason
    audit(e)
    err(f"ERROR: {reason}")
    sys.exit(EXIT_ERROR)


# --------------------------------------------------------------------------
# key custody
# --------------------------------------------------------------------------

def read_key():
    """Read the live key from its file. The ONLY place this file is read."""
    global _KEY_CACHE
    if _KEY_CACHE:
        return _KEY_CACHE
    if not os.path.isfile(KEY_PATH):
        fail(f"no key file at {KEY_PATH}. Custody of the live key is a manual, "
             "human step; this script will not look anywhere else for it "
             "(not the environment, not a .env, not a repo).")
    st = os.stat(KEY_PATH)
    if st.st_mode & 0o077:
        fail(f"{KEY_PATH} is readable by group or others (mode "
             f"{oct(st.st_mode & 0o777)}). Fix with: chmod 600 {KEY_PATH}")
    with open(KEY_PATH) as fh:
        key = fh.read().strip()
    if not key:
        fail(f"{KEY_PATH} is empty")
    if not re.fullmatch(r"[A-Za-z0-9_]+", key):
        # Also guarantees the key cannot break out of the curl config quoting.
        fail("key file does not contain a bare Stripe key "
             "(expected only letters, digits and underscores)")
    if not key.startswith(("sk_", "rk_")):
        fail("key file does not look like a Stripe secret or restricted key")
    _KEY_CACHE = key
    return key


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def child_env():
    """Environment for the curl child: no Stripe secret inherited.

    The key is supposed to be out of the environment entirely — that is layer
    1 and it is the control that matters. But this script must not DEPEND on
    that being true: during the transition the key was still in
    settings.local.json, and on macOS `ps -E` shows a process's environment to
    its own user, so an inherited copy is a real second exposure. Strip
    anything Stripe-named or key-shaped before spawning.
    """
    out = {}
    for k, v in os.environ.items():
        upper = k.upper()
        if upper.startswith("STRIPE"):
            continue
        if upper.endswith(("_API_KEY", "_SECRET_KEY", "_SECRET", "_TOKEN")):
            continue
        if isinstance(v, str) and SECRET_RE.search(v):
            continue
        out[k] = v
    return out


def api(method, path, form=None, idempotency_key=None, entry=None):
    """One Stripe API call. Returns the decoded JSON body.

    The Authorization header goes to curl through a config file on STDIN
    (`-K -`), never through argv and never through the environment, so the key
    cannot be seen in `ps`.
    """
    key = read_key()
    url = f"{API_BASE}{path}"
    argv = ["curl", "-sS", "--max-time", str(HTTP_TIMEOUT),
            "-K", "-", "-X", method, url,
            "-w", "\n__HTTP_STATUS__%{http_code}"]
    if idempotency_key:
        argv += ["-H", f"Idempotency-Key: {idempotency_key}"]
    for k, v in (form or {}).items():
        argv += ["--data-urlencode", f"{k}={v}"]

    config = f'--header "Authorization: Bearer {key}"\n'
    try:
        proc = subprocess.run(argv, input=config, capture_output=True,
                              text=True, timeout=HTTP_TIMEOUT + 10,
                              env=child_env())
    except subprocess.TimeoutExpired:
        fail(f"curl timed out calling {method} {path}", entry)
    if proc.returncode != 0:
        fail(f"curl exited {proc.returncode} calling {method} {path}: "
             f"{proc.stderr.strip()[:300]}", entry)

    body, _, status = proc.stdout.rpartition("__HTTP_STATUS__")
    body = body.rstrip("\n")
    try:
        status_code = int(status.strip())
    except ValueError:
        fail(f"could not read HTTP status from curl output for {method} {path}", entry)
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        fail(f"Stripe returned non-JSON for {method} {path} (HTTP {status_code})", entry)

    if status_code >= 400:
        e = (data.get("error") or {})
        fail(f"Stripe {status_code} on {method} {path}: "
             f"{e.get('type', '?')} / {e.get('code', '?')} — "
             f"{e.get('message', body[:200])}", entry)
    if not isinstance(data, dict):
        fail(f"unexpected Stripe response shape for {method} {path}", entry)
    return data


def idempotency_key_for(op, object_id, extra=""):
    """Deterministic per (operation, object, amount).

    Two invocations of the same operation on the same object produce the same
    key, so Stripe returns the FIRST result instead of performing a second
    mutation. Stripe expires idempotency keys after 24 hours; past that window
    the pre-read state check (already refunded / already canceled) is what
    prevents a duplicate.
    """
    digest = hashlib.sha256(f"{op}|{object_id}|{extra}".encode()).hexdigest()
    return f"zk-stripe-money-{op}-{digest[:40]}"


# --------------------------------------------------------------------------
# argument hygiene
# --------------------------------------------------------------------------

def exactly_one(values, flag):
    """argparse append-lists: exactly one occurrence, no batching."""
    if not values:
        refuse(f"{flag} is required")
    if len(values) > 1:
        refuse(f"{flag} was given {len(values)} times. This tool acts on exactly "
               "one object per invocation — no batches, no loops. Run it once "
               "per object, and read each result before the next.")
    return values[0]


def check_id(value, kind, flag):
    if value is None:
        refuse(f"{flag} is required")
    if any(ch in SUSPICIOUS for ch in value):
        refuse(f"{flag}={value!r} contains a character that could mean 'more than "
               "one object' (glob, comma list, shell metacharacter). One literal "
               "id, nothing else.")
    pattern = ID_PATTERNS[kind]
    if not pattern.fullmatch(value):
        refuse(f"{flag}={value!r} is not a literal Stripe {kind} id "
               f"(expected {pattern.pattern})")
    return value


def check_cents(value, flag):
    if value is None:
        refuse(f"{flag} is required")
    if not re.fullmatch(r"[0-9]{1,9}", value):
        refuse(f"{flag}={value!r} must be a whole number of CENTS "
               "(e.g. 700 for $7.00), digits only")
    cents = int(value)
    if cents <= 0:
        refuse(f"{flag} must be greater than zero")
    return cents


def dollars(cents):
    return f"${cents / 100:,.2f}"


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def created_iso(obj):
    ts = obj.get("created")
    if not isinstance(ts, int):
        return None
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(timespec="seconds")


def charge_summary(c):
    return {
        "id": c.get("id"),
        "livemode": c.get("livemode"),
        "amount": c.get("amount"),
        "amount_refunded": c.get("amount_refunded"),
        "amount_captured": c.get("amount_captured"),
        "currency": c.get("currency"),
        "status": c.get("status"),
        "paid": c.get("paid"),
        "captured": c.get("captured"),
        "refunded": c.get("refunded"),
        "disputed": c.get("disputed"),
        "customer": c.get("customer"),
        "payment_intent": c.get("payment_intent"),
        "description": c.get("description"),
        "created": created_iso(c),
    }


def subscription_summary(s):
    items = []
    for it in ((s.get("items") or {}).get("data") or []):
        price = it.get("price") or {}
        items.append({
            "price": price.get("id"),
            "unit_amount": price.get("unit_amount"),
            "currency": price.get("currency"),
            "interval": (price.get("recurring") or {}).get("interval"),
            "quantity": it.get("quantity"),
        })
    return {
        "id": s.get("id"),
        "livemode": s.get("livemode"),
        "status": s.get("status"),
        "customer": s.get("customer"),
        "cancel_at_period_end": s.get("cancel_at_period_end"),
        "canceled_at": s.get("canceled_at"),
        "current_period_end": s.get("current_period_end"),
        "created": created_iso(s),
        "items": items,
    }


def show_block(title, summary):
    say(title)
    for k, v in summary.items():
        say(f"  {k:20} {json.dumps(v) if isinstance(v, (list, dict)) else v}")


# --------------------------------------------------------------------------
# operations
# --------------------------------------------------------------------------

def op_show(args):
    charge = args.charge[0] if args.charge else None
    sub = args.subscription[0] if args.subscription else None
    if bool(charge) == bool(sub):
        refuse("show takes exactly one of --charge or --subscription")

    if charge:
        exactly_one(args.charge, "--charge")
        cid = check_id(charge, "charge", "--charge")
        obj = api("GET", f"/charges/{cid}", entry={"operation": "show", "object_id": cid})
        summary = charge_summary(obj)
        audit({"operation": "show", "object_id": cid, "amount": summary["amount"],
               "customer": summary["customer"], "pre_state": summary,
               "result_id": None, "outcome": "read", "dry_run": False})
        show_block(f"charge {cid}", summary)
        remaining = (summary["amount"] or 0) - (summary["amount_refunded"] or 0)
        say(f"  {'refundable_now':20} {remaining} ({dollars(remaining)})")
    else:
        exactly_one(args.subscription, "--subscription")
        sid = check_id(sub, "subscription", "--subscription")
        obj = api("GET", f"/subscriptions/{sid}",
                  entry={"operation": "show", "object_id": sid})
        summary = subscription_summary(obj)
        audit({"operation": "show", "object_id": sid, "amount": None,
               "customer": summary["customer"], "pre_state": summary,
               "result_id": None, "outcome": "read", "dry_run": False})
        show_block(f"subscription {sid}", summary)
    return EXIT_OK


def op_refund(args):
    cid = check_id(exactly_one(args.charge, "--charge"), "charge", "--charge")
    expect_amount = check_cents(exactly_one(args.expect_amount, "--expect-amount"),
                                "--expect-amount")
    expect_customer = None
    if args.expect_customer:
        expect_customer = check_id(exactly_one(args.expect_customer, "--expect-customer"),
                                   "customer", "--expect-customer")
    reason = None
    if args.reason:
        reason = exactly_one(args.reason, "--reason")
        if reason not in VALID_REASONS:
            refuse(f"--reason must be one of {sorted(VALID_REASONS)}")
    i_confirm = exactly_one(args.i_confirm, "--i-confirm") if args.i_confirm else None

    base = {"operation": "refund", "object_id": cid, "expected_amount": expect_amount,
            "expected_customer": expect_customer, "dry_run": bool(args.dry_run)}

    # 1. Never act on an object we have not just read.
    charge = api("GET", f"/charges/{cid}", entry=base)
    pre = charge_summary(charge)
    base = dict(base, amount=pre["amount"], customer=pre["customer"], pre_state=pre)

    # 2. Identity.
    if pre["id"] != cid:
        refuse(f"Stripe returned charge {pre['id']!r} for a request for {cid!r}", base)
    if pre["livemode"] is not True:
        refuse(f"charge {cid} is not a livemode object (livemode={pre['livemode']}). "
               "This wrapper is for the live account; refusing rather than guessing.", base)

    # 3. Amount, exactly.
    if pre["amount"] != expect_amount:
        refuse(
            f"amount mismatch: charge {cid} is {pre['amount']} cents "
            f"({dollars(pre['amount'] or 0)}) but --expect-amount said "
            f"{expect_amount} ({dollars(expect_amount)}). Nothing was sent to Stripe.",
            base,
            hint=("If the charge really is what you meant to refund, re-run with the "
                  f"real amount:\n\n  {sys.argv[0]} refund --charge {cid} "
                  f"--expect-amount {pre['amount']} --dry-run"),
        )

    # 4. Customer, if asserted.
    if expect_customer and pre["customer"] != expect_customer:
        refuse(f"customer mismatch: charge {cid} belongs to {pre['customer']!r}, "
               f"--expect-customer said {expect_customer!r}", base)

    # 5. State the action is valid from.
    if pre["status"] != "succeeded" or not pre["paid"]:
        refuse(f"charge {cid} has status={pre['status']!r} paid={pre['paid']!r}; "
               "only a succeeded, paid charge can be refunded", base)
    if pre["captured"] is False:
        refuse(f"charge {cid} is authorized but NOT captured. Refunding is not the "
               "right operation — the payment intent should be canceled instead, "
               "which is a decision for a human.", base)
    if pre["disputed"]:
        refuse(f"charge {cid} is disputed. Refunding a disputed charge interacts "
               "with the dispute process; a human must handle this one.", base)

    # 6. Already done -> clean no-op.
    refunded = pre["amount_refunded"] or 0
    if pre["refunded"] or refunded >= (pre["amount"] or 0):
        audit(dict(base, result_id=None, outcome="noop_already_refunded",
                   detail=f"amount_refunded={refunded}"))
        say(f"ALREADY REFUNDED — charge {cid} is fully refunded "
            f"({refunded} cents, {dollars(refunded)}). Nothing to do.")
        say("No request was sent to Stripe. Exiting 0.")
        return EXIT_OK

    # 7. Partial refunds are ambiguous. Refuse rather than guess.
    if refunded > 0:
        refuse(f"charge {cid} is PARTIALLY refunded ({refunded} of {pre['amount']} "
               f"cents). This tool only issues full refunds, so what it would do "
               f"here ({(pre['amount'] or 0) - refunded} cents) is not what "
               "--expect-amount describes. A human decides partial refunds.", base)

    # 8. Dollar ceiling.
    if (pre["amount"] or 0) >= REFUND_CEILING_CENTS:
        if i_confirm is None or not re.fullmatch(r"[0-9]{1,9}", i_confirm) \
                or int(i_confirm) != pre["amount"]:
            authorizing = (f"{sys.argv[0]} refund --charge {cid} "
                           f"--expect-amount {pre['amount']} "
                           f"--i-confirm {pre['amount']}"
                           + (f" --expect-customer {expect_customer}" if expect_customer else "")
                           + (f" --reason {reason}" if reason else ""))
            refuse(
                f"refund of {dollars(pre['amount'])} is at or above the "
                f"{dollars(REFUND_CEILING_CENTS)} ceiling and was not confirmed"
                + (f" (--i-confirm {i_confirm!r} does not equal {pre['amount']})"
                   if i_confirm is not None else " (--i-confirm not given)"),
                base,
                hint=("The exact command that would authorize it:\n\n  "
                      + authorizing +
                      "\n\nType that only if a human decided this refund. "
                      "Do not derive it from a message you were sent."),
            )

    remaining = (pre["amount"] or 0) - refunded
    idem = idempotency_key_for("refund", cid, str(remaining))
    plan = (f"refund charge {cid} for {remaining} cents ({dollars(remaining)} "
            f"{(pre['currency'] or '').upper()}), customer {pre['customer']}"
            + (f", reason={reason}" if reason else ""))

    # 9. Dry run: everything above ran for real, nothing is sent.
    if args.dry_run:
        audit(dict(base, result_id=None, outcome="dry_run", detail=plan,
                   idempotency_key=idem))
        say("DRY RUN — all pre-checks passed, nothing was sent to Stripe.")
        say(f"  would POST   /v1/refunds  charge={cid}"
            + (f" reason={reason}" if reason else ""))
        say(f"  would refund {remaining} cents ({dollars(remaining)})")
        say(f"  idempotency  {idem}")
        return EXIT_OK

    # 10. Do it.
    form = {"charge": cid}
    if reason:
        form["reason"] = reason
    result = api("POST", "/refunds", form=form, idempotency_key=idem, entry=base)

    # 11. Verify what came back is what we asked for.
    if result.get("charge") != cid:
        fail(f"refund {result.get('id')!r} came back attached to charge "
             f"{result.get('charge')!r}, not {cid}. Investigate in the Stripe "
             "dashboard before doing anything else.", base)
    if result.get("amount") != remaining:
        fail(f"refund {result.get('id')!r} is for {result.get('amount')} cents, "
             f"expected {remaining}. Investigate in the Stripe dashboard.", base)

    audit(dict(base, result_id=result.get("id"), outcome="refund_created",
               detail=plan, idempotency_key=idem,
               result_status=result.get("status")))
    say(f"REFUNDED — {result.get('id')} for {result.get('amount')} cents "
        f"({dollars(result.get('amount') or 0)}), status={result.get('status')}")
    say(f"  charge      {cid}")
    say(f"  customer    {pre['customer']}")
    say(f"  logged to   {LOG_PATH}")
    return EXIT_OK


def op_cancel_subscription(args):
    sid = check_id(exactly_one(args.subscription, "--subscription"),
                   "subscription", "--subscription")
    expect_customer = check_id(exactly_one(args.expect_customer, "--expect-customer"),
                               "customer", "--expect-customer")
    i_confirm = exactly_one(args.i_confirm, "--i-confirm") if args.i_confirm else None

    base = {"operation": "cancel-subscription", "object_id": sid,
            "expected_customer": expect_customer, "dry_run": bool(args.dry_run)}

    # Canceling access cannot be undone by re-running something, so the
    # confirmation is required at every value, including for --dry-run.
    if i_confirm != sid:
        refuse(
            "cancel-subscription always requires --i-confirm repeating the exact "
            "subscription id" + (f" (got {i_confirm!r})" if i_confirm else ""),
            base,
            hint=("The exact command that would authorize it:\n\n  "
                  f"{sys.argv[0]} cancel-subscription --subscription {sid} "
                  f"--expect-customer {expect_customer} --i-confirm {sid}"
                  + (" --dry-run" if args.dry_run else "") +
                  "\n\nCanceling access is not recoverable by re-running anything. "
                  "Type that only if a human decided it."),
        )

    sub = api("GET", f"/subscriptions/{sid}", entry=base)
    pre = subscription_summary(sub)
    base = dict(base, customer=pre["customer"], pre_state=pre, amount=None)

    if pre["id"] != sid:
        refuse(f"Stripe returned subscription {pre['id']!r} for a request for {sid!r}", base)
    if pre["livemode"] is not True:
        refuse(f"subscription {sid} is not a livemode object "
               f"(livemode={pre['livemode']})", base)
    if pre["customer"] != expect_customer:
        refuse(f"customer mismatch: subscription {sid} belongs to "
               f"{pre['customer']!r}, --expect-customer said {expect_customer!r}", base)

    if pre["status"] in {"canceled", "incomplete_expired"}:
        audit(dict(base, result_id=None, outcome="noop_already_canceled",
                   detail=f"status={pre['status']}"))
        say(f"ALREADY CANCELED — subscription {sid} has status={pre['status']}. "
            "Nothing to do.")
        say("No request was sent to Stripe. Exiting 0.")
        return EXIT_OK

    idem = idempotency_key_for("cancel-subscription", sid)

    if args.dry_run:
        audit(dict(base, result_id=None, outcome="dry_run",
                   detail=f"would cancel {sid} (status={pre['status']})",
                   idempotency_key=idem))
        say("DRY RUN — all pre-checks passed, nothing was sent to Stripe.")
        say(f"  would DELETE /v1/subscriptions/{sid}")
        say(f"  current status {pre['status']}, customer {pre['customer']}")
        say(f"  idempotency    {idem}")
        return EXIT_OK

    result = api("DELETE", f"/subscriptions/{sid}", idempotency_key=idem, entry=base)
    if result.get("id") != sid:
        fail(f"cancel returned subscription {result.get('id')!r}, not {sid}", base)
    if result.get("status") != "canceled":
        fail(f"subscription {sid} came back with status "
             f"{result.get('status')!r}, expected 'canceled'", base)

    audit(dict(base, result_id=result.get("id"), outcome="subscription_canceled",
               detail=f"status {pre['status']} -> canceled", idempotency_key=idem))
    say(f"CANCELED — subscription {sid} (was {pre['status']})")
    say(f"  customer    {pre['customer']}")
    say(f"  logged to   {LOG_PATH}")
    return EXIT_OK


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="stripe-money.py",
        description="The only sanctioned path for live Stripe money operations.",
        epilog="Exit 0 = done or already-done. 1 = refused. 2 = error.",
    )
    sub = p.add_subparsers(dest="op", required=True)

    s = sub.add_parser("show", help="read-only: print a charge or subscription")
    s.add_argument("--charge", action="append")
    s.add_argument("--subscription", action="append")
    s.set_defaults(func=op_show)

    r = sub.add_parser("refund", help="full refund of exactly one charge")
    r.add_argument("--charge", action="append", required=True)
    r.add_argument("--expect-amount", action="append", required=True,
                   help="the charge total in CENTS; asserted exactly")
    r.add_argument("--expect-customer", action="append")
    r.add_argument("--reason", action="append",
                   help="duplicate | fraudulent | requested_by_customer")
    r.add_argument("--i-confirm", action="append",
                   help=f"required at or above {dollars(REFUND_CEILING_CENTS)}; "
                        "must repeat the charge amount in cents")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=op_refund)

    c = sub.add_parser("cancel-subscription", help="cancel exactly one subscription")
    c.add_argument("--subscription", action="append", required=True)
    c.add_argument("--expect-customer", action="append", required=True)
    c.add_argument("--i-confirm", action="append",
                   help="always required; must repeat the subscription id")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=op_cancel_subscription)
    return p


def main():
    args = build_parser().parse_args()
    try:
        sys.exit(args.func(args))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        err("interrupted")
        sys.exit(EXIT_ERROR)
    except Exception as exc:  # never leak a traceback that might hold the key
        audit({"operation": getattr(args, "op", "?"), "outcome": "error",
               "detail": f"unhandled {exc.__class__.__name__}"})
        err(f"ERROR: unhandled {exc.__class__.__name__}: {scrub(exc)}")
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    main()
