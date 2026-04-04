Detect and safely remove dead code, unused dependencies, and unnecessary complexity.

## Instructions

1. **Scan for Dead Code**:
   - Unused exports: Search for exported functions/components/types that are never imported elsewhere
   - Unused imports: Check each file for imports that aren't referenced
   - Unused variables: Look for declared but unused variables
   - Unreachable code: Code after return/throw statements
   - Commented-out code blocks (more than 3 lines)

2. **Scan for Unused Dependencies**:
   - Check `package.json` dependencies against actual imports in `src/`
   - Flag devDependencies that aren't used in scripts or configs

3. **Categorize by Safety**:
   - **Safe**: Unused imports, unused variables, commented-out code -- can delete immediately
   - **Likely Safe**: Unused exports (verify no dynamic imports first)
   - **Needs Verification**: Unused dependencies (might be used in configs, scripts, or CLI)

4. **Execute Cleanup** (after user confirmation):
   - Remove items in order: Safe → Likely Safe → Verified
   - After each batch, run the build to verify nothing broke
   - If build breaks, revert the last batch and flag for manual review

5. **Report**: Summary of what was removed, bytes/lines saved, and any remaining items that need manual decision.
