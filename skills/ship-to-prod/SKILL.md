---
name: ship-to-prod
description: Ship delta-agents to production as one procedure — confirm target branch once, pre-flight via scripts/check.sh, heredoc commit, push, background-watch the "Deploy to ECS" run, ground-truth-verify per-service ECS image tags against the pushed SHA, smoke-test the gateway /health endpoint, and report. Use when the user says "ship it", "ship to prod", "deploy to prod", "push and deploy", or "commit, push and watch the deploy". Replaces the hand-rolled 200+-command commit/push/poll ritual with one background watch and a deterministic verification chain.
---

Ship the delta-agents repo (`/Users/zalo/dev/delta-agents`) to production ECS in one deterministic pass. Every constant below is grounded in `.github/workflows/deploy.yml` and `docs/RUNBOOK.md` — do not substitute names from memory.

## Grounded constants (from deploy.yml)

- **Workflow name:** `Deploy to ECS` — triggers ONLY on `push` to `main`. Pushing any other branch deploys nothing.
- **ECS cluster:** `delta-agents` (region `us-east-1`)
- **Services / containers / task-def families:** `gateway`, `worker`, `embedding-worker`, `insights-worker`, `url-watch-worker`, `wa-bailey` — task-def families are `delta-agents-{service}` (see `.aws/task-definitions/*.json`)
- **Image tag = full commit SHA:** `340829666011.dkr.ecr.us-east-1.amazonaws.com/delta-agents/{service}:{sha}`
- **Path-filtered deploys:** the `detect-changes` job (dorny/paths-filter) only deploys services whose paths changed. `packages/**` fans out to ALL six. `apps/widget/**` rebuilds the gateway (it serves the widget bundle). An `--allow-empty` commit deploys NOTHING.
- **Ordering:** worker deploys before gateway (`deploy-gateway` needs `deploy-worker`). Full run takes ~10-12 min. A `post-deploy-smoke` job runs last.
- **Health path:** `/health` in `apps/gateway/src/index.ts` returns `{"status":"ok","service":"gateway"}`. (`/ready` is the sticky readiness gate; RUNBOOK's `/healthz` is the ALB-level alias — the source-of-truth path is `/health`.)

## When to invoke

- The user approves shipping a finished change to production
- After an `/autopilot`/feature branch has been merged to `main` locally and needs to go live
- The user asks to "watch the deploy" for a push that is about to happen

Skip for: dashboard-only preview builds, local dev, anything not destined for `main`.

## Step 0 — Pre-flight (ask ONCE, then proceed)

1. **Branch permission — one question, one time.** Per `~/.claude/rules/git-safety.md`, never push without explicit permission. If the user's invocation already named the target ("ship to prod", "push to main"), that IS the permission — state `Target: push to main → Deploy to ECS` in your first reply and proceed. Otherwise ask exactly once ("Confirm: commit and push to `main`, which triggers the production ECS deploy?") and wait. Do NOT re-ask at the push step.
2. **Verify branch and tree state:**
   ```bash
   git branch --show-current   # must be main — the workflow only fires on main
   git status                  # staged set matches intent; no secrets; no stray files
   ```
   If not on `main`, stop and surface it — merging to `main` is a separate decision, not something this skill does silently.
3. **Run the repo's own check chain** (typecheck → build → test, failure-region output built in):
   ```bash
   scripts/check.sh
   ```
   Exit code non-zero → STOP and fix; do not commit a red tree. (In a repo without `scripts/check.sh`, fall back to the `typecheck-and-build` skill.)

## Step 1 — Commit (heredoc pattern)

Invoke the `commit-with-heredoc` skill: stage specific files (never `git add .`), review `git diff --cached`, then commit with the `$(cat <<'EOF' … EOF)` pattern including the `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer (adjust to the running model).

**Gotcha — the commit may time out but LAND.** The gitleaks-guard pre-commit hook can eat the Bash tool budget so the call reports a timeout while git finished underneath. Before any retry:

```bash
git log -1 --format="%H %s"
```

If the commit is there, do NOT retry — a blind retry duplicates the commit. Capture the SHA now:

```bash
SHA=$(git rev-parse HEAD)
```

## Step 2 — Push

Only after the Step 0 confirmation:

```bash
git push origin main
```

Run it FOREGROUND (never background a mutating git op — the credential helper needs the TTY) and read the result in the same turn.

## Step 3 — Find and watch the deploy run (background, never poll)

A push to `main` triggers MULTIPLE workflow runs (lint guardrails go green in ~30s and will fool a bare `gh run list --limit 1`). Select the deploy run explicitly and confirm its `headSha` matches `$SHA`:

```bash
gh run list --workflow "Deploy to ECS" --limit 1 \
  --json databaseId,status,conclusion,headSha \
  --jq '.[0] | "\(.databaseId) \(.status) \(.conclusion // "in_progress") \(.headSha[0:8])"'
```

(If the run hasn't registered yet, re-run after ~10s.) Then watch it **as a background task** — pass `run_in_background: true` on the Bash call so the ~10-12 min roll never foreground-polls the main context:

```bash
RUN_ID=$(gh run list --workflow "Deploy to ECS" --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
```

Do other work or wait for the background completion callback. When it returns, check the conclusion explicitly — `gh run watch --exit-status` has been observed exiting 0 while the run concluded `failure`:

```bash
gh run view "$RUN_ID" --json conclusion,url --jq '"\(.conclusion) \(.url)"'
```

`conclusion` must be `success`. On `failure`, open the failed job logs (`gh run view "$RUN_ID" --log-failed`) and route via RUNBOOK §"Deploy pipeline". Known transient: `auth.docker.io/token: 504 Gateway Timeout` on `FROM node:22-slim` is a Docker Hub outage, not your code — re-run the failed jobs once it recovers.

## Step 4 — Ground-truth verification (the deploy-clobber check)

**A green run is NOT proof your SHA is live.** A manually re-run OLDER deploy can overwrite a newer commit's services (hit live 2026-06-08). Ground truth is the image tag on each service's active task definition:

```bash
for svc in gateway worker embedding-worker insights-worker url-watch-worker wa-bailey; do
  td=$(aws ecs describe-services --cluster delta-agents --services "$svc" \
    --query 'services[0].taskDefinition' --output text)
  img=$(aws ecs describe-task-definition --task-definition "$td" \
    --query 'taskDefinition.containerDefinitions[0].image' --output text)
  echo "$svc ${img##*:}"
done
```

(The `zalo-admin` IAM user is configured locally — `aws sts get-caller-identity` confirms.)

Interpretation — compare each tag to `$SHA`:

- Services whose watched paths changed in this push → tag MUST equal `$SHA`. Mismatch = clobber or failed job; fix by re-running the NEWER run in full (`gh run rerun "$RUN_ID"` — not `--failed`, since "succeeded" jobs get skipped) so concurrency queues it last, then re-verify.
- Services whose paths did NOT change → an older tag is EXPECTED (paths-filter skipped them). Do not flag these.

## Step 5 — Smoke test

```bash
curl -sS -o /tmp/ship-health.json -w "HTTP %{http_code}\n" https://api.operatorbase.app/health
cat /tmp/ship-health.json
```

Expect `HTTP 200` and `{"status":"ok","service":"gateway"}`. Non-200 → the deploy is NOT done regardless of green CI; go to RUNBOOK "First 5 minutes".

## Step 6 — Report

One block, all evidence fresh from this session:

```
Shipped: {SHA} ({subject line})
Run: {conclusion} — {run URL}
Image tags: gateway={tag} worker={tag} embedding-worker={tag} insights-worker={tag} url-watch-worker={tag} wa-bailey={tag}
Smoke: GET https://api.operatorbase.app/health → HTTP {code}
```

## Anti-patterns

- ❌ Foreground `gh run watch` or a sleep/curl polling loop in main context — background the watch
- ❌ `gh run list --limit 1` without `--workflow "Deploy to ECS"` — grabs the 30s lint run and declares victory early
- ❌ Trusting `gh run watch` exit 0 or a green badge as "deployed" — verify per-service image tags (Step 4)
- ❌ Retrying a "timed out" commit without `git log -1` first — duplicates the commit
- ❌ `--allow-empty` commit to force a redeploy — `detect-changes` is path-gated and skips every build; use `gh run rerun` on the newest run instead
- ❌ Re-asking for push permission at every step — Step 0 asks once; after that, proceed
