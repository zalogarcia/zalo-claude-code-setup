#!/bin/bash
printf '%s' 'Back-end Stress Test: Read the full implementation first.

Then systematically try to break every backend flow — think like a malicious request, a thundering herd, and a database that just decided to lie to you.

Data Integrity & Validation:

What happens when required fields are missing, null, wrong type, or absurdly large?
Can a crafted payload bypass validation (nested objects, extra fields, type coercion)?
Are database writes atomic? If step 3 of 5 fails, do steps 1-2 roll back or leave orphaned data?
What enforces uniqueness, foreign keys, and constraints — the code or the DB? What if both disagree?

Error Propagation & Failure Handling:

Trace every external call (APIs, DB, cache, queues) — what happens when each one times out, returns garbage, or just dies?
Do errors bubble up with useful context or get swallowed silently?
Are retries idempotent? If a timeout triggers a retry, does it double-charge, duplicate-create, or corrupt state?
What'\''s the fallback when a dependency is completely unavailable?

Concurrency & Race Conditions:

Two identical requests hit the same endpoint simultaneously — what wins, what breaks, what duplicates?
Read-then-write patterns without locks — can stale reads cause wrong writes?
Queue consumers processing the same message twice — is every handler idempotent?
Long-running operations — what happens if the same job fires again before the first one finishes?

Auth, Permissions & Access Control:

Can a valid user access or mutate another user'\''s data by manipulating IDs in the request?
Are permissions checked at the data layer or just the route layer? What if someone hits the service directly?
Token expiry mid-operation — does it fail gracefully or leave things half-done?
Deleted/deactivated user'\''s token still valid — what can they still touch?

Scale & Resource Pressure:

What happens at 100x normal payload size? 100x normal request volume?
Are there unbounded queries (SELECT without LIMIT, unfiltered list endpoints)?
Memory leaks on repeated operations — connections not closed, listeners not removed?
N+1 queries, missing indexes, full table scans hiding behind small dev datasets?

For each finding: what breaks → root cause → severity (critical/high/medium/low) → fix.

Run the full report by me before making any changes.' | pbcopy
