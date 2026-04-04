Extract reusable patterns and lessons from the current session and save them to memory.

## Instructions

1. **Analyze the Current Session**: Review what was accomplished in this conversation:
   - What problems were solved?
   - What debugging techniques worked?
   - What workarounds were needed?
   - What patterns emerged?

2. **Categorize Findings**:
   - **Bug Patterns**: Recurring bugs and their root causes
   - **Workarounds**: Non-obvious solutions to platform/tool limitations
   - **Architecture Decisions**: Why certain approaches were chosen
   - **Tool Tips**: Useful commands, flags, or configurations discovered
   - **Anti-patterns**: Approaches that were tried and failed (and why)

3. **Check for Duplicates**: Read existing memory files to avoid saving duplicate information.

4. **Save to Memory**: Update the appropriate memory file(s):
   - `~/.claude/projects/<project>/memory/MEMORY.md` for project-specific learnings
   - `~/.claude/CLAUDE.md` for global workflow preferences
   - Create topic-specific memory files if the learning is substantial

5. **Summarize**: Tell the user what was saved and where.

## Rules
- Only save patterns that are likely to recur
- Be specific -- include file paths, error messages, and exact solutions
- Don't save session-specific state (current task, in-progress work)
- Verify against project docs before writing architectural claims
