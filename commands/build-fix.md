Detect and fix build errors iteratively with guardrails.

## Instructions

1. **Detect Build System**: Look for `package.json`, `tsconfig.json`, `vite.config.*`, `next.config.*`, etc. Determine the correct build command (e.g., `npm run build`, `npx tsc --noEmit`, `vite build`).

2. **Run the Build**: Execute the build command and capture all errors.

3. **Parse Errors**: Extract each unique error with file path, line number, and error message. Group by file.

4. **Fix One at a Time**: For each error:
   a. Read the file around the error location
   b. Understand the root cause
   c. Apply the minimal fix
   d. Re-run the build to verify

5. **Guardrails**:
   - If a fix introduces MORE errors than it resolves, REVERT the change and try a different approach
   - After 5 consecutive failed fix attempts on the same error, STOP and ask the user for guidance
   - Never modify test files unless the error is specifically in a test
   - Never delete code to "fix" type errors -- fix the types properly

6. **Report**: When all errors are resolved (or you're blocked), summarize:
   - Total errors found → fixed
   - Files modified
   - Any remaining issues that need manual attention
