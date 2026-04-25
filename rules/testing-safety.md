# Live App Testing Safety

When testing in a live application (staging or production), protect real user data and accounts.

## Admin-Only Testing

**When testing features in a running app, ONLY use an admin email/account.** Never create test accounts with random emails, never impersonate real users, never use throwaway emails that could collide with real signups.

- Use the project's designated admin/test email (check `.env`, `.env.local`, or ask on first encounter — then remember it)
- If no admin email is configured, ask the user for one before proceeding
- Never use `test@test.com`, `user@example.com`, or generated emails against a live system — these may belong to real people or trigger real email sends

## What This Applies To

- Signing up / logging in during live-test or e2e testing
- Creating records that reference a user (orders, subscriptions, profiles)
- Testing auth flows (password reset, magic link, OAuth)
- Testing payment flows (use Stripe test mode + admin email)
- Testing email/notification systems (sends go to real inboxes)

## What This Does NOT Apply To

- Unit tests with mocked auth (no real system involved)
- Local-only dev servers with seeded test databases
- Playwright tests against localhost with test fixtures
- Supabase local development (`supabase start`)

## In Autopilot / Autonomous Mode

When `/autopilot`, `/autotest`, or `/e2e` need to test in a live app:

1. Check for admin email in project config (`.env*`, `CLAUDE.md`, memory)
2. If found → use it for all test interactions
3. If not found → log "No admin email configured" to decisions.log and SKIP live-user testing (run build/typecheck/unit tests only)
4. Never generate fake user data against a live database in autonomous mode
