#!/bin/bash
# fable-weekly-insights.sh — headless weekly self-audit runner for launchd.
# Runs the 'fable-insights' Workflow (manifest -> per-session analysis -> stubs)
# via `claude -p`, then has the session synthesize the weekly HTML report, the
# raw facets JSON, and a PROPOSED_CHANGES markdown (proposals only, no config
# changes applied).
#
# Loaded by: ~/Library/LaunchAgents/com.zalo.claude-weekly-insights.plist
# Log:       ~/.claude/usage-data/weekly-insights.log

set -u

# ---- PATH so `claude`, `jq`, `node` resolve under launchd's minimal env --------
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ] && [ -x "$HOME/.local/bin/claude" ]; then
  CLAUDE_BIN="$HOME/.local/bin/claude"
fi

USAGE_DIR="$HOME/.claude/usage-data"
LOG_FILE="$USAGE_DIR/weekly-insights.log"
mkdir -p "$USAGE_DIR"

# All output (ours + claude's) appends to the log.
exec >> "$LOG_FILE" 2>&1

echo ""
echo "===================================================================="
echo "=== fable-weekly-insights run: $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo "===================================================================="

if [ -z "$CLAUDE_BIN" ]; then
  echo "FATAL: claude CLI not found on PATH and no $HOME/.local/bin/claude — aborting."
  exit 1
fi
echo "claude binary: $CLAUDE_BIN ($("$CLAUDE_BIN" --version 2>/dev/null || echo 'version unknown'))"

# ---- lockfile: guard against overlapping runs ----------------------------------
LOCKFILE="/tmp/fable-weekly-insights.lock"
if [ -e "$LOCKFILE" ]; then
  OLD_PID="$(cat "$LOCKFILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "SKIP: previous run still active (pid $OLD_PID) — not starting a second one."
    exit 0
  fi
  echo "Stale lockfile found (pid ${OLD_PID:-unknown} not running) — removing."
  rm -f "$LOCKFILE"
fi
echo "$$" > "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# ---- output paths (bash stamps the dates; workflow scripts cannot) --------------
TODAY="$(date +%F)"
REPORT_PATH="$USAGE_DIR/report-fable-weekly-$TODAY.html"
FACETS_PATH="$USAGE_DIR/fable-facets-weekly-$TODAY.json"
PROPOSED_PATH="$USAGE_DIR/PROPOSED_CHANGES-$TODAY.md"
REFERENCE_REPORT="$USAGE_DIR/report-fable-2026-07-11.html"

cd "$HOME"

PROMPT="Run the Workflow named 'fable-insights' with args {\"days\": 7}. It returns {facets, stubs, failed, manifest_counts}.

When it returns, produce exactly three artifacts:

1. $FACETS_PATH — write the raw workflow result as pretty-printed JSON: {facets, stubs, failed, manifest_counts}. This is the machine-readable record for week-over-week comparison.

2. $REPORT_PATH — a fully self-contained HTML report (all CSS inline, no external requests) synthesizing the facets: outcomes and satisfaction distributions, per-project breakdown, verification-quality split, friction clusters ranked by frequency with root causes and avoidability, wasted-cycles themes, standouts, and notable quotes. Before writing it, Read $REFERENCE_REPORT and match its structure and section order — this weekly report should be directly comparable to that one. Week-over-week: look for the newest previous facets file matching $USAGE_DIR/fable-facets-weekly-*.json (excluding today's) — or, if none exists yet, $USAGE_DIR/fable-facets-*.json — and if found, add a comparison section (outcome/satisfaction/friction deltas vs that week). If no previous facets file exists, state that this is the baseline week.

3. $PROPOSED_PATH — a markdown file of concrete proposed changes to ~/.claude (rules, hooks, skills, CLAUDE.md) derived from recurring friction in this week's facets. Each proposal must cite the friction cluster that motivates it (with session counts) and show the concrete proposed diff or new-file content. IMPORTANT: proposals ONLY — do NOT apply any config changes, do NOT edit any file under ~/.claude other than writing these three artifacts into $USAGE_DIR.

Finish by printing a one-paragraph summary: sessions analyzed, failures, top friction cluster, and the three artifact paths."

echo "Launching claude -p (model: fable, workflow: fable-insights, days: 7)..."
START_TS=$(date +%s)

# Tool scoping (security): this run ingests raw session transcripts — untrusted
# third-party content (fetched web pages, API error payloads) that could carry
# prompt injections — with nobody watching. So no blanket Bash, no Edit, and
# Write only into the usage-data output dir. The Bash specifiers below cover
# exactly the commands the fable-insights workflow's extraction recipes use.
"$CLAUDE_BIN" -p "$PROMPT" \
  --model fable \
  --allowedTools "Read,Glob,Grep,Workflow,Agent,Bash(jq:*),Bash(find:*),Bash(grep:*),Bash(head:*),Bash(tail:*),Bash(wc:*),Bash(date:*),Bash(stat:*),Bash(lsof:*),Bash(sort:*),Bash(uniq:*),Bash(cut:*),Bash(basename:*),Bash(ls:*),Write(~/.claude/usage-data/**)" \
  --disallowedTools "Edit,Skill,Bash(curl:*),Bash(wget:*),Bash(git:*),Write(//Users/**/.claude/hooks/**),Write(//Users/**/.claude/settings.json),Write(//Users/**/.claude/CLAUDE.md)"
# Residual risk (documented, accepted 2026-07-11): Bash prefix rules cannot
# express "sort without -o" or "find without -exec" — an injected instruction
# could still abuse those flags for bash-level file writes. Primary containment
# is the absence of curl/wget/git/sh and the Write/Edit scoping above; the
# weekly PROPOSED_CHANGES review is the human backstop. Do not widen this list.
CLAUDE_EXIT=$?

END_TS=$(date +%s)
echo ""
echo "--- claude exited with code $CLAUDE_EXIT after $((END_TS - START_TS))s ---"

# ---- post-run artifact check (existence, not correctness) -----------------------
for f in "$REPORT_PATH" "$FACETS_PATH" "$PROPOSED_PATH"; do
  if [ -s "$f" ]; then
    echo "OK: $f ($(wc -c < "$f" | tr -d ' ') bytes)"
  else
    echo "MISSING/EMPTY: $f"
  fi
done

echo "=== run complete: $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
exit "$CLAUDE_EXIT"
