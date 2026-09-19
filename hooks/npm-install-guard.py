#!/usr/bin/env python3
"""PreToolUse guard: agent-initiated package installs.

Why this exists
---------------
2026-08-04, npm supply chain: keyv 6.0.0, flat-cache 6.1.24,
file-entry-cache 11.1.6, cacheable-request 13.0.20, cache-manager 7.2.10 and
7 sibling packages were published with a `preinstall` dropper (setup.mjs +
Math_Symbol.js). It ran during `npm install`, before install even finished,
and harvested npm tokens, GitHub PATs and OIDC tokens, AWS creds, Vault and
K8s tokens, Stripe and Slack keys, SSH keys, .env files and Terraform state.
433+ further packages were infected by worm propagation. Detection came within
hours of publish, which is exactly the window a cooldown closes.

Zalo's box was clean (his lockfiles pinned older versions), but the exposure
shape is specific and worth naming: HE does not type `npm install`. Autopilot
runs, /goal loops and the Telegram bg workers do, unsupervised, at 3am, on a
machine holding live Supabase, Stripe, Retell, ISN, Telegram and OpenAI creds.
Every Bash tool call is by definition agent-initiated — so this guard gates
all of them, and Zalo stays completely free in his own terminal.

Division of labour with ~/.npmrc
-------------------------------
`min-release-age=7` in ~/.npmrc covers the WHOLE dependency tree including
transitive deps, which is what actually matters (keyv is nearly always
transitive). But it needs npm >= 11.10.0 and the box had 10.9.2, where the key
is silently ignored. So this hook enforces the same 7-day cooldown itself, for
direct installs, over the live registry — protection that does not wait on the
npm upgrade. Once npm is upgraded the two overlap, deliberately.

What it BLOCKS
--------------
1. Installing a named package that is not already a dependency of the repo
   being worked in. Adding a dependency is a decision, not a mechanical step.
2. Installing a named package whose resolved version is younger than 7 days,
   even when it IS already a dependency.
3. Bare `npm install` in a repo that has a lockfile -> must be `npm ci`, which
   installs exactly the lockfile and cannot pull a new version through a caret
   range. This is most of why the keyv wave missed this machine.
4. Global installs (`-g` / `--global`) — system-wide, needs a human.
5. Anything that weakens the protections: `--min-release-age` below 7,
   `--ignore-scripts=false`, `npm config set min-release-age <7`.
6. yarn add / pnpm add / bun add equivalents.

What it ALLOWS
--------------
`npm ci` (any flags), `npm run|test|rebuild|ls|view|outdated|audit|why`,
bare `npm install` where no lockfile exists yet, re-installing an existing
dependency that has cleared the cooldown, and every non-install command.

KNOWN GAP (deliberate, documented rather than half-guarded)
-----------------------------------------------------------
`npx <pkg>` downloads and executes in one step and is NOT gated here — `npx
tsx`, `npx playwright`, `npx supabase` are load-bearing across these repos and
blocking them would break far more than it protects. `npm ci`/`--ignore-
scripts` do not cover it either. If that gap ever needs closing, gate npx on
"is this package already in node_modules" rather than on the registry.

There is no in-band override. If Zalo wants a package installed, he installs it
in his own terminal. Do not work around this guard — report the block.

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import json
import os
import re
import shlex
import sys
from urllib.parse import quote

COOLDOWN_DAYS = 7
REGISTRY = "https://registry.npmjs.org"
NET_TIMEOUT = 6

# Subcommands that add/resolve packages from the registry.
INSTALL_VERBS = {
    "npm": {"install", "i", "add", "in", "ins", "isnt", "isntall", "install-test", "it"},
    "yarn": {"add", "install"},
    "pnpm": {"add", "install", "i"},
    "bun": {"add", "install"},
}
# Subcommands that are safe: they never resolve a NEW version from the registry.
SAFE_VERBS = {
    "ci",
    "run",
    "run-script",
    "test",
    "start",
    "rebuild",
    "ls",
    "list",
    "view",
    "info",
    "outdated",
    "audit",
    "why",
    "exec",
    "link",
    "pack",
    "version",
    "publish",
    "whoami",
    "ping",
    "dedupe",
    "prune",
    "uninstall",
    "remove",
    "rm",
    "un",
}

OPERATORS = {"&&", "||", ";", "|", "&", "\n"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(command: str) -> str:
    """Remove heredoc BODIES before parsing.

    Writing a brief or a doc that CONTAINS the text `npm install foo` is not
    installing anything, but shlex would happily tokenise the heredoc body and
    read it as a command. Since a lot of what gets written on this box is
    exactly that (worker briefs, rules files, this hook's own docstring), the
    body is dropped and only the surrounding command is parsed.
    """
    lines = command.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = HEREDOC_RE.search(line)
        i += 1
        if not m:
            continue
        delim = m.group(2)
        while i < len(lines) and lines[i].strip() != delim:
            i += 1
        if i < len(lines):
            i += 1  # consume the terminator too
    return "\n".join(out)


def segments(command: str, _depth: int = 0):
    """Split a shell command into candidate sub-commands, as TOKEN LISTS.

    Tokenising BEFORE splitting is the whole point. An earlier version split
    the raw text on `&&|;|` first, which tore quoted strings apart: a perfectly
    innocent

        grep -h "npm install\\|npm i " file

    was cut at the `\\|` inside the quotes and the fragment `npm i " file` read
    as an install of a package literally named `"`. That is the failure mode
    that teaches agents to route around a guard instead of reporting it, so it
    matters more than it looks. shlex keeps a quoted string as ONE token, so
    text that merely MENTIONS an install command is never mistaken for one.

    `punctuation_chars=True` makes `;`, `|`, `&&` separate tokens even when not
    space-padded (`echo hi;npm install x`).

    Also unwraps `bash -c "..."` one level — the obvious smuggling route.
    """
    out = []
    for line in strip_heredocs(command).splitlines():
        # Newlines must be split BEFORE tokenising: shlex treats "\n" as plain
        # whitespace, so `echo hi\nnpm install evil` would collapse into one
        # segment starting with `echo` and sail straight past this guard.
        if not line.strip():
            continue
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            tokens = list(lex)
        except ValueError:
            # Unbalanced quotes: fall back to a naive split rather than
            # allowing the line through unexamined.
            tokens = line.split()

        cur = []
        for tok in tokens:
            if tok in OPERATORS:
                if cur:
                    out.append(cur)
                    cur = []
            else:
                cur.append(tok)
        if cur:
            out.append(cur)

    if _depth < 2:
        for seg in list(out):
            if (
                len(seg) >= 3
                and os.path.basename(seg[0]) in SHELLS
                and seg[1].startswith("-")
                and "c" in seg[1]
            ):
                out.extend(segments(seg[2], _depth + 1))
    return out


def find_package_json(start: str):
    """Walk up from `start` looking for a package.json (max 4 levels)."""
    cur = os.path.abspath(start or ".")
    for _ in range(4):
        candidate = os.path.join(cur, "package.json")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def existing_deps(cwd: str):
    """Every dependency name already declared in the nearest package.json."""
    pj = find_package_json(cwd)
    if not pj:
        return set(), None
    try:
        with open(pj) as fh:
            data = json.load(fh)
    except Exception:
        return set(), pj
    names = set()
    for field in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        names.update((data.get(field) or {}).keys())
    return names, pj


def has_lockfile(cwd: str):
    pj = find_package_json(cwd)
    if not pj:
        return False
    root = os.path.dirname(pj)
    return any(
        os.path.isfile(os.path.join(root, f))
        for f in ("package-lock.json", "npm-shrinkwrap.json")
    )


def split_spec(spec: str):
    """'foo@1.2.3' -> ('foo','1.2.3'); '@scope/foo@1.2.3' -> ('@scope/foo','1.2.3')."""
    if spec.startswith("@"):
        at = spec.find("@", 1)
        if at == -1:
            return spec, None
        return spec[:at], spec[at + 1 :] or None
    name, _, version = spec.partition("@")
    return name, version or None


def age_days(name: str, version: str | None):
    """Days since `version` (or dist-tags.latest) was published. None = unknown.

    Shells out to curl rather than urllib on purpose: this box's system python
    has no usable CA bundle (`CERTIFICATE_VERIFY_FAILED` on every https call),
    which made urllib return None for every package and — because this guard
    fails closed — would have blocked every install on the machine. curl works.
    """
    import datetime
    import subprocess

    url = f"{REGISTRY}/{quote(name, safe='@/')}"
    try:
        proc = subprocess.run(
            ["curl", "-sSf", "--max-time", str(NET_TIMEOUT), url],
            capture_output=True,
            timeout=NET_TIMEOUT + 4,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None, None
        meta = json.loads(proc.stdout)
    except Exception:
        return None, None
    times = meta.get("time") or {}
    resolved = version
    if not resolved or resolved not in times:
        resolved = (meta.get("dist-tags") or {}).get("latest")
    stamp = times.get(resolved)
    if not stamp:
        return None, resolved
    try:
        published = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except Exception:
        return None, resolved
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - published).total_seconds() / 86400.0, resolved


HEADER = "BLOCKED (npm-install-guard): "
FOOTER = (
    "\nThere is no in-band override. If this package genuinely needs to be\n"
    "added, say so and let Zalo run it in his own terminal. Do not rewrite the\n"
    "command to get around this guard — report the block instead.\n"
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on a malformed payload

    if payload.get("tool_name") != "Bash":
        return 0

    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or "")
    if not command.strip():
        return 0
    cwd = payload.get("cwd") or os.getcwd()

    for tokens in segments(command):
        if not tokens:
            continue
        seg = " ".join(tokens)

        # Strip a leading env-var assignment prefix (FOO=bar npm install ...).
        idx = 0
        while idx < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[idx]):
            idx += 1
        tokens = tokens[idx:]
        if not tokens:
            continue

        binary = os.path.basename(tokens[0])
        if binary not in INSTALL_VERBS:
            continue
        rest = tokens[1:]
        if not rest:
            continue

        flags = [t for t in rest if t.startswith("-")]
        args = [t for t in rest if not t.startswith("-")]
        verb = args[0] if args else ""

        # `npm config set min-release-age <N>` — never let the floor be lowered.
        if verb == "config" and len(args) >= 4 and args[1] == "set":
            key = args[2]
            if key.replace("_", "-") in ("min-release-age", "minimumreleaseage"):
                val = args[3] if len(args) > 3 else ""
                try:
                    if int(val) < COOLDOWN_DAYS:
                        sys.stderr.write(
                            f"{HEADER}lowering the install cooldown.\n\n"
                            f"  {seg}\n\n"
                            f"min-release-age is the 7-day floor that keeps this box from being\n"
                            f"the first to install a fresh compromise. It is set deliberately in\n"
                            f"~/.npmrc after the 2026-08-04 keyv/flat-cache attack.\n" + FOOTER
                        )
                        return 2
                except ValueError:
                    pass
            continue

        if verb not in INSTALL_VERBS[binary]:
            if verb in SAFE_VERBS:
                continue
            continue

        # --- weakening flags ---------------------------------------------
        joined = " ".join(flags)
        if re.search(r"--ignore-scripts[= ]*false", joined):
            sys.stderr.write(
                f"{HEADER}--ignore-scripts=false re-enables install scripts.\n\n"
                f"  {seg}\n\n"
                "The 2026-08-04 keyv compromise executed entirely through a\n"
                "`preinstall` script. Do not turn that surface back on.\n" + FOOTER
            )
            return 2
        m = re.search(r"--min-release-age[= ]*(\d+)", joined)
        if m and int(m.group(1)) < COOLDOWN_DAYS:
            sys.stderr.write(
                f"{HEADER}--min-release-age below the {COOLDOWN_DAYS}-day floor.\n\n"
                f"  {seg}\n" + FOOTER
            )
            return 2

        # --- global installs ---------------------------------------------
        if any(f in ("-g", "--global") for f in flags):
            sys.stderr.write(
                f"{HEADER}global install.\n\n"
                f"  {seg}\n\n"
                "A -g install changes the whole machine, outside any repo or\n"
                "lockfile, and usually needs sudo anyway.\n" + FOOTER
            )
            return 2

        packages = args[1:]

        # --- bare install: must be `npm ci` when a lockfile exists ---------
        if not packages:
            if binary == "npm" and has_lockfile(cwd):
                sys.stderr.write(
                    f"{HEADER}bare `npm install` where a lockfile exists.\n\n"
                    f"  {seg}\n\n"
                    "`npm install` re-resolves caret ranges and can silently pull a\n"
                    "newly published version into the tree — exactly how the\n"
                    "2026-08-04 keyv/flat-cache wave spread. `npm ci` installs the\n"
                    "lockfile verbatim and cannot.\n\n"
                    "Use instead:\n"
                    "  npm ci\n" + FOOTER
                )
                return 2
            continue

        # --- named packages ------------------------------------------------
        deps, pj = existing_deps(cwd)
        for spec in packages:
            name, version = split_spec(spec)
            if not name:
                continue

            if name not in deps:
                where = pj or "(no package.json found)"
                sys.stderr.write(
                    f"{HEADER}adding a NEW dependency.\n\n"
                    f"  {seg}\n"
                    f"  package: {name}\n"
                    f"  not declared in: {where}\n\n"
                    "Adding a dependency is a decision, not a mechanical step, and\n"
                    "unsupervised 3am installs are the exposure this guard exists\n"
                    "for: a typosquat or a compromised publish lands its preinstall\n"
                    "script on a box holding live Supabase, Stripe, Retell, ISN,\n"
                    "Telegram and OpenAI credentials.\n\n"
                    "Prefer finishing the task without the dependency. If it is\n"
                    "genuinely required, say which package and why.\n" + FOOTER
                )
                return 2

            days, resolved = age_days(name, version)
            if days is None:
                sys.stderr.write(
                    f"{HEADER}could not verify publish age for {name}.\n\n"
                    f"  {seg}\n\n"
                    f"The registry lookup failed or returned no timestamp, so the\n"
                    f"{COOLDOWN_DAYS}-day cooldown cannot be confirmed. This guard fails\n"
                    "closed on purpose.\n" + FOOTER
                )
                return 2
            if days < COOLDOWN_DAYS:
                sys.stderr.write(
                    f"{HEADER}{name}@{resolved} is {days:.1f} days old.\n\n"
                    f"  {seg}\n\n"
                    f"The {COOLDOWN_DAYS}-day cooldown is not met. Malicious publishes are\n"
                    "typically caught within hours; waiting the window out means this\n"
                    "box is never the one that installs a compromise first. The\n"
                    "2026-08-04 keyv wave was detected the same day it shipped.\n\n"
                    f"Pin a version older than {COOLDOWN_DAYS} days, or wait.\n" + FOOTER
                )
                return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
