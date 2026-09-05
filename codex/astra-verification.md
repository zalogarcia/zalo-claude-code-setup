# Astra verification evidence

Required commands ran on 2026-09-04 in /Users/zalo/.claude.

`python3 scripts/codex-sync.test.py` exited 0:

```text
65/65 passed, 0 failed
```

`python3 hooks/codex-shim.test.py` exited 0:

```text
39/39 passed, 0 failed
```

`python3 scripts/codex-sync.py all` exited 1:

```text
PermissionError: [Errno 1] Operation not permitted: '/Users/zalo/.codex/agents/brainstorm.toml.tmp.70634'
```

`python3 scripts/codex-sync.py check` exited 1:

```text
STALE: 4 projected file(s) differ from the source.
  /Users/zalo/.codex/agents/brainstorm.toml
  /Users/zalo/.codex/agents/bug-fix.toml
  /Users/zalo/.codex/agents/qa-agent.toml
  /Users/zalo/.codex/agents/safe-planner.toml
```

Generated-file searches returned:

```text
49:## GPT-6 Astra behavior
6:model = "gpt-5.6-sol"
7:model_reasoning_effort = "xhigh"
```

The first line is from ~/.codex/AGENTS.md; the last two are from the generated
brainstorm.toml. The manual was already refreshed when the explicit all command
ran, consistent with the configured edit hook. The explicit sync failed at the
first changed agent. No hook trust warning was emitted. The hooks projection
does not appear in the subsequent stale list.

An additional in-memory run of gen_agents parsed all eight generated TOMLs and
asserted four Astra xhigh pairs and four GPT-5.5 high pairs. It passed without
writing generated files. This verifies generation logic, not live agent loading.

`bash -n skills/codex/codex-run.sh` exited 0. Reading its complete argv builder
and checking parameter names found zero sampling parameters and no effort
override. It inherits the CLI's effective reasoning effort. No wrapper script
change was needed. The TypeScript build skill was reviewed; this Python and
documentation change has no TypeScript build to run.

External proposals were applied in memory: six of six hunks across four diffs
matched current source bytes and line counts. Proposed JSON and TOML parsed.
No external bridge or top-level config edits were applied.

Activation remains blocked by the workspace sandbox. The reviewer must run
the all and check commands from a session authorized to write the generated
directories. No git mutations were performed.

Independent light QA reviewed six of six implementation surfaces. Its two
wording findings were corrected and confirmed by fresh reads: preparation now
precedes clarification as well as approval, and subscription usage wording is
consistent. No remaining finding was reported in that confirmation.

After the wording fixes, sync check still reports exactly the same four stale
agent files. The live generated manual contains both the Astra section and
the corrected approval or clarification sentence.

All nine authored files were checked with the requested Python regular
expression for U+2013 and U+2014. Each returned 0. This checks authored source
and reports; existing verbatim embedded manuals and generated agent bodies
were not globally rewritten to remove their historical punctuation.
