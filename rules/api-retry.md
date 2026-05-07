# API Retry Protocol

Shared retry-and-recovery protocol for orchestrators that dispatch sub-agents
via the `Agent` tool. Use this when the underlying Anthropic API errors
transiently (overload, rate limit, 5xx) so that work units don't get marked
`failed` for what is actually a recoverable condition. Includes a circuit
breaker for sustained outages.

## Detection Signals (phrase-anchored, NOT bare codes)

A dispatch return is **retryable** if its body contains ANY of the following
substrings (case-insensitive grep on the agent's return text):

- `overloaded_error` — Anthropic SDK error type name
- `rate_limit_error` — Anthropic SDK error type name
- `Anthropic API` paired with any of these on the same line:
  `error`, `failed`, `unavailable`, `try again`, `please retry`,
  any 3-digit status code 5xx
- Full phrases (literal multi-token strings):
  - `529 overloaded`
  - `503 Service Unavailable`
  - `502 Bad Gateway`
  - `504 Gateway Timeout`
  - `service is temporarily unavailable`
  - `rate limit exceeded`
- `temporarily` paired with `unavailable` OR `try again` on the same line

**DO NOT include bare 3-digit codes** (`503`, `502`, `504`, `529`) as
standalone detection signals — they false-positive on legitimate code returns
that mention HTTP status codes (e.g., a fix-agent return that mentions an
error handler returning 503).

A dispatch return is **NOT retryable** (treat as real failure or external
blocker) if its body contains:

- `invalid_api_key`
- `authentication_error`
- `permission_denied`
- `not_found_error`
- `invalid_request_error` (the input itself is malformed)
- Vendor-specific blockers covered by `~/.claude/commands/autopilot.md`'s
  External Blocker Protocol (Stripe `pending_review`, etc.) — those route
  to External Blocker Protocol, not retry

## Backoff Schedule

| Attempt       | Wait before retry | Cumulative wait |
| ------------- | ----------------- | --------------- |
| 1 (initial)   | 0s                | 0s              |
| 2 (1st retry) | 30s               | 30s             |
| 3 (2nd retry) | 60s               | 90s             |
| 4 (3rd retry) | 120s              | 210s            |

After attempt 4 fails with a retryable signal → mark dispatch as
`api_retry_exhausted`, increment the phase-level exhaustion counter (see
Circuit Breaker), and route to the orchestrator's normal failure handling.

**Implementation in bash:**

```bash
sleep_for_attempt() {
  case "$1" in
    1) echo 0 ;;
    2) echo 30 ;;
    3) echo 60 ;;
    4) echo 120 ;;
    *) echo -1 ;;  # exhausted
  esac
}
```

The orchestrator runs `sleep <N>` between retry attempts. Each retry uses
the **same prompt** as the original dispatch — the failure was
transport-layer, not prompt-layer.

## Constants

- `MAX_API_RETRIES = 3` (attempts 2, 3, 4)
- `RETRY_BACKOFF_SCHEDULE = [30, 60, 120]` seconds
- `MAX_PHASE_API_EXHAUSTIONS = 3` (circuit breaker threshold per phase)

Total wait per dispatch with full retry budget: 30 + 60 + 120 = 210 seconds
(~3.5 minutes).

## Circuit Breaker (per-phase)

Anthropic outages typically last 10-60 minutes. Without a circuit breaker, a
single outage causes every dispatch in a phase to burn its full retry budget
(3.5 minutes each) before failing — wasting time and budget across N
dispatches. The circuit breaker stops the bleeding.

**Counter:** `api_retry_exhaustions_in_phase` (integer, persisted in
orchestrator's state file).

**Increment:** every time a single dispatch exhausts all retries with a
retryable signal.

**Decrement / reset:** counter resets to 0 at the start of each new phase.

**Trip condition:** when `api_retry_exhaustions_in_phase >= MAX_PHASE_API_EXHAUSTIONS`,
the orchestrator MUST:

1. Halt the current phase (do not dispatch additional Agent calls in this phase)
2. Write `BLOCKED_BY_API_OUTAGE` to `deferred_issues.md` (or equivalent
   blocker log) with the timestamp, the phase name, and the last detected
   signal
3. Exit cleanly to the orchestrator's terminal phase (e.g., autopilot's
   Phase 5) with status `ABORTED_API_OUTAGE`

The circuit breaker preserves work already done — completed work units stay
completed, partial work units get marked `blocked_by_api_outage` (NOT
`failed`), and the orchestrator emits a clean terminal report rather than
mass-marking everything failed.

## State Persistence (compaction safety)

Long backoff sleeps (up to 120s) can cross a `/compact` boundary. To survive
compaction, the orchestrator persists retry state to its state file
(typically `.autopilot/state.json`) BEFORE entering each `sleep`.

**Schema (added to existing state.json):**

```json
{
  "current_dispatch_retry": {
    "wu_id": "<work unit id>",
    "agent": "<subagent_type>",
    "prompt_ref": "<key into a prompts dir, OR full prompt if short>",
    "attempt": 2,
    "last_signal": "overloaded_error",
    "sleep_until_ts": "<ISO8601 timestamp when sleep ends>"
  },
  "api_retry_exhaustions_in_phase": 0
}
```

When the orchestrator resumes (post-compaction or post-interrupt), it MUST:

1. Read `current_dispatch_retry` from state.json
2. If absent → no in-flight retry; proceed normally
3. If present:
   - If `sleep_until_ts` is in the past → dispatch the retry immediately
   - If `sleep_until_ts` is in the future → `sleep` the remainder, then dispatch
4. After dispatch returns, clear `current_dispatch_retry` (or update to next
   attempt's state)

This is what makes the retry loop compaction-safe.

## Logging

Every retry attempt logs to the orchestrator's `decisions.log`:

```json
{
  "ts": "<iso8601>",
  "tier": "api_retry",
  "decision": "retry attempt <N>",
  "reasoning": "detected signal: <signal>",
  "work_unit": "<id>"
}
```

Successful recovery after retry:

```json
{
  "ts": "<iso8601>",
  "tier": "api_retry",
  "decision": "recovered after <N> retries",
  "work_unit": "<id>"
}
```

Exhaustion:

```json
{"ts":"<iso8601>","tier":"api_retry","decision":"api_retry_exhausted","reasoning":"<last detected signal>","work_unit":"<id>","phase_exhaustion_count":<N>}
```

Circuit breaker trip:

```json
{
  "ts": "<iso8601>",
  "tier": "api_retry",
  "decision": "circuit_breaker_tripped",
  "reasoning": "phase exhaustion count reached <N>",
  "phase": "<name>"
}
```

## Distinction from External Blocker Protocol

- **API retry (this rule):** the Anthropic API itself is transiently
  unavailable. Retry the SAME dispatch.
- **External Blocker Protocol (`autopilot.md`):** a third-party vendor
  (Stripe, Apple, A2P 10DLC) is blocking. Defer the work unit and continue.
- If a return contains BOTH signals, External Blocker Protocol wins.

API retry handles transport-layer transient errors that resolve in seconds
to a few minutes. External Blocker Protocol handles vendor-side waits
(rate-limited accounts, pending approvals, queue full) that resolve in
minutes, hours, or days — those are not retryable in a backoff loop; the
work unit gets deferred and the orchestrator continues with other work.

## Use From Orchestrators

Orchestrators that adopt this protocol wrap their Agent dispatches with the
retry loop AND maintain the per-phase exhaustion counter AND persist the
retry state. Reference: `~/.claude/commands/autopilot.md` "API Dispatch
Wrapper Protocol" section.
