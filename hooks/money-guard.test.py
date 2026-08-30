#!/usr/bin/env python3
"""Behaviour suite for money-guard.py. Run: python3 ~/.claude/hooks/money-guard.test.py

Same shape as tmux-peer-guard.test.py / npm-install-guard.test.py: feed the hook
a PreToolUse payload on stdin, assert allow (exit 0) vs deny (exit 2).

Nothing here talks to Stripe. The `sk_live_` strings below are obvious fakes
built at runtime so this file never contains a real key, and so the file itself
does not become a thing that must be handled carefully.
"""

import json
import subprocess
import sys

HOOK = "/Users/zalo/.claude/hooks/money-guard.py"
WRAP = "/Users/zalo/.claude/scripts/stripe-money.py"

# Built at runtime so no key-shaped literal is stored in this file.
FAKE_SK = "sk_" + "live_" + "51FAKEFAKEFAKEfakefake00"
FAKE_RK = "rk_" + "live_" + "51FAKEFAKEFAKEfakefake00"

# Synthetic ids. Real charge/customer ids are a customer's payment records and
# this repo mirrors to a public GitHub remote, so none appear here; the hook
# only pattern-matches shapes, so synthetic ids exercise it identically.
CH = "ch_1EXAMPLEEXAMPLEEXAMPLE01"
SUB = "sub_1EXAMPLEEXAMPLE01"
CUS = "cus_EXAMPLEEXAMPLE01"
API = "https://api.stripe.com"

CASES = []


def case(label, cmd, expected):
    CASES.append((label, cmd, expected))


# ---------------------------------------------------------------- allowed --
case("unrelated: ls", "ls -la ~/dev", "allow")
case("unrelated: git status", "git status", "allow")
case("unrelated: npm ci", "npm ci", "allow")
case("unrelated: build", "npm run build 2>&1 | tail -40", "allow")
case("prose mentioning stripe in a commit message",
     'git commit -m "fix stripe webhook signature check"', "allow")
case("grep for the word stripe in a repo",
     'grep -rn "stripe" ~/dev/copymyaiagency/src', "allow")
case("reading a file that happens to be about refunds",
     "cat ~/dev/copymyaiagency/docs/refund-policy.md", "allow")
case("npm script whose name contains stripe", "npm run test:stripe", "allow")
case("stripe CLI read-only: logs", "stripe logs tail", "allow")
case("stripe CLI read-only: get", f"stripe get /v1/charges/{CH}", "allow")
case("stripe CLI read-only: list", "stripe charges list --limit 3", "allow")
case("stripe CLI version", "stripe --version", "allow")
case("read-only GET at api.stripe.com",
     f"curl -sS {API}/v1/charges/{CH}", "allow")
case("read-only GET with -G and query params",
     f"curl -sS -G {API}/v1/charges -d limit=3", "allow")

case("wrapper: show charge", f"python3 {WRAP} show --charge {CH}", "allow")
case("wrapper: show subscription", f"python3 {WRAP} show --subscription {SUB}", "allow")
case("wrapper: refund dry-run",
     f"python3 {WRAP} refund --charge {CH} --expect-amount 700 --dry-run", "allow")
case("wrapper: real refund invocation",
     f"python3 {WRAP} refund --charge {CH} --expect-amount 700 "
     f"--expect-customer {CUS} --reason requested_by_customer", "allow")
case("wrapper: cancel subscription",
     f"python3 {WRAP} cancel-subscription --subscription {SUB} "
     f"--expect-customer {CUS} --i-confirm {SUB}", "allow")
case("wrapper: tilde path", f"python3 ~/.claude/scripts/stripe-money.py show --charge {CH}",
     "allow")
case("wrapper: executed directly", f"{WRAP} show --charge {CH}", "allow")
case("wrapper: after an unrelated command",
     f"echo starting && python3 {WRAP} show --charge {CH}", "allow")
case("wrapper: its own test suite",
     "python3 /Users/zalo/.claude/scripts/stripe-money.test.py", "allow")
case("reading the wrapper's audit log", "tail -5 ~/.claude/logs/stripe-actions.jsonl",
     "allow")
case("listing the key DIRECTORY without touching the file",
     "ls -la ~/.config/stripe", "allow")

# ------------------------------------------------- denied: HTTP endpoints --
case("POST /v1/refunds", f"curl -X POST {API}/v1/refunds -d charge={CH}", "deny")
case("implicit POST via -d to /v1/refunds", f"curl {API}/v1/refunds -d charge={CH}", "deny")
case("GET on /v1/refunds still denied", f"curl -sS {API}/v1/refunds", "deny")
case("legacy charge refund path", f"curl -X POST {API}/v1/charges/{CH}/refunds", "deny")
case("singular /refund path", f"curl -X POST {API}/v1/charges/{CH}/refund", "deny")
case("payment intent cancel",
     f"curl -X POST {API}/v1/payment_intents/pi_1EXAMPLEEXAMPLE01/cancel", "deny")
case("subscription DELETE", f"curl -X DELETE {API}/v1/subscriptions/{SUB}", "deny")
case("subscription cancel path", f"curl -X POST {API}/v1/subscriptions/{SUB}/cancel", "deny")
case("credit note create", f"curl -X POST {API}/v1/credit_notes -d invoice=in_1", "deny")
case("invoice void", f"curl -X POST {API}/v1/invoices/in_1/void", "deny")
case("charge capture", f"curl -X POST {API}/v1/charges/{CH}/capture", "deny")
case("customer DELETE", f"curl -X DELETE {API}/v1/customers/{CUS}", "deny")
case("payout create (not in the original list, moves money)",
     f"curl -X POST {API}/v1/payouts -d amount=50000", "deny")
case("transfer create (not in the original list, moves money)",
     f"curl -X POST {API}/v1/transfers -d amount=50000 -d destination=acct_1", "deny")
case("topup create", f"curl -X POST {API}/v1/topups -d amount=50000", "deny")
case("generic mutating POST to any Stripe path",
     f"curl -X POST {API}/v1/customers/{CUS} -d email=x@y.z", "deny")
case("generic mutating PATCH", f"curl -X PATCH {API}/v1/subscriptions/{SUB} -d x=1", "deny")
case("wget POST to refunds", f"wget --method=POST {API}/v1/refunds", "deny")
case("httpie style", f"http POST {API}/v1/refunds charge={CH}", "deny")

# ------------------------------------------------------ denied: stripe CLI --
case("stripe refunds create", f"stripe refunds create --charge {CH}", "deny")
case("stripe subscriptions cancel", f"stripe subscriptions cancel {SUB}", "deny")
case("stripe subscriptions delete", f"stripe subscriptions delete {SUB}", "deny")
case("stripe payment_intents cancel", "stripe payment_intents cancel pi_1EXAMPLEEXAMPLE01", "deny")
case("stripe credit_notes create", "stripe credit_notes create --invoice in_1", "deny")
case("stripe invoices void", "stripe invoices void in_1", "deny")
case("stripe payouts create", "stripe payouts create --amount 50000", "deny")
case("stripe raw post verb", f"stripe post /v1/refunds -d charge={CH}", "deny")
case("stripe raw delete verb", f"stripe delete /v1/subscriptions/{SUB}", "deny")
case("stripe customers delete", f"stripe customers delete {CUS}", "deny")
case("stripe by absolute path", f"/opt/homebrew/bin/stripe refunds create --charge {CH}",
     "deny")

# ------------------------------------------------------- denied: SDK inline --
case("python SDK refund one-liner",
     f"""python3 -c "import stripe; stripe.Refund.create(charge='{CH}')" """, "deny")
case("python SDK subscription delete one-liner",
     f"""python3 -c "import stripe; stripe.Subscription.delete('{SUB}')" """, "deny")
case("node SDK refund one-liner",
     f"""node -e "require('stripe')(k).refunds.create({{charge:'{CH}'}})" """, "deny")
case("node SDK subscription cancel one-liner",
     f"""node -e "require('stripe')(k).subscriptions.del('{SUB}')" """, "deny")
case("node SDK payout one-liner",
     """node -e "require('stripe')(k).payouts.create({amount:50000})" """, "deny")
case("heredoc fed to python (executes)",
     "python3 <<'PYEOF'\nimport stripe\n"
     f"stripe.Refund.create(charge='{CH}')\nPYEOF", "deny")
case("heredoc fed to node (executes)",
     "node <<'JSEOF'\nconst s=require('stripe')(k)\n"
     f"s.refunds.create({{charge:'{CH}'}})\nJSEOF", "deny")
case("heredoc WRITING a doc that mentions the endpoint is not a call",
     "cat > /tmp/notes.md <<'MDEOF'\nWe call POST /v1/refunds from the server.\nMDEOF",
     "allow")

# ------------------------------------------------------ denied: obfuscation --
case("bash -c wrapper", f'bash -c "curl -X POST {API}/v1/refunds -d charge={CH}"', "deny")
case("sh -c wrapper", f"sh -c 'curl -X POST {API}/v1/refunds'", "deny")
case("after a ; separator", f"echo hi; curl -X POST {API}/v1/refunds -d charge={CH}", "deny")
case("after && separator", f"true && curl -X POST {API}/v1/refunds", "deny")
case("after || separator", f"false || curl -X POST {API}/v1/refunds", "deny")
case("on a second line", f"echo hi\ncurl -X POST {API}/v1/refunds", "deny")
case("unspaced semicolon", f"echo hi;curl -X POST {API}/v1/refunds", "deny")
case("sudo prefix", f"sudo curl -X POST {API}/v1/refunds", "deny")
case("nohup prefix", f"nohup curl -X POST {API}/v1/refunds", "deny")
case("env-assignment prefix", f"FOO=1 curl -X POST {API}/v1/refunds", "deny")
case("env wrapper prefix", f"env FOO=1 curl -X POST {API}/v1/refunds", "deny")
case("xargs prefix", f"xargs curl -X POST {API}/v1/refunds", "deny")
case("jammed -XPOST on a non-money path",
     f"curl -XPOST {API}/v1/customers/{CUS} -d email=x@y.z", "deny")
case("--request=DELETE equals form",
     f"curl --request=DELETE {API}/v1/customers/{CUS}", "deny")
case("-X and method as separate tokens on a non-money path",
     f"curl -X PUT {API}/v1/customers/{CUS}", "deny")
case("host in a variable, path in the call",
     f"B={API}; curl -X POST $B/v1/refunds -d charge={CH}", "deny")
case("unbalanced quoting fails closed",
     f'curl -X POST "{API}/v1/refunds -d charge={CH}', "deny")
case("wrapper mentioned in a comment does not launder an SDK call",
     f"""python3 -c "import stripe; stripe.Refund.create(charge='{CH}')  # stripe-money.py" """,
     "deny")
case("wrapper run first does not whitelist a later curl",
     f"python3 {WRAP} show --charge {CH} && curl -X POST {API}/v1/refunds -d charge={CH}",
     "deny")

# ------------------------------------------------------- denied: key literal --
case("sk_live pasted inline in a header",
     f'curl -H "Authorization: Bearer {FAKE_SK}" {API}/v1/charges', "deny")
case("sk_live exported to the environment",
     f"export STRIPE_API_KEY={FAKE_SK}", "deny")
case("rk_live restricted key inline", f"echo {FAKE_RK} > /tmp/k", "deny")
case("sk_live written inside a heredoc body",
     f"cat > /tmp/k <<'EOF'\n{FAKE_SK}\nEOF", "deny")
case("sk_live in an echo", f"echo {FAKE_SK}", "deny")
case("uppercase SK_LIVE still caught", f"echo {FAKE_SK.upper()}", "deny")

# ---------------------------------------------------------- denied: key file --
case("cat the key file", "cat ~/.config/stripe/live-key", "deny")
case("cat with absolute path", "cat /Users/zalo/.config/stripe/live-key", "deny")
case("cat with $HOME", "cat $HOME/.config/stripe/live-key", "deny")
case("grep the key file", "grep . ~/.config/stripe/live-key", "deny")
case("head the key file", "head -c 20 ~/.config/stripe/live-key", "deny")
case("tail the key file", "tail ~/.config/stripe/live-key", "deny")
case("less the key file", "less ~/.config/stripe/live-key", "deny")
case("cp the key file", "cp ~/.config/stripe/live-key /tmp/k", "deny")
case("cd then cat the bare filename", "cd ~/.config/stripe && cat live-key", "deny")
case("glob over the key directory", "cat ~/.config/stripe/*", "deny")
case("command substitution into a variable",
     'K=$(cat ~/.config/stripe/live-key); echo done', "deny")
case("bash -c wrapper around the read", 'bash -c "cat ~/.config/stripe/live-key"', "deny")
case("wc the key file", "wc -c < ~/.config/stripe/live-key", "deny")
case("xxd the key file", "xxd ~/.config/stripe/live-key", "deny")

# -------------------------------------------------------- denied: env exfil --
case("echo the env var", "echo $STRIPE_API_KEY", "deny")
case("echo the env var into a file", "echo $STRIPE_API_KEY > /tmp/k", "deny")
case("printenv the named var", "printenv STRIPE_API_KEY", "deny")
case("env piped to grep stripe", "env | grep -i stripe", "deny")
case("printenv piped to grep stripe", "printenv | grep STRIPE", "deny")
case("curl using the env var directly",
     f'curl -H "Authorization: Bearer $STRIPE_API_KEY" {API}/v1/charges', "deny")

# ------------------------- denied: ps -E, the process-environment dump route --
# Found empirically on 2026-08-30: six long-lived MCP server processes were
# carrying STRIPE_API_KEY in their environment, and `ps -ww -E -o command`
# handed the live key to anything that asked, without naming Stripe at all.
case("ps -E dumps every environment", "ps -ww -E -o pid,command", "deny")
case("ps -E piped to grep", "ps -E | grep -i stripe", "deny")
case("ps -E flag jammed with others", "ps -wwE -o command", "deny")
case("ps --environment long form", "ps --environment", "deny")
case("BSD dash-less bundle with e", "ps auxe", "deny")
case("BSD axe", "ps axe | head", "deny")
case("ps -ef is process list, not environment", "ps -ef | head -20", "allow")
case("ps aux is fine", "ps aux | grep node", "allow")
case("ps -eo pid,args is fine", "ps -eo pid,args | head", "allow")
case("pgrep is fine", "pgrep -fl claude", "allow")

# --------------------- regression: source code is not shell -------------------
# The first version of this hook re-segmented interpreter heredoc bodies as
# shell, so the PYTHON line `"stripe" in low` produced a segment whose head was
# the bare word `stripe` and got denied as a CLI call. It blocked a patch to
# its own source. Source bodies now get text rules only.
case("python heredoc containing the word stripe in a string",
     'python3 - <<\'PYEOF\'\nlow = cmd.lower()\nif "stripe" in low:\n'
     '    print("mentions stripe")\nPYEOF', "allow")
case("python heredoc editing this guard's own source",
     "python3 - <<'PYEOF'\nimport pathlib\n"
     "p = pathlib.Path('money-guard.py')\n"
     "s = p.read_text().replace('stripe in low', 'stripe_in_low')\n"
     "p.write_text(s)\nPYEOF", "allow")
case("but a python heredoc that really calls a refund is still denied",
     "python3 - <<'PYEOF'\nimport stripe\n"
     f"stripe.Refund.create(charge='{CH}')\nPYEOF", "deny")
case("and one that shells out to the refunds endpoint is still denied",
     "python3 - <<'PYEOF'\nimport os\n"
     f"os.system('curl -X POST {API}/v1/refunds -d charge={CH}')\nPYEOF", "deny")
case("bash heredoc IS shell and is still segmented",
     f"bash <<'SHEOF'\ncurl -X POST {API}/v1/refunds -d charge={CH}\nSHEOF", "deny")
case("bash heredoc reading the key file", "bash <<'SHEOF'\ncat ~/.config/stripe/live-key\nSHEOF",
     "deny")


def run(cmd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                          "cwd": "/Users/zalo/dev"})
    p = subprocess.run(["python3", HOOK], input=payload, capture_output=True, text=True)
    return ("allow" if p.returncode == 0 else "deny"), p.stdout + p.stderr


def main():
    fails = 0
    for label, cmd, expected in CASES:
        got, output = run(cmd)
        ok = got == expected
        if not ok:
            fails += 1
        print(f"{'PASS ' if ok else 'FAIL '}| expected {expected:5} got {got:5} | {label}")
        if not ok:
            print("        cmd: " + cmd.replace("\n", "\\n")[:160])
            if output.strip():
                print("        out: " + output.strip().split("\n")[0][:160])

    # Non-Bash tools must be ignored entirely.
    extra_fails = 0
    other = subprocess.run(
        ["python3", HOOK],
        input=json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": "/tmp/x", "new_string": FAKE_SK}}),
        capture_output=True, text=True)
    if other.returncode != 0:
        print("FAIL  | non-Bash tool payload should be ignored")
        extra_fails += 1
    else:
        print("PASS  | non-Bash tool payload ignored")

    for label, payload in (("malformed json", "not json at all"),
                           ("bare string payload", '"hello"'),
                           ("missing tool_input", '{"tool_name": "Bash"}'),
                           ("empty command", '{"tool_name":"Bash","tool_input":{"command":""}}')):
        p = subprocess.run(["python3", HOOK], input=payload, capture_output=True, text=True)
        if p.returncode != 0:
            print(f"FAIL  | {label} should not block (got exit {p.returncode})")
            extra_fails += 1
        else:
            print(f"PASS  | {label} does not block")

    # The block message must name the wrapper and be honest about the limit.
    _, msg = run("cat ~/.config/stripe/live-key")
    required = ["stripe-money.py", "cannot see inside a script file",
                "no in-band override", "--dry-run"]
    missing = [r for r in required if r not in msg]
    if missing:
        print(f"FAIL  | block message is missing: {missing}")
        extra_fails += 1
    else:
        print("PASS  | block message names the wrapper and states the hook's limit")

    total = len(CASES) + 6
    passed = total - fails - extra_fails
    print(f"\n{passed}/{total} passed, {fails + extra_fails} failed")
    return 1 if (fails or extra_fails) else 0


if __name__ == "__main__":
    sys.exit(main())
