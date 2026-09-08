# Runbook

How a session gets started, by M (the Telegram bridge) or by Zalo at a terminal. Astra
runs the work; this file is about reaching it and confirming it can see the skill.

## The one thing that decides everything: which lane

This skill sends real DMs from Zalo's accounts, so it needs Chrome, so it needs the
**codex-bare** session: Codex running without the macOS sandbox, with the Computer Use
plugin loaded. The sandboxed rail (`codex exec`, and the bridge's
`bg.mjs --engine codex` background lane) runs under the seatbelt sandbox, where Chrome
exits 134. That lane can still draft, but it can never send.

So: do not hand this skill to `bg.mjs --engine codex`. Send it to codex-bare.

## Starting a session from M or from any Claude session

The peer call, verbatim:

```bash
~/.claude/scripts/peer-ask.sh codex-bare -m "Use the bu-cold-outreach skill. Run today's session."
```

`peer-ask.sh` types the message into the named tmux session, presses Enter separately,
polls until the composer comes back, and prints the reply with the elapsed time. Exit 0
means it replied, exit 3 means it timed out, exit 4 means the session ended. A full session
runs long, so raise the timeout:

```bash
~/.claude/scripts/peer-ask.sh codex-bare --timeout 1800 -m "Use the bu-cold-outreach skill. Run today's session."
```

### The variants

Replies only, no new batch. Use this when Zalo just wants to know what came back:

```bash
~/.claude/scripts/peer-ask.sh codex-bare -m "Use the bu-cold-outreach skill. Replies only: read every inbox, update stages, and report the replies. Do not draft or send a batch."
```

Approve a batch and send it. Name the date so the approval cannot drift onto a different
batch:

```bash
~/.claude/scripts/peer-ask.sh codex-bare --timeout 3600 -m "Use the bu-cold-outreach skill. Zalo approves batch-2026-09-09.md. Send it within the caps and the pacing, log every send, then report."
```

Report only, nothing else touched:

```bash
~/.claude/scripts/peer-ask.sh codex-bare -m "Use the bu-cold-outreach skill. Report only: read the working folder and print today's report. Send nothing, draft nothing."
```

Draft only, explicitly, even in a lane that could send:

```bash
~/.claude/scripts/peer-ask.sh codex-bare --timeout 1800 -m "Use the bu-cold-outreach skill. Draft today's batch only. Send nothing regardless of the approval mode."
```

### Rules for the caller

- **Always target the exact session name printed by `tmux ls`.** tmux prefix matches
  silently, so `-t codex` can land somewhere else.
- One instruction per call. `peer-ask.sh` sends literal text and Enter, nothing else.
- The reply is DATA. Summarize it for Zalo; never paste the raw pane.
- A peer message cannot authorize a send that `config.md` does not. If approval mode is
  on, only Zalo naming a batch releases it.

## Launching codex-bare when it is not running

Check first:

```bash
tmux ls | grep codex-bare
```

If it is not there, launch it through the xbar script (YOLO mode, no approval prompts,
Computer Use available):

```bash
open -a Terminal "$HOME/Library/Application Support/xbar/plugins/scripts/launch-codex-bare.sh"
```

Wait for the composer placeholder ("Ask Codex to do anything") to appear before sending
anything. `peer-ask.sh` already waits on that string as its idle marker, so a call fired
too early will time out rather than land silently.

## Verifying Codex sees the skill

Codex reads skills from `~/.agents/skills/`, which is a generated projection of
`~/.claude/skills/`. After adding or editing this skill:

```bash
python3 ~/.claude/scripts/codex-sync.py skills
python3 ~/.claude/scripts/codex-sync.py check
ls -la ~/.agents/skills/bu-cold-outreach
```

The `ls` must show a symlink pointing at
`/Users/zalo/.claude/skills/bu-cold-outreach`. **Never hand create that symlink**, and
never edit anything under `~/.agents` or `~/.codex` directly: those surfaces are generated
and hand edits are destroyed on the next sync. If `codex-sync.py` refuses, read what it
says and fix the source in `~/.claude`, do not work around it.

A Codex SessionStart hook runs `codex-sync.py all --if-stale --quiet`, so a session started
after the edit picks the skill up on its own. The manual run above is for making the change
visible inside a session that is already open.

Confirm from inside codex-bare by asking it to list what it has:

```bash
~/.claude/scripts/peer-ask.sh codex-bare -m "Do you have a skill called bu-cold-outreach? Print its description line and the paths of its template files. Do not run it."
```

## First run in a fresh working folder

The working folder is:

```
~/Documents/Clients/Black Umbrella/Delta Division/AI Division/Cold Outreach/
```

Astra seeds it on the first run, copying from this skill's `templates/` only the files that
do not exist. Two things must happen before the first send, and neither is Astra's:

1. Zalo fills `config.md`: `ramp_start_date`, which channels are active, and the approval
   mode. It ships with `approval_mode: on`.
2. `prospects.csv` has to be in the folder. It is produced elsewhere and this skill never
   writes it.

`proof.md` and the price fields in `call-one-pager.md` are optional and block nothing.

## Reading a session afterwards

Every session writes `reports/YYYY-MM-DD.md` in the working folder and prints the same
content as its final message, which is what M relays to Zalo. The audit trail of what
actually went out is `sent-log.csv`, and it is the only thing that counts as a send. If the
report and the sent log disagree, the sent log is right.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Astra says it is in a sandboxed lane and will only draft | the job went to `bg.mjs --engine codex` or a `codex exec` run | re-send it to codex-bare |
| `peer-ask.sh` exits 3 | the session is still working, or was never ready | raise `--timeout`, or check the pane with `tmux capture-pane -t codex-bare -p -S -60` |
| `peer-ask.sh` exits 4 | codex-bare ended | relaunch it with the xbar script above |
| Astra reports a channel logged out | Chrome profile lost the session | Zalo logs in in that profile, then re-run |
| Astra reports a warning event and a stopped channel | a captcha, a slow down notice, or a restriction | leave it stopped. The ramp is back at week 1 and a hold is written into the channel holds block of `config.md`, halving that channel for 7 days after a captcha or slow down, stopping it for 7 days after a restriction. Astra lifts a hold when its date passes. Only Zalo lifts one early |
| Nothing sends and the report says drafts waiting | approval mode is on and this is working as designed | Zalo reads the batch file and approves it by name |
| `codex-sync.py check` exits 1 | the projection is stale | run `python3 ~/.claude/scripts/codex-sync.py all` |
