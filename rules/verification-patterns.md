# Verification Patterns

The defining principle for `qa-agent`, `live-test`, and any "is it actually done?" check.

## Core Principle

**Existence ≠ Implementation.**

A file existing does not mean the feature works. Verification must check:

1. **Exists** — File present at expected path.
2. **Substantive** — Content is real implementation, not placeholder.
3. **Wired** — Connected to the rest of the system.
4. **Functional** — Actually works when invoked.

Levels 1-3 can be checked programmatically with greps. Level 4 often requires running the code or `live-test`.

## Universal Stub-Detection Greps

Run these against any file claimed as "done":

```bash
# Comment-based stubs
grep -E "(TODO|FIXME|XXX|HACK|PLACEHOLDER)" "$file"
grep -iE "implement|add later|coming soon|will be" "$file"
grep -E "// \.\.\.|/\* \.\.\. \*/|# \.\.\." "$file"

# Placeholder text in output
grep -iE "placeholder|lorem ipsum|coming soon|under construction" "$file"
grep -iE "sample|example|test data|dummy" "$file"
grep -E "\[.*\]|<.*>|\{.*\}" "$file"  # Template brackets left in

# Empty/trivial implementations
grep -E "return null|return undefined|return \{\}|return \[\]" "$file"
grep -E "pass$|\.\.\.|\bnothing\b" "$file"
grep -E "console\.(log|warn|error).*only" "$file"  # Log-only functions
```

## React Stub Red Flags

```jsx
// RED FLAGS - These are stubs:
return <div>Component</div>
return <div>Placeholder</div>
return <div>{/* TODO */}</div>
return <p>Coming soon</p>
return null
return <></>

// Also stubs - empty handlers:
onClick={() => {}}
onChange={() => console.log('clicked')}
onSubmit={(e) => e.preventDefault()}  // Only prevents default, does nothing
```

## API Route Stubs

```typescript
// RED FLAGS:
export async function POST() {
  return Response.json({ message: "Not implemented" });
}
export async function GET() {
  return Response.json([]); // Empty array with no DB query
}
```

## Wiring Verification

After confirming substantive content, verify wiring:

- **Component → API**: grep the component for the fetch/call; verify the response shape is actually used.
- **API → Database**: grep the route for the DB query; verify columns/tables exist.
- **Form → Handler**: grep the form for the submit handler; verify it does more than `preventDefault`.
- **State → Render**: grep the component for the state variable; verify it's rendered, not just declared.

## Aggregate Shell Checks

```bash
check_exists()      { [ -f "$1" ] && echo "EXISTS: $1" || echo "MISSING: $1"; }
check_stubs()       { local stubs=$(grep -c -E "TODO|FIXME|placeholder|not implemented" "$1" 2>/dev/null || echo 0); [ "$stubs" -gt 0 ] && echo "STUB_PATTERNS: $stubs in $1"; }
check_wiring()      { grep -q "$2" "$1" && echo "WIRED: $1 → $2" || echo "NOT_WIRED: $1 → $2"; }
check_substantive() { local lines=$(wc -l < "$1"); [ "$lines" -ge "$2" ] && echo "SUBSTANTIVE" || echo "THIN"; }
```

## Common Failures Table

| Claim            | Requires                        | Not Sufficient              |
| ---------------- | ------------------------------- | --------------------------- |
| Tests pass       | Test command output: 0 failures | "Should pass"               |
| Linter clean     | Linter output: 0 errors         | Partial check               |
| Build succeeds   | Build command: exit 0           | Logs look good              |
| Bug fixed        | Test original symptom: passes   | Code changed, assumed fixed |
| Agent completed  | VCS diff shows changes          | Agent reports "success"     |
| Requirements met | Line-by-line spec checklist     | Tests passing               |

(See also `~/.claude/rules/gates.md` Part 2 — Verification Gate Function.)
