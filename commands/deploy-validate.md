# /deploy-validate - Self-Healing Deployment

You are executing a deployment validation pipeline. Every check must pass before proceeding to production.

## Pre-Deploy Gate

1. **Run full QA** — typecheck, build, and test must all pass:
   - `npx tsc --noEmit`
   - `npm run build`
   - Run test suite if it exists
   - If ANY check fails: fix it, re-run, do NOT proceed until green

2. **Check for uncommitted changes** — `git status` must be clean. Commit or stash anything outstanding.

## Deploy to Staging

3. **Deploy edge functions** to Supabase:
   - Use `supabase functions deploy` for each changed function
   - Check deployment output for errors

4. **Smoke test each endpoint**:
   - Curl each deployed edge function with test payloads
   - Validate response shapes match expected TypeScript types
   - Check HTTP status codes (expect 200/201 for success paths)

5. **Check logs for errors**:
   - Use `mcp__supabase__get_logs` or `supabase functions logs` to check the last 60 seconds
   - Flag any errors, warnings, or unexpected patterns

6. **Validate environment & config**:
   - Confirm all required env vars are set in Supabase dashboard/config
   - Verify JWT/auth configuration is correct
   - Check that any new DB migrations have been applied

## Decision Point

7. **If ANY check failed**:
   - Report the failure with root cause analysis
   - Suggest a specific fix
   - Do NOT proceed to production
   - Offer to fix and re-run

8. **If ALL checks passed**:
   - Present a deployment summary: what changed, what was tested, all green results
   - Ask user: "All checks passed. Deploy to production?"
   - **STOP and wait for explicit approval**

## Rules

- Never deploy to production without explicit user approval
- Retry transient failures (network timeouts, rate limits) up to 3 times before reporting failure
- If a rollback is needed, present the rollback steps clearly before executing
- Log everything — the user should be able to audit what was checked and what passed
