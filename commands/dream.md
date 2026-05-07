# /dream — Memory Consolidation (Local Dreams)

Local equivalent of Anthropic Managed Agents "Dreams" feature. Reads recent session transcripts + current memory store and produces a review-then-apply proposal of memory mutations (deduplications, contradictions, stale-reference removals, recurring-pattern additions).

**Scope:** memory files only (`~/.claude/projects/-Users-zalo/memory/`). Does NOT touch `~/.claude/rules/` or `~/.claude/CLAUDE.md`.

**Trigger:** manual only. No cron, no hook. You decide when to consolidate.

**Apply mode:** always review-first. Proposals are written to disk; nothing mutates the live memory store until you run `/dream apply <id>`.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/verification-patterns.md
@~/.claude/rules/anti-patterns.md

## Subcommands

| Invocation            | What it does                                                  |
| --------------------- | ------------------------------------------------------------- |
| `/dream`              | Run a new consolidation pass with default 7-day window        |
| `/dream --days=N`     | Run with custom lookback window (e.g., `/dream --days=30`)    |
| `/dream list`         | List existing proposals in `~/.claude/dreams/`                |
| `/dream apply <id>`   | Apply the proposal at `~/.claude/dreams/<id>/` to live memory |
| `/dream discard <id>` | Delete the proposal directory                                 |
| `/dream show <id>`    | Print the proposal.md to terminal                             |
| `/dream diff <id>`    | Show `diff -r current_memory output_memory` for the proposal  |

## Workflow — `/dream` (run new)

### Step 1: Pre-flight

```bash
mkdir -p ~/.claude/dreams
DREAM_ID=$(date -u +%Y-%m-%d-%H%M%S)  # second-resolution prevents collisions on rapid re-runs
WINDOW_DAYS=${1:-7}  # parsed from --days=N, default 7
MEMORY_DIR=~/.claude/projects/-Users-zalo/memory
OUTPUT_DIR=~/.claude/dreams/$DREAM_ID

# Pre-create the proposal package subdirs so the agent's `cp -R src/* dst/`
# snapshot step succeeds (cp requires destination dir to exist).
mkdir -p "$OUTPUT_DIR/current_memory" "$OUTPUT_DIR/output_memory"
```

Verify:

- `[ -d "$MEMORY_DIR" ]` — memory dir exists. If not → ABORT: "Memory directory not found at $MEMORY_DIR. Initialize the auto-memory system first."
- `[ -f "$MEMORY_DIR/MEMORY.md" ]` — MEMORY.md index exists. If not → continue but warn (the agent will rebuild the index).
- `[ ! -d "$OUTPUT_DIR/proposal.md" ]` — proposal not yet written for this id. (DREAM_ID has second resolution; near-zero collision risk, but the guard is real protection — never remove it.)

### Step 2: Dispatch dream-consolidator

```
Dispatch dream-consolidator (model: "opus") with prompt:
  """
  Run a memory consolidation pass.

  Dream ID: {DREAM_ID}
  Window: {WINDOW_DAYS} days
  Memory directory: {MEMORY_DIR}
  Transcript root: ~/.claude/projects/

  Follow the 3-phase pipeline in your agent definition (Orient → Consolidate → Output).

  Write the proposal package to ~/.claude/dreams/{DREAM_ID}/:
    - current_memory/   (snapshot of live memory dir at start)
    - output_memory/    (proposed new state)
    - proposal.md       (human-readable summary)
    - changes.json      (machine-readable mutation list)

  Emit ## DREAM PROPOSAL READY when written.
  Emit ## DREAM NO_CHANGES_NEEDED if memory is already clean.
  Emit ## BLOCKED if you cannot proceed.
  """
```

### Step 3: Handle the marker

- `## DREAM PROPOSAL READY` →

  **Step 3a: Verify the proposal package shape before claiming "ready".** The agent's marker is a self-report; the slash command's own anti-patterns forbid trusting it without verification.

  ```bash
  for f in proposal.md changes.json; do
    [ -f "$OUTPUT_DIR/$f" ] || {
      echo "MALFORMED: agent emitted PROPOSAL READY but $f is missing."
      echo "Inspect: ls -la $OUTPUT_DIR"
      echo "Discard: rm -rf $OUTPUT_DIR"
      exit 1
    }
  done
  for d in current_memory output_memory; do
    [ -d "$OUTPUT_DIR/$d" ] || {
      echo "MALFORMED: agent emitted PROPOSAL READY but $d/ is missing."
      echo "Inspect: ls -la $OUTPUT_DIR"
      echo "Discard: rm -rf $OUTPUT_DIR"
      exit 1
    }
    # Snapshot dirs must be non-empty (agent should have populated them)
    [ -n "$(ls -A "$OUTPUT_DIR/$d" 2>/dev/null)" ] || {
      echo "MALFORMED: $d/ exists but is empty — agent did not write its expected content."
      exit 1
    }
  done
  # Validate changes.json is parseable JSON
  python3 -c "import json; json.load(open('$OUTPUT_DIR/changes.json'))" 2>/dev/null || {
    echo "MALFORMED: changes.json is not valid JSON."
    exit 1
  }
  ```

  Only after all checks pass, print the success summary:

  ```
  Dream proposal ready: {DREAM_ID}
  Actions proposed: {N} (HIGH: x, MEDIUM: y, LOW: z)

  Review:
    /dream show {DREAM_ID}     # see the proposal
    /dream diff {DREAM_ID}     # see file-level diff

  Apply or discard:
    /dream apply {DREAM_ID}
    /dream discard {DREAM_ID}
  ```

  STOP. Do not auto-apply.

- `## DREAM NO_CHANGES_NEEDED` → print: "Memory is already clean — no consolidation actions found in the {N}-day window. Empty proposal directory removed."
  - `rm -rf ~/.claude/dreams/{DREAM_ID}` (delete the empty proposal)

- `## BLOCKED` → print the agent's reason. Suggest fixes (check transcript permissions, memory dir presence, etc.)

## Workflow — `/dream apply <id>`

Applies a proposal. Performs staleness detection, executes mutations, optionally commits.

### Step 1: Validate

```bash
[ -n "$1" ] || { echo "Usage: /dream apply <id>"; exit 1; }
PROPOSAL=~/.claude/dreams/"$1"
[ -d "$PROPOSAL" ] || { echo "No proposal at $PROPOSAL"; exit 1; }
[ -f "$PROPOSAL/changes.json" ] || { echo "Malformed proposal (missing changes.json)"; exit 1; }
[ -d "$PROPOSAL/current_memory" ] || { echo "Malformed proposal (missing snapshot)"; exit 1; }
[ -d "$PROPOSAL/output_memory" ] || { echo "Malformed proposal (missing output_memory)"; exit 1; }
```

### Step 2: Staleness check

The memory dir may have changed since the proposal was generated (you may have manually edited memory between `/dream` and `/dream apply`). If so, applying could clobber unrelated changes.

```bash
# Compute current hash of live memory
LIVE_HASH=$(find ~/.claude/projects/-Users-zalo/memory -type f -name "*.md" -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1)

# Compute hash of proposal's current_memory snapshot
SNAPSHOT_HASH=$(find $PROPOSAL/current_memory -type f -name "*.md" -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1)

if [ "$LIVE_HASH" != "$SNAPSHOT_HASH" ]; then
  echo "STALE: live memory changed since this proposal was generated."
  echo "Diff: live ($LIVE_HASH) vs snapshot ($SNAPSHOT_HASH)"
  echo "Options:"
  echo "  1. Inspect: diff -r $PROPOSAL/current_memory ~/.claude/projects/-Users-zalo/memory"
  echo "  2. Discard this proposal and run /dream again to incorporate recent edits"
  echo "  3. Force-apply (DANGEROUS, may overwrite recent edits): /dream apply $1 --force"
  exit 1
fi
```

If `--force` flag passed, skip the staleness gate (warn that user opted in).

### Step 3: Backup live memory

```bash
BACKUP=~/.claude/dreams/"$1"/backup_$(date -u +%Y%m%d-%H%M%S)
cp -R ~/.claude/projects/-Users-zalo/memory "$BACKUP"
echo "Backup: $BACKUP"
```

### Step 4: Atomic apply (stage-then-swap, NOT rsync)

`rsync --delete` is non-transactional — interruption mid-sync leaves live memory in a half-mutated state. Instead, build the new state in a sibling staging directory, then atomically swap directory names. Window where `memory/` is missing is microseconds (one rename), bounded.

```bash
LIVE=~/.claude/projects/-Users-zalo/memory
STAGING="${LIVE}.staging.$$"
OLDDIR="${LIVE}.old.$$"

# Stage: full copy of the proposed output state under a sibling path
cp -R "$PROPOSAL/output_memory" "$STAGING" || {
  echo "STAGE FAILED — could not copy output_memory to staging path. No live state changed."
  rm -rf "$STAGING" 2>/dev/null
  exit 1
}

# Swap: two renames. If interrupted between them, OLDDIR has the prior state for manual recovery.
mv "$LIVE" "$OLDDIR" && mv "$STAGING" "$LIVE" || {
  echo "SWAP FAILED — attempting auto-restore from $OLDDIR..."
  # Restore: if $LIVE exists, the second mv succeeded; nothing to do. If not, restore from OLDDIR.
  [ -d "$LIVE" ] || mv "$OLDDIR" "$LIVE"
  rm -rf "$STAGING" 2>/dev/null
  echo "Restore attempted. Inspect: ls $LIVE"
  exit 1
}

# Both renames succeeded — clean up the prior state
rm -rf "$OLDDIR"
```

### Step 5: Verify (auto-restore on failure)

```bash
# Sanity: live memory now matches output_memory
NEW_LIVE_HASH=$(find ~/.claude/projects/-Users-zalo/memory -type f -name "*.md" -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1)
EXPECTED_HASH=$(find "$PROPOSAL/output_memory" -type f -name "*.md" -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1)

if [ "$NEW_LIVE_HASH" != "$EXPECTED_HASH" ]; then
  echo "VERIFY FAILED — live memory does not match expected state."
  echo "Auto-restoring from backup: $BACKUP"
  rm -rf ~/.claude/projects/-Users-zalo/memory
  cp -R "$BACKUP" ~/.claude/projects/-Users-zalo/memory
  echo "Restored. Live memory matches pre-apply state."
  echo "Backup retained at: $BACKUP"
  exit 1
fi
```

### Step 6: Optional git commit (if ~/.claude/ is a git repo)

```bash
cd ~/.claude
if git rev-parse --git-dir > /dev/null 2>&1; then
  git add projects/-Users-zalo/memory/
  git diff --cached --stat
  echo "Live memory updated. Review the staged changes above."
  echo "Commit when ready: cd ~/.claude && git commit -m '[dream] consolidation $1'"
  # NEVER auto-commit — let the user review the diff first.
fi
```

### Step 7: Report

```
Dream applied: {DREAM_ID}
Actions executed: {N}
Backup: {BACKUP}
Proposal kept at: {PROPOSAL} (delete with /dream discard {DREAM_ID})

Verify:
  ls ~/.claude/projects/-Users-zalo/memory
  cat ~/.claude/projects/-Users-zalo/memory/MEMORY.md
```

## Workflow — `/dream discard <id>`

```bash
# CRITICAL: empty $1 would expand to ~/.claude/dreams/ and rm -rf would wipe ALL proposals.
[ -n "$1" ] || { echo "Usage: /dream discard <id>"; exit 1; }
[ -d ~/.claude/dreams/"$1" ] || { echo "No proposal at $1"; exit 1; }
rm -rf ~/.claude/dreams/"$1"
echo "Discarded proposal $1."
```

## Workflow — `/dream list`

```bash
ls -lt ~/.claude/dreams/ 2>/dev/null | grep '^d' | awk '{print $NF, $6, $7, $8}' || echo "No proposals."
```

## Workflow — `/dream show <id>`

```bash
[ -n "$1" ] || { echo "Usage: /dream show <id>"; exit 1; }
[ -f ~/.claude/dreams/"$1"/proposal.md ] || { echo "No proposal at $1"; exit 1; }
cat ~/.claude/dreams/"$1"/proposal.md
```

## Workflow — `/dream diff <id>`

```bash
[ -n "$1" ] || { echo "Usage: /dream diff <id>"; exit 1; }
[ -d ~/.claude/dreams/"$1"/current_memory ] || { echo "No proposal at $1"; exit 1; }
diff -r ~/.claude/dreams/"$1"/current_memory ~/.claude/dreams/"$1"/output_memory | head -200
```

## Anti-Patterns (will not do)

- Auto-apply a proposal without explicit `/dream apply <id>` invocation
- Skip the staleness gate (live memory changes between propose and apply must be detected)
- Skip the backup before applying
- Apply when `current_memory/` snapshot is missing (proposal is malformed; abort)
- Touch `~/.claude/rules/` or `~/.claude/CLAUDE.md` (out of scope)
- Touch any project's `.claude/` directory (out of scope; only the auto-memory store)
- Auto-commit to `~/.claude/` git repo (user reviews staged diff before committing)
- Run multiple consolidation passes in parallel (one dream at a time — they share the same memory dir)
- Trust agent output without verifying the proposal package shape (changes.json + current_memory + output_memory must all exist)
