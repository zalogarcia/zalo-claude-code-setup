#!/usr/bin/env bash
# ============================================================================
# AUTOLOOP HARNESS — Script-layer watchdog for autonomous optimization
# ============================================================================
# This script wraps Claude Code and ensures the optimization loop runs
# to completion, even through API errors, crashes, and interruptions.
#
# Usage:
#   autoloop-harness.sh [project-dir] [options]
#
# Options:
#   --max-retries N     Total retries before giving up (default: 50)
#   --cooldown N        Base cooldown between retries in seconds (default: 10)
#   --max-hours N       Maximum wall-clock hours (default: 24)
#   --stall-timeout N   Seconds of no progress before restarting agent (default: 900)
#   --agent-timeout N   Max seconds per agent run (default: 7200)
#   --max-budget N      Max USD spend per agent run (default: 5)
#   --model M           Model to use (default: opus)
#   --skip-briefing     Skip Phase 0 (briefing already saved to .autoloop/briefing.md)
#
# Examples:
#   autoloop-harness.sh .
#   autoloop-harness.sh /path/to/project --max-retries 100 --max-hours 8
#   autoloop-harness.sh . --stall-timeout 1200 --max-budget 5.00
#
# The harness does NOT contain optimization logic — Claude does that.
# The harness ensures Claude KEEPS RUNNING until the job is done.
# ============================================================================

set -euo pipefail

# --- Default Configuration ---
PROJECT_DIR="."
MAX_RETRIES=50
COOLDOWN_BASE=10
COOLDOWN_MAX=120
MAX_HOURS=24
HEARTBEAT_INTERVAL=30
STALL_THRESHOLD=900             # 15 min default (recon/large tests need time)
AGENT_TIMEOUT=7200              # 2 hours per agent run (generous for complex phases)
MAX_BUDGET=0                    # Max USD per agent run (0 = unlimited, default)
MODEL="opus"
SKIP_BRIEFING=false
SKILL_FILE="$HOME/.claude/commands/autoloop.md"  # Full skill instructions

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-retries)    MAX_RETRIES="$2"; shift 2 ;;
        --cooldown)       COOLDOWN_BASE="$2"; shift 2 ;;
        --max-hours)      MAX_HOURS="$2"; shift 2 ;;
        --stall-timeout)  STALL_THRESHOLD="$2"; shift 2 ;;
        --agent-timeout)  AGENT_TIMEOUT="$2"; shift 2 ;;
        --max-budget)     MAX_BUDGET="$2"; shift 2 ;;
        --model)          MODEL="$2"; shift 2 ;;
        --skill)          SKILL_FILE="$2"; shift 2 ;;
        --skip-briefing)  SKIP_BRIEFING=true; shift ;;
        --help|-h)        head -31 "$0" | tail -25; exit 0 ;;
        -*)               echo "Unknown option: $1" >&2; exit 1 ;;
        *)                PROJECT_DIR="$1"; shift ;;
    esac
done

# Resolve to absolute path
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"

# --- Derived paths ---
AUTOLOOP_DIR="${PROJECT_DIR}/.autoloop"
RESULTS_FILE="${AUTOLOOP_DIR}/results.tsv"
BRIEFING_FILE="${AUTOLOOP_DIR}/briefing.md"
PHASE_FILE="${AUTOLOOP_DIR}/phase.txt"
HARNESS_LOG="${AUTOLOOP_DIR}/harness.log"
PID_FILE="${AUTOLOOP_DIR}/harness.pid"
STATE_FILE="${AUTOLOOP_DIR}/state.json"
LOCK_FILE="${AUTOLOOP_DIR}/harness.lock"
AGENT_PID_FILE="${AUTOLOOP_DIR}/agent.pid"
AGENT_LOG="${AUTOLOOP_DIR}/agent.log"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================================
# FUNCTIONS
# ============================================================================

log()         { echo -e "${BLUE}[harness $(date '+%H:%M:%S')]${NC} $1" | tee -a "$HARNESS_LOG"; }
log_error()   { echo -e "${RED}[harness $(date '+%H:%M:%S')] ERROR:${NC} $1" | tee -a "$HARNESS_LOG"; }
log_success() { echo -e "${GREEN}[harness $(date '+%H:%M:%S')]${NC} $1" | tee -a "$HARNESS_LOG"; }
log_warn()    { echo -e "${YELLOW}[harness $(date '+%H:%M:%S')] WARN:${NC} $1" | tee -a "$HARNESS_LOG"; }
log_detail()  { echo -e "${CYAN}[harness $(date '+%H:%M:%S')]${NC} $1" | tee -a "$HARNESS_LOG"; }

# --- Lock Management ---
acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local old_info
        old_info=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        local old_pid
        old_pid=$(echo "$old_info" | head -1)
        local old_host
        old_host=$(echo "$old_info" | tail -1)
        local current_host
        current_host=$(hostname)

        if [ "$old_host" = "$current_host" ] && [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            log_error "Another harness is already running (PID: $old_pid on $old_host)"
            exit 1
        else
            log_warn "Stale lock file found (PID: $old_pid, host: ${old_host:-unknown}), removing"
            rm -f "$LOCK_FILE"
        fi
    fi
    printf '%s\n%s\n' "$$" "$(hostname)" > "$LOCK_FILE"
}

release_lock() {
    rm -f "$LOCK_FILE" "$PID_FILE" "$AGENT_PID_FILE"
}

# --- Progress Detection ---
get_experiment_count() {
    if [ -f "$RESULTS_FILE" ]; then
        local count
        count=$(wc -l < "$RESULTS_FILE" | tr -d ' ')
        echo $(( count > 0 ? count - 1 : 0 ))
    else
        echo 0
    fi
}

# Returns the most recent modification epoch across all progress signals
get_latest_progress_epoch() {
    local latest=0

    # Check all .autoloop artifacts
    for f in "$AUTOLOOP_DIR"/*.md "$AUTOLOOP_DIR"/*.tsv "$AUTOLOOP_DIR"/*.txt "$AUTOLOOP_DIR"/*.json; do
        if [ -f "$f" ] && [ "$f" != "$HARNESS_LOG" ] && [ "$f" != "$STATE_FILE" ] && [ "$f" != "$LOCK_FILE" ]; then
            local fmod
            fmod=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0)
            [ "$fmod" -gt "$latest" ] && latest="$fmod"
        fi
    done

    # Check agent.log as a progress signal (stream-json output is written continuously)
    if [ -f "$AGENT_LOG" ]; then
        local amod
        amod=$(stat -f %m "$AGENT_LOG" 2>/dev/null || stat -c %Y "$AGENT_LOG" 2>/dev/null || echo 0)
        [ "$amod" -gt "$latest" ] && latest="$amod"
    fi

    # Check git log for new commits
    local latest_commit
    latest_commit=$(cd "$PROJECT_DIR" && git log -1 --format=%ct 2>/dev/null || echo 0)
    [ "$latest_commit" -gt "$latest" ] && latest="$latest_commit"

    # Check if any tracked file changed (agent may be editing code)
    local work_tree_mod
    work_tree_mod=$(cd "$PROJECT_DIR" && git diff --stat 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    if [ "$work_tree_mod" -gt 0 ]; then
        latest=$(date +%s)  # Working tree is being modified right now
    fi

    echo "$latest"
}

# --- Phase Detection (reads phase.txt written by the skill) ---
detect_phase() {
    # Primary: read phase.txt written by the agent
    if [ -f "$PHASE_FILE" ]; then
        local phase_val
        phase_val=$(cat "$PHASE_FILE" 2>/dev/null | tr -d '[:space:]')
        # Only use phase.txt if it contains a non-empty valid value
        if [ -n "$phase_val" ]; then
            echo "$phase_val"
            return
        fi
        # Empty phase.txt — fall through to artifact-based detection
    fi
    # Fallback: infer from artifacts
    if [ ! -f "$BRIEFING_FILE" ]; then
        echo "briefing"
    elif [ ! -f "${AUTOLOOP_DIR}/recon.md" ]; then
        echo "recon"
    elif [ -f "${AUTOLOOP_DIR}/report.md" ]; then
        echo "complete"
    else
        echo "optimizing"
    fi
}

# Phase-aware stall threshold — recon and hardening need more time
get_stall_threshold() {
    local phase
    phase=$(detect_phase)
    case "$phase" in
        recon)      echo $(( STALL_THRESHOLD * 2 )) ;;  # Recon reads many files
        hardening)  echo $(( STALL_THRESHOLD * 2 )) ;;  # Hardening runs many tests
        *)          echo "$STALL_THRESHOLD" ;;
    esac
}

# --- Completion Check ---
check_completion() {
    if [ -f "${AUTOLOOP_DIR}/report.md" ]; then
        return 0
    fi
    local phase
    phase=$(detect_phase)
    if [ "$phase" = "complete" ]; then
        return 0
    fi
    if [ -f "$STATE_FILE" ]; then
        local status
        status=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('status','running'))" 2>/dev/null || echo "running")
        if [ "$status" = "completed" ] || [ "$status" = "exhausted" ]; then
            return 0
        fi
    fi
    return 1
}

# --- State Management ---
save_state() {
    local retry_count="$1"
    local phase="$2"
    local experiments="$3"
    cat > "$STATE_FILE" << STATEEOF
{
    "status": "running",
    "retry_count": $retry_count,
    "phase": "$phase",
    "experiments": $experiments,
    "last_restart": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
    "harness_pid": $$,
    "hostname": "$(hostname)",
    "start_time": "$START_TIME"
}
STATEEOF
}

load_state() {
    if [ -f "$STATE_FILE" ]; then
        local status
        status=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('status','unknown'))" 2>/dev/null || echo "unknown")
        if [ "$status" = "running" ]; then
            local prev_retries
            prev_retries=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('retry_count', 0))" 2>/dev/null || echo 0)
            # Write to stderr + log file (NOT stdout) to avoid polluting the return value
            echo -e "${BLUE}[harness $(date '+%H:%M:%S')]${NC} Resuming from previous state (retry: $prev_retries)" | tee -a "$HARNESS_LOG" >&2
            echo "$prev_retries"
            return
        fi
    fi
    echo 0
}

# --- Exponential Backoff ---
calc_cooldown() {
    local retry="$1"
    local capped=$(( retry > 5 ? 5 : retry ))
    local base_delay=$(( COOLDOWN_BASE * (2 ** capped) ))
    local jitter=$(( RANDOM % (base_delay / 2 + 1) ))
    local total=$(( base_delay + jitter ))
    [ "$total" -gt "$COOLDOWN_MAX" ] && total=$COOLDOWN_MAX
    echo "$total"
}

# --- Build Resume Prompt ---
build_resume_prompt() {
    local phase
    phase=$(detect_phase)
    local experiments
    experiments=$(get_experiment_count)

    case "$phase" in
        briefing)
            echo "Continue the /autoloop optimization. The briefing is complete (check .autoloop/briefing.md). Proceed to Phase 1: Reconnaissance."
            ;;
        recon)
            echo "Continue the /autoloop optimization. Briefing is at .autoloop/briefing.md. Proceed to or resume Phase 1: Reconnaissance. Do NOT re-interview the human."
            ;;
        optimizing|sandbox|integration|hardening)
            echo "Continue the /autoloop optimization. The harness restarted you after an interruption. Current phase: $phase. Experiments logged: $experiments (see .autoloop/results.tsv). Read .autoloop/briefing.md and .autoloop/recon.md to restore context. Read .autoloop/results.tsv to see what's been tried. Read .autoloop/phase.txt for current phase. Resume from where you left off. Do NOT re-interview the human. Do NOT re-run successful experiments. Check git log --oneline -20 for recent committed state. Check for orphaned worktrees with git worktree list and clean up any stale ones."
            ;;
        complete)
            echo "DONE"
            ;;
        *)
            # Unknown or empty phase — treat as optimizing with full context restore
            log_warn "Unknown phase '$phase' detected. Treating as optimization resume."
            echo "Continue the /autoloop optimization. The harness restarted you after an interruption. Phase could not be determined (check .autoloop/phase.txt). Experiments logged: $experiments (see .autoloop/results.tsv). Read .autoloop/briefing.md and .autoloop/recon.md to restore context. Read .autoloop/results.tsv to see what's been tried. Resume from where you left off. Do NOT re-interview the human. Check git log --oneline -20."
            ;;
    esac
}

# --- Git Safety ---
ensure_autoloop_branch() {
    cd "$PROJECT_DIR"
    local current_branch
    current_branch=$(git branch --show-current 2>/dev/null || echo "")

    # NEVER work on main/master — create or switch to autoloop branch
    if [ "$current_branch" = "main" ] || [ "$current_branch" = "master" ]; then
        local autoloop_branch="autoloop/$(date +%Y%m%d-%H%M%S)"
        log_warn "Currently on '$current_branch'. Creating autoloop branch: $autoloop_branch"
        git checkout -b "$autoloop_branch" 2>&1 | tee -a "$HARNESS_LOG"
        log_success "Switched to branch: $autoloop_branch"
    elif [ -z "$current_branch" ]; then
        # Detached HEAD or other weird state
        local autoloop_branch="autoloop/$(date +%Y%m%d-%H%M%S)"
        log_warn "Detached HEAD. Creating autoloop branch: $autoloop_branch"
        git checkout -b "$autoloop_branch" 2>&1 | tee -a "$HARNESS_LOG" || true
    else
        log "Working on branch: $current_branch"
    fi
    cd - > /dev/null
}

ensure_git_repo() {
    cd "$PROJECT_DIR"

    # Create .gitignore for harness runtime files BEFORE any git add
    # This prevents harness.log, lock files, PIDs from being committed
    local gitignore_autoloop="${AUTOLOOP_DIR}/.gitignore"
    if [ ! -f "$gitignore_autoloop" ]; then
        cat > "$gitignore_autoloop" << 'GIEOF'
# Autoloop harness runtime files (do not track)
harness.log
harness.pid
harness.lock
agent.pid
state.json
research_notes.md
GIEOF
        log_detail "Created .autoloop/.gitignore for runtime files"
    fi

    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        log "Not a git repo. Initializing git for ratchet tracking..."
        git init 2>&1 | tee -a "$HARNESS_LOG"
        git add -A 2>&1 | tee -a "$HARNESS_LOG"
        git commit -m "[autoloop] Initial commit — baseline before optimization" 2>&1 | tee -a "$HARNESS_LOG" || true
        log_success "Git repo initialized with baseline commit."
    elif ! git log -1 &>/dev/null 2>&1; then
        # Git repo exists but has no commits
        log "Git repo has no commits. Creating baseline commit..."
        git add -A 2>&1 | tee -a "$HARNESS_LOG"
        git commit -m "[autoloop] Initial commit — baseline before optimization" 2>&1 | tee -a "$HARNESS_LOG" || true
        log_success "Baseline commit created."
    fi
    cd - > /dev/null
}

cleanup_worktrees() {
    cd "$PROJECT_DIR"
    local orphaned
    orphaned=$(git worktree list --porcelain 2>/dev/null | grep -c "^worktree " || echo 0)
    if [ "$orphaned" -gt 1 ]; then
        log "Cleaning up orphaned worktrees ($((orphaned - 1)) found)..."
        git worktree prune 2>&1 | tee -a "$HARNESS_LOG" || true
        # Remove any leftover autoloop worktree directories
        for wt in $(git worktree list --porcelain 2>/dev/null | grep "^worktree " | awk '{print $2}' | grep -i autoloop || true); do
            if [ -d "$wt" ]; then
                log_detail "Removing orphaned worktree: $wt"
                git worktree remove "$wt" --force 2>&1 | tee -a "$HARNESS_LOG" || true
            fi
        done
    fi
    cd - > /dev/null
}

recover_git_state() {
    cd "$PROJECT_DIR"
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        log_warn "Dirty git state after agent exit. Discarding incomplete experiment (ratchet principle)..."
        git checkout -- . 2>&1 | tee -a "$HARNESS_LOG" || true
        # Clean untracked files EXCEPT .autoloop/ (harness state)
        git clean -fd --exclude=.autoloop 2>&1 | tee -a "$HARNESS_LOG" || true
    fi
    # Clean up any orphaned worktrees from subagents
    cleanup_worktrees
    cd - > /dev/null
}

# --- Run Agent ---
# Returns: 0 = clean exit, 1 = crash, 2 = stall killed, 3 = timeout killed
run_agent() {
    local prompt="$1"

    log "Launching Claude Code agent..."
    log_detail "Phase: $(detect_phase) | Model: $MODEL"

    # Build claude command
    # Use stream-json output for real-time terminal feed in the dashboard
    local -a cmd=(claude --print --verbose --output-format stream-json --dangerously-skip-permissions --model "$MODEL")

    # CRITICAL: Inject the full skill file as a system prompt so the agent
    # has all 414 lines of optimization instructions on every autonomous run.
    # Without this, the agent only gets a brief resume prompt and has no idea
    # about phases, ratchet principle, subagent strategy, etc.
    if [ -f "$SKILL_FILE" ]; then
        cmd+=(--append-system-prompt-file "$SKILL_FILE")
    else
        log_warn "Skill file not found at $SKILL_FILE — agent will run without full instructions"
    fi

    # Add cost cap if set
    if [ "$MAX_BUDGET" != "0" ]; then
        cmd+=(--max-budget-usd "$MAX_BUDGET")
    fi

    # Each run is a fresh session with full context injected via system prompt.
    # Session resumption (--resume) was removed because it's fragile:
    # the agent gets all context it needs from .autoloop/ artifacts + the skill file.

    # Inject harness runtime context into the prompt itself
    # (cannot use --append-system-prompt alongside --append-system-prompt-file)
    local phase
    phase=$(detect_phase)
    local experiments
    experiments=$(get_experiment_count)
    local harness_context="HARNESS CONTEXT: You are being run by the autoloop harness. Current phase: ${phase}. Experiments so far: ${experiments}. Write current phase to .autoloop/phase.txt after each phase transition. The harness monitors .autoloop/ files and git commits for progress — if you stop writing for ${STALL_THRESHOLD}s, the harness will restart you. Keep making progress."

    cmd+=(-p "${harness_context}

${prompt}")

    # Enable unattended retry for API resilience
    export CLAUDE_CODE_UNATTENDED_RETRY=1
    export CLAUDE_CODE_MAX_RETRIES=10

    # Run agent in its own process group so kill_agent_tree
    # can kill the agent + subagents without killing the harness.
    # macOS doesn't have setsid CLI — use perl POSIX fallback.
    # Agent output (stream-json) goes to agent.log only.
    # Harness messages go to harness.log via the log() functions.
    if command -v setsid &>/dev/null; then
        setsid "${cmd[@]}" >> "$AGENT_LOG" 2>&1 &
    else
        # macOS: perl calls setsid() then execs the agent in the new session
        perl -e 'use POSIX qw(setsid); setsid(); exec @ARGV or die "exec failed: $!"' -- "${cmd[@]}" >> "$AGENT_LOG" 2>&1 &
    fi
    local agent_pid=$!
    echo "$agent_pid" > "$AGENT_PID_FILE"

    log "Agent PID: $agent_pid (process group: $(ps -o pgid= -p $agent_pid 2>/dev/null | tr -d ' ' || echo 'unknown'))"

    local elapsed=0
    local last_progress
    last_progress=$(get_latest_progress_epoch)
    local stall_seconds=0
    local current_stall_threshold
    current_stall_threshold=$(get_stall_threshold)

    # Monitor the agent process
    while kill -0 "$agent_pid" 2>/dev/null; do
        sleep "$HEARTBEAT_INTERVAL"
        elapsed=$(( elapsed + HEARTBEAT_INTERVAL ))

        # Check wall-clock timeout for this single agent run
        if [ "$elapsed" -gt "$AGENT_TIMEOUT" ]; then
            log_warn "Agent exceeded per-run timeout (${AGENT_TIMEOUT}s). Killing process group..."
            kill_agent_tree "$agent_pid"
            return 3
        fi

        # Refresh stall threshold (phase may have changed)
        current_stall_threshold=$(get_stall_threshold)

        # Check all progress signals
        local current_progress
        current_progress=$(get_latest_progress_epoch)

        if [ "$current_progress" -gt "$last_progress" ]; then
            stall_seconds=0
            last_progress="$current_progress"
            local current_phase
            current_phase=$(detect_phase)
            log "Heartbeat OK: ${elapsed}s elapsed | phase: $current_phase | stall threshold: ${current_stall_threshold}s"
        else
            stall_seconds=$(( stall_seconds + HEARTBEAT_INTERVAL ))
            if [ "$stall_seconds" -ge "$current_stall_threshold" ]; then
                log_warn "Agent stalled for ${stall_seconds}s (threshold: ${current_stall_threshold}s). Killing..."
                kill_agent_tree "$agent_pid"
                return 2
            fi
            log_detail "Heartbeat: no progress (stall: ${stall_seconds}/${current_stall_threshold}s)"
        fi
    done

    # Agent exited on its own
    wait "$agent_pid" 2>/dev/null
    local exit_code=$?
    rm -f "$AGENT_PID_FILE"

    if [ "$exit_code" -eq 0 ]; then
        log "Agent exited cleanly (code 0)"
        return 0
    else
        log_error "Agent crashed (exit code: $exit_code)"
        return 1
    fi
}

# Kill agent and all child processes (subagents)
# Safe because setsid gives the agent its own process group
kill_agent_tree() {
    local pid="$1"

    # Agent runs in its own process group (via setsid), so killing
    # the group is safe — it won't affect the harness
    local pgid
    pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || echo "")

    if [ -n "$pgid" ] && [ "$pgid" != "0" ]; then
        log_detail "Killing agent process group $pgid..."
        kill -- -"$pgid" 2>/dev/null || true
    else
        # Fallback: kill just the main process + direct children
        kill "$pid" 2>/dev/null || true
        pkill -P "$pid" 2>/dev/null || true
    fi

    wait "$pid" 2>/dev/null || true
    rm -f "$AGENT_PID_FILE"
}

# --- Cleanup ---
cleanup() {
    log "Harness shutting down (PID: $$)"
    if [ -f "$AGENT_PID_FILE" ]; then
        local agent_pid
        agent_pid=$(cat "$AGENT_PID_FILE" 2>/dev/null || echo "")
        if [ -n "$agent_pid" ] && kill -0 "$agent_pid" 2>/dev/null; then
            log "Killing agent tree (PID: $agent_pid)..."
            kill_agent_tree "$agent_pid"
        fi
    fi
    release_lock
    exit 0
}

# ============================================================================
# MAIN
# ============================================================================

trap cleanup EXIT INT TERM

# --- Validate environment ---
if ! command -v claude &> /dev/null; then
    log_error "Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# --- Initialize ---
mkdir -p "$AUTOLOOP_DIR"
acquire_lock
echo $$ > "$PID_FILE"

START_TIME=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
START_EPOCH=$(date +%s)
DEADLINE=$(( START_EPOCH + (MAX_HOURS * 3600) ))

log "============================================"
log "AUTOLOOP HARNESS v3"
log "============================================"
log "Project:        $PROJECT_DIR"
log "Model:          $MODEL"
log "Max retries:    $MAX_RETRIES"
log "Max hours:      $MAX_HOURS"
log "Stall timeout:  ${STALL_THRESHOLD}s (2x for recon/hardening)"
log "Agent timeout:  ${AGENT_TIMEOUT}s"
log "Budget/run:     ${MAX_BUDGET:-unlimited}"
log "Deadline:       $(date -r "$DEADLINE" 2>/dev/null || date -d "@$DEADLINE" 2>/dev/null || echo 'N/A')"
log "PID:            $$"
log "Hostname:       $(hostname)"
log "============================================"

# --- Ensure git repo exists with at least one commit ---
ensure_git_repo

# --- Never commit to main/master — create autoloop branch ---
ensure_autoloop_branch

# --- Clean up orphaned worktrees from prior runs ---
cleanup_worktrees

# --- Load previous state if resuming ---
RETRY_COUNT=$(load_state)

# --- Phase 0: Interactive Briefing ---
if [ -f "$BRIEFING_FILE" ]; then
    log "Briefing already exists at $BRIEFING_FILE. Skipping Phase 0."
elif [ "$SKIP_BRIEFING" = true ]; then
    log_error "No briefing found and --skip-briefing was set."
    log_error "Create .autoloop/briefing.md before using --skip-briefing."
    exit 1
else
    # Verify we're in an interactive terminal
    if [ ! -t 0 ]; then
        log_error "No briefing found and stdin is not a terminal."
        log_error "Either run interactively first, or create .autoloop/briefing.md manually."
        exit 1
    fi

    log ""
    log "============================================"
    log "  INTERACTIVE BRIEFING SESSION"
    log "  Answer the agent's questions below."
    log "  The harness takes over once briefing.md is saved."
    log "============================================"
    log ""

    # Phase 0 runs INTERACTIVELY — no --print flag
    claude --dangerously-skip-permissions \
        --model "$MODEL" \
        "/autoloop — Begin Phase 0: Briefing. Interview the human thoroughly. Save the completed briefing to .autoloop/briefing.md when done. Write 'briefing' to .autoloop/phase.txt." \
        2>&1 | tee -a "$HARNESS_LOG" || true

    if [ ! -f "$BRIEFING_FILE" ]; then
        log_error "Briefing was not saved to .autoloop/briefing.md. Cannot proceed."
        log_error "Re-run the harness, or create .autoloop/briefing.md manually."
        exit 1
    fi
    log_success "Briefing complete. Switching to autonomous mode."
fi

# ============================================================================
# THE WATCHDOG LOOP
# ============================================================================

while [ "$RETRY_COUNT" -lt "$MAX_RETRIES" ]; do
    # --- Check deadline ---
    if [ "$(date +%s)" -gt "$DEADLINE" ]; then
        log_warn "Wall-clock deadline reached ($MAX_HOURS hours). Stopping."
        break
    fi

    # --- Check completion ---
    if check_completion; then
        log_success "Optimization complete! Report at .autoloop/report.md"
        break
    fi

    # --- Build resume prompt ---
    PROMPT=$(build_resume_prompt)
    if [ "$PROMPT" = "DONE" ]; then
        log_success "Optimization already complete."
        break
    fi

    # --- Track progress ---
    EXPERIMENTS_BEFORE=$(get_experiment_count)

    # --- Save state ---
    PHASE=$(detect_phase)
    save_state "$RETRY_COUNT" "$PHASE" "$EXPERIMENTS_BEFORE"

    # --- Run the agent with monitoring ---
    AGENT_RESULT=0
    run_agent "$PROMPT" || AGENT_RESULT=$?

    # --- Update state after run ---
    EXPERIMENTS_AFTER=$(get_experiment_count)
    PHASE_AFTER=$(detect_phase)
    save_state "$RETRY_COUNT" "$PHASE_AFTER" "$EXPERIMENTS_AFTER"

    case "$AGENT_RESULT" in
        0)  # Clean exit
            if check_completion; then
                log_success "Agent completed! $EXPERIMENTS_AFTER total experiments."
                break
            else
                log_warn "Agent exited but not complete (phase: $PHASE_AFTER, experiments: $EXPERIMENTS_AFTER). Restarting..."
                RETRY_COUNT=$(( RETRY_COUNT + 1 ))
                sleep 5
            fi
            ;;
        1)  # Crash
            log_error "Agent crashed (phase: $PHASE_AFTER, experiments: $EXPERIMENTS_AFTER)."
            recover_git_state
            if [ "$EXPERIMENTS_AFTER" -gt "$EXPERIMENTS_BEFORE" ]; then
                log "Made progress: $((EXPERIMENTS_AFTER - EXPERIMENTS_BEFORE)) new experiments. Short cooldown."
                RETRY_COUNT=$(( RETRY_COUNT + 1 ))
                sleep "$COOLDOWN_BASE"
            else
                RETRY_COUNT=$(( RETRY_COUNT + 1 ))
                COOLDOWN=$(calc_cooldown "$RETRY_COUNT")
                log_warn "No progress. Retry $RETRY_COUNT/$MAX_RETRIES. Cooling down ${COOLDOWN}s..."
                sleep "$COOLDOWN"
            fi
            ;;
        2)  # Stall
            log_warn "Agent stalled (phase: $PHASE_AFTER). Restarting..."
            recover_git_state
            RETRY_COUNT=$(( RETRY_COUNT + 1 ))
            sleep "$COOLDOWN_BASE"
            ;;
        3)  # Timeout
            log_warn "Agent hit per-run timeout (phase: $PHASE_AFTER). Restarting..."
            recover_git_state
            RETRY_COUNT=$(( RETRY_COUNT + 1 ))
            sleep "$COOLDOWN_BASE"
            ;;
    esac

    log "--- Iteration $RETRY_COUNT complete | Phase: $PHASE_AFTER | Experiments: $EXPERIMENTS_AFTER ---"
done

# ============================================================================
# FINAL STATUS
# ============================================================================

FINAL_EXPERIMENTS=$(get_experiment_count)
FINAL_PHASE=$(detect_phase)

DURATION_MINS=$(( ($(date +%s) - START_EPOCH) / 60 ))

# Determine final status
FINAL_STATUS=""
if check_completion; then
    FINAL_STATUS="COMPLETED"
    log_success "STATUS: COMPLETED"
    log "Report: ${AUTOLOOP_DIR}/report.md"
    log "Results: ${RESULTS_FILE}"
elif [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
    FINAL_STATUS="EXHAUSTED_RETRIES"
    log_error "STATUS: EXHAUSTED RETRIES ($MAX_RETRIES)"
else
    FINAL_STATUS="TIMED_OUT"
    log_warn "STATUS: TIMED OUT ($MAX_HOURS hours)"
fi

log "============================================"
log "AUTOLOOP HARNESS FINISHED"
log "============================================"
log "Total experiments: $FINAL_EXPERIMENTS"
log "Final phase:       $FINAL_PHASE"
log "Total retries:     $RETRY_COUNT"
log "Duration:          $DURATION_MINS minutes"
log "============================================"

# ============================================================================
# TELEGRAM NOTIFICATION
# ============================================================================
# Sends completion status to Telegram using the bot configured in
# ~/.claude/settings.local.json (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)

send_telegram() {
    local message="$1"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\": \"${TELEGRAM_CHAT_ID}\", \"text\": $(python3 -c "import json; print(json.dumps('''$message'''))" 2>/dev/null || echo "\"$message\""), \"parse_mode\": \"Markdown\"}" \
            >> "$HARNESS_LOG" 2>&1 || log_warn "Telegram notification failed"
    else
        log_detail "Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set). Skipping notification."
    fi
}

# Build notification message
PROJECT_NAME=$(basename "$PROJECT_DIR")
case "$FINAL_STATUS" in
    COMPLETED)
        TG_EMOJI="✅"
        TG_STATUS="*COMPLETED*"
        ;;
    EXHAUSTED_RETRIES)
        TG_EMOJI="❌"
        TG_STATUS="*FAILED* (exhausted $MAX_RETRIES retries)"
        ;;
    TIMED_OUT)
        TG_EMOJI="⏰"
        TG_STATUS="*TIMED OUT* ($MAX_HOURS hours)"
        ;;
esac

TG_MESSAGE="${TG_EMOJI} *Autoloop finished*

Project: \`${PROJECT_NAME}\`
Status: ${TG_STATUS}
Experiments: ${FINAL_EXPERIMENTS}
Duration: ${DURATION_MINS} minutes
Phase: ${FINAL_PHASE}

$(if [ -f "${AUTOLOOP_DIR}/report.md" ]; then echo "Report saved to \`.autoloop/report.md\`"; else echo "No report generated — check \`.autoloop/harness.log\`"; fi)"

send_telegram "$TG_MESSAGE"
log "Telegram notification sent."
