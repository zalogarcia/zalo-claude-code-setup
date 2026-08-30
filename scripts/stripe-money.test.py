#!/usr/bin/env python3
"""Behaviour suite for stripe-money.py. Run: python3 ~/.claude/scripts/stripe-money.test.py

Moves no money. Every case that could reach a mutating endpoint is wired to a
fake transport that RAISES on anything other than GET, so a regression that
removed a guard would fail the suite loudly instead of issuing a refund.

Two kinds of case:
  * stubbed   — the whole HTTP layer is faked, so the object states that do not
                exist in the live account (a $500 unrefunded charge, an active
                subscription, a disputed charge) can still be exercised.
  * live-read — the object is really fetched from Stripe with the real key, and
                only the fields under test are overridden in memory. Skipped
                automatically if the key file is missing or the network is down.

All audit output is redirected to a temp file so the suite never pollutes
~/.claude/logs/stripe-actions.jsonl.
"""

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile

SCRIPT = os.path.expanduser("~/.claude/scripts/stripe-money.py")

spec = importlib.util.spec_from_file_location("stripe_money", SCRIPT)
sm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm)

LOG_FD, LOG_TMP = tempfile.mkstemp(prefix="stripe-money-test-", suffix=".jsonl")
os.close(LOG_FD)
sm.LOG_PATH = LOG_TMP


class MutationAttempted(BaseException):
    """Not an Exception subclass on purpose: main()'s catch-all must not eat it."""


def charge(**over):
    base = {
        "id": "ch_TESTTESTTESTTEST01",
        "object": "charge",
        "livemode": True,
        "amount": 700,
        "amount_refunded": 0,
        "amount_captured": 700,
        "currency": "usd",
        "status": "succeeded",
        "paid": True,
        "captured": True,
        "refunded": False,
        "disputed": False,
        "customer": "cus_TESTTESTTEST01",
        "payment_intent": "pi_TESTTESTTEST01",
        "description": "test",
        "created": 1756000000,
    }
    base.update(over)
    return base


def subscription(**over):
    base = {
        "id": "sub_TESTTESTTESTTEST1",
        "object": "subscription",
        "livemode": True,
        "status": "active",
        "customer": "cus_TESTTESTTEST01",
        "cancel_at_period_end": False,
        "canceled_at": None,
        "current_period_end": 1760000000,
        "created": 1756000000,
        "items": {"data": []},
    }
    base.update(over)
    return base


def fake_transport(obj):
    """GET returns obj. Anything else is a test failure, loudly."""

    def _api(method, path, form=None, idempotency_key=None, entry=None):
        if method != "GET":
            raise MutationAttempted(f"{method} {path} form={form}")
        return copy.deepcopy(obj)

    return _api


def run(argv, obj):
    """Run the CLI with a faked transport; return (exit_code, stdout, stderr)."""
    saved_api, saved_argv = sm.api, sys.argv
    sm.api = fake_transport(obj)
    sys.argv = ["stripe-money.py"] + argv
    out, errbuf = io.StringIO(), io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(errbuf):
            try:
                sm.main()
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        sm.api, sys.argv = saved_api, saved_argv
    return code, out.getvalue(), errbuf.getvalue()


CASES = []


def case(label, argv, obj, expect_code, expect_text=None):
    CASES.append((label, argv, obj, expect_code, expect_text))


CH = "ch_TESTTESTTESTTEST01"
CUS = "cus_TESTTESTTEST01"
SUB = "sub_TESTTESTTESTTEST1"

# ---- argument hygiene: these must refuse before any HTTP happens ----------
case("glob in charge id", ["refund", "--charge", "ch_TEST*", "--expect-amount", "700"],
     charge(), 1, "glob")
case("comma list of charges",
     ["refund", "--charge", "ch_AAAAAAAA1,ch_BBBBBBBB2", "--expect-amount", "700"],
     charge(), 1, "glob")
case("two --charge flags (batch)",
     ["refund", "--charge", CH, "--charge", "ch_OTHEROTHER02", "--expect-amount", "700"],
     charge(), 1, "exactly one object")
case("shell metacharacter in id",
     ["refund", "--charge", "ch_AAAAAAAA1;id", "--expect-amount", "700"],
     charge(), 1, "glob")
case("wrong id prefix", ["refund", "--charge", "sub_AAAAAAAAAA", "--expect-amount", "700"],
     charge(), 1, "not a literal Stripe charge id")
case("dollars not cents", ["refund", "--charge", CH, "--expect-amount", "7.00"],
     charge(), 1, "CENTS")
case("zero amount", ["refund", "--charge", CH, "--expect-amount", "0"],
     charge(), 1, "greater than zero")

# ---- refund assertions ----------------------------------------------------
case("amount mismatch", ["refund", "--charge", CH, "--expect-amount", "999"],
     charge(), 1, "amount mismatch")
case("customer mismatch",
     ["refund", "--charge", CH, "--expect-amount", "700",
      "--expect-customer", "cus_WRONGWRONG01"], charge(), 1, "customer mismatch")
case("customer match passes (dry-run)",
     ["refund", "--charge", CH, "--expect-amount", "700",
      "--expect-customer", CUS, "--dry-run"], charge(), 0, "DRY RUN")
case("not livemode", ["refund", "--charge", CH, "--expect-amount", "700"],
     charge(livemode=False), 1, "not a livemode object")
case("charge failed/unpaid", ["refund", "--charge", CH, "--expect-amount", "700"],
     charge(status="failed", paid=False), 1, "only a succeeded, paid charge")
case("uncaptured charge", ["refund", "--charge", CH, "--expect-amount", "700"],
     charge(captured=False, amount_captured=0), 1, "NOT captured")
case("disputed charge", ["refund", "--charge", CH, "--expect-amount", "700"],
     charge(disputed=True), 1, "disputed")
case("id echoed back differs",
     ["refund", "--charge", CH, "--expect-amount", "700"],
     charge(id="ch_SOMETHINGELSE99"), 1, "returned charge")

# ---- already-done is a clean no-op ---------------------------------------
case("already fully refunded (live path)",
     ["refund", "--charge", CH, "--expect-amount", "700"],
     charge(refunded=True, amount_refunded=700), 0, "ALREADY REFUNDED")
case("already fully refunded (dry-run)",
     ["refund", "--charge", CH, "--expect-amount", "700", "--dry-run"],
     charge(refunded=True, amount_refunded=700), 0, "ALREADY REFUNDED")
case("partially refunded refuses",
     ["refund", "--charge", CH, "--expect-amount", "700"],
     charge(amount_refunded=300), 1, "PARTIALLY refunded")

# ---- the $200 ceiling ----------------------------------------------------
BIG = charge(amount=50000, amount_captured=50000)
case("ceiling: no --i-confirm",
     ["refund", "--charge", CH, "--expect-amount", "50000"], BIG, 1, "ceiling")
case("ceiling: refusal prints the authorizing command",
     ["refund", "--charge", CH, "--expect-amount", "50000"], BIG, 1, "--i-confirm 50000")
case("ceiling: wrong --i-confirm",
     ["refund", "--charge", CH, "--expect-amount", "50000", "--i-confirm", "49999"],
     BIG, 1, "does not equal")
case("ceiling: --i-confirm cannot be a non-number",
     ["refund", "--charge", CH, "--expect-amount", "50000", "--i-confirm", "yes"],
     BIG, 1, "ceiling")
case("ceiling: correct --i-confirm passes to dry-run",
     ["refund", "--charge", CH, "--expect-amount", "50000",
      "--i-confirm", "50000", "--dry-run"], BIG, 0, "DRY RUN")
case("just under ceiling needs no confirm",
     ["refund", "--charge", CH, "--expect-amount", "19999", "--dry-run"],
     charge(amount=19999, amount_captured=19999), 0, "DRY RUN")
case("exactly at ceiling needs confirm",
     ["refund", "--charge", CH, "--expect-amount", "20000", "--dry-run"],
     charge(amount=20000, amount_captured=20000), 1, "ceiling")

# ---- reason ---------------------------------------------------------------
case("bad --reason", ["refund", "--charge", CH, "--expect-amount", "700",
                      "--reason", "because", "--dry-run"], charge(), 1, "--reason must be one of")
case("good --reason", ["refund", "--charge", CH, "--expect-amount", "700",
                       "--reason", "requested_by_customer", "--dry-run"],
     charge(), 0, "reason=requested_by_customer")

# ---- cancel-subscription --------------------------------------------------
case("cancel without --i-confirm",
     ["cancel-subscription", "--subscription", SUB, "--expect-customer", CUS],
     subscription(), 1, "always requires --i-confirm")
case("cancel with wrong --i-confirm",
     ["cancel-subscription", "--subscription", SUB, "--expect-customer", CUS,
      "--i-confirm", "sub_SOMETHINGELSE1"], subscription(), 1, "always requires --i-confirm")
case("cancel dry-run also requires --i-confirm",
     ["cancel-subscription", "--subscription", SUB, "--expect-customer", CUS, "--dry-run"],
     subscription(), 1, "always requires --i-confirm")
case("cancel customer mismatch",
     ["cancel-subscription", "--subscription", SUB, "--expect-customer",
      "cus_WRONGWRONG01", "--i-confirm", SUB], subscription(), 1, "customer mismatch")
case("cancel already canceled is a no-op",
     ["cancel-subscription", "--subscription", SUB, "--expect-customer", CUS,
      "--i-confirm", SUB], subscription(status="canceled"), 0, "ALREADY CANCELED")
case("cancel not livemode",
     ["cancel-subscription", "--subscription", SUB, "--expect-customer", CUS,
      "--i-confirm", SUB], subscription(livemode=False), 1, "not a livemode object")
case("cancel active + confirm + dry-run",
     ["cancel-subscription", "--subscription", SUB, "--expect-customer", CUS,
      "--i-confirm", SUB, "--dry-run"], subscription(), 0, "DRY RUN")
case("cancel requires --expect-customer",
     ["cancel-subscription", "--subscription", SUB, "--i-confirm", SUB],
     subscription(), 2, None)  # argparse: missing required arg -> exit 2

# ---- show is read-only ----------------------------------------------------
case("show charge", ["show", "--charge", CH], charge(), 0, "refundable_now")
case("show subscription", ["show", "--subscription", SUB], subscription(), 0, "status")
case("show needs exactly one target", ["show", "--charge", CH, "--subscription", SUB],
     charge(), 1, "exactly one")
case("show with neither target", ["show"], charge(), 1, "exactly one")


def main():
    passed = failed = skipped = 0
    for label, argv, obj, expect_code, expect_text in CASES:
        try:
            code, out, errout = run(argv, obj)
        except MutationAttempted as exc:
            print(f"FAIL  | {label}: REACHED A MUTATING CALL ({exc})")
            failed += 1
            continue
        except SystemExit as exc:  # argparse errors escape before our handler
            code, out, errout = (exc.code if isinstance(exc.code, int) else 1), "", ""
        blob = out + errout
        ok = code == expect_code and (expect_text is None or expect_text in blob)
        if ok:
            passed += 1
            print(f"PASS  | exit {code} | {label}")
        else:
            failed += 1
            print(f"FAIL  | expected exit {expect_code}"
                  + (f" containing {expect_text!r}" if expect_text else "")
                  + f" got exit {code} | {label}")
            print("        " + blob.strip().replace("\n", "\n        ")[:500])

    # ---- live-read case: real object, real key, only the tested fields moved
    # The charge id comes from the environment, never from this file: real ids
    # are a customer's payment records and this repo mirrors publicly. Run it
    # as:  STRIPE_MONEY_TEST_CHARGE=ch_... python3 stripe-money.test.py
    live_label = "LIVE: ceiling refuses on a really-fetched charge"
    live_charge = os.environ.get("STRIPE_MONEY_TEST_CHARGE", "").strip()
    if not live_charge:
        print(f"SKIP  | {live_label} (set STRIPE_MONEY_TEST_CHARGE=ch_... to run it)")
        skipped += 1
    elif os.path.isfile(sm.KEY_PATH):
        real_api = sm.api
        try:
            real = real_api("GET", f"/charges/{live_charge}")
        except BaseException as exc:  # network down, key rotated, etc.
            print(f"SKIP  | {live_label} (could not fetch: {type(exc).__name__})")
            skipped += 1
            real = None
        if real is not None:
            forged = dict(real, amount=50000, amount_captured=50000,
                          amount_refunded=0, refunded=False)
            code, out, errout = run(
                ["refund", "--charge", live_charge, "--expect-amount", "50000"], forged)
            blob = out + errout
            key = sm._KEY_CACHE or ""
            leaked = bool(key) and key in blob
            ok = code == 1 and "ceiling" in blob and not leaked
            print(("PASS  | " if ok else "FAIL  | ") + live_label
                  + f" (exit {code}, key_leaked={leaked})")
            print("        real id/customer read from Stripe: "
                  f"{real.get('id')} / {real.get('customer')} livemode={real.get('livemode')}")
            print("        " + blob.strip().split("\n")[0][:300])
            passed += 1 if ok else 0
            failed += 0 if ok else 1
    else:
        print(f"SKIP  | {live_label} (no key file)")
        skipped += 1

    # ---- the audit log must never contain anything key-shaped ----
    leaked_lines = 0
    if os.path.isfile(LOG_TMP):
        with open(LOG_TMP) as fh:
            for line in fh:
                if sm.SECRET_RE.search(line) or (sm._KEY_CACHE and sm._KEY_CACHE in line):
                    leaked_lines += 1
    if leaked_lines == 0:
        passed += 1
        print("PASS  | audit log written by this suite contains no key-shaped text")
    else:
        failed += 1
        print(f"FAIL  | audit log contains {leaked_lines} key-shaped line(s)")

    # ---- every refusal/no-op must have produced an audit record ----
    records = 0
    if os.path.isfile(LOG_TMP):
        with open(LOG_TMP) as fh:
            for line in fh:
                try:
                    json.loads(line)
                    records += 1
                except json.JSONDecodeError:
                    pass
    if records >= 25:
        passed += 1
        print(f"PASS  | audit log recorded {records} entries for this suite")
    else:
        failed += 1
        print(f"FAIL  | audit log only recorded {records} entries (expected >= 25)")

    os.unlink(LOG_TMP)
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
