# /deploy-validate — Self-Healing Deployment Pipeline

Pre-deploy QA → deploy to staging → smoke test → log audit → human-action checkpoint for production.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/checkpoints.md
@~/.claude/rules/git-safety.md

## Pre-Deploy Gate (Abort Gate)

This is an Abort Gate per `~/.claude/rules/gates.md` Part 1. If anything below fails, **abort** — do NOT proceed to deploy.

1. Run full QA — apply `~/.claude/rules/gates.md` Part 2 Verification Gate Function:
   - `npx tsc --noEmit`
   - `npm run build`
   - Test suite if it exists
2. `git status` must be clean. Commit or stash anything outstanding (per `~/.claude/rules/git-safety.md`).

If any check fails → fix it, re-run, do NOT proceed until green.

## Deploy to Staging

3. Deploy edge functions: `supabase functions deploy <name>` for each changed function. Capture deployment output.
4. Smoke test each endpoint:
   - Curl with realistic test payloads
   - Validate response shape matches expected TypeScript types
   - Check HTTP status codes
5. Check logs for errors:
   - `mcp__supabase__get_logs` for the last 60 seconds
   - Flag any errors, warnings, unexpected patterns
6. Validate environment & config:
   - Required env vars set
   - JWT/auth configuration correct
   - New DB migrations applied

## Decision Point

7. If ANY staging check failed:
   - Report failure with root cause
   - Suggest specific fix
   - Do NOT proceed to production
   - Offer to fix and re-run

8. If ALL checks passed → proceed to Human-Action Checkpoint.

## Production Deploy — Human-Action Checkpoint

This is a `checkpoint:human-action` per `~/.claude/rules/checkpoints.md`. The deploy itself touches shared infrastructure — the human must approve and authorize.

```xml
<checkpoint type="human-action">
  <context>
    All pre-deploy + staging checks passed. Ready to deploy to production.
  </context>
  <summary>
    [What changed, what was tested, all green results — be specific]
  </summary>
  <ask>
    "All checks passed. Deploy to production? Type 'deploy' to confirm."
  </ask>
  <on-confirm>
    Run production deploy commands.
    Re-run smoke tests against production.
    Re-check logs against production.
  </on-confirm>
  <on-deny>
    Hold. Report what would have been deployed. End session.
  </on-deny>
</checkpoint>
```

**Never default to deploy.** If user response is ambiguous, default to Hold.

## Post-Deploy Verification (Verification Gate Function)

After production deploy:

1. Smoke test production endpoints (same payloads as staging).
2. Check production logs for errors in the next 2 minutes.
3. Report: deployed functions, smoke test results, log clean/issues.

## Rollback Plan

If post-deploy verification shows errors:

- Present rollback steps clearly **before** executing.
- Wait for user confirmation.
- For Supabase edge functions: redeploy the previous version (`supabase functions deploy <name> --import-map <previous>`).
- For migrations: present manual revert SQL — do not auto-revert migrations.

## Anti-Patterns (will not do)

- Deploy to production without explicit user typing "deploy".
- Auto-revert migrations (irreversible by default — needs human review).
- Skip the staging smoke test ("the build passed").
- Retry transient failures more than 3 times before reporting.
- Continue to production if any staging check is yellow ("probably fine").
