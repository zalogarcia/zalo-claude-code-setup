Save the current session context to a file for continuity across sessions.

## Instructions

1. **Summarize Current State**:
   - What task(s) were being worked on
   - What was completed
   - What's still in progress or pending
   - Any blockers or open questions
   - Key decisions made and their reasoning

2. **Save to Memory**: Write/update the project memory file at the current project's memory directory:
   `~/.claude/projects/<current-project>/memory/MEMORY.md`

   Determine the current project path from the working directory. Add a `## Last Session` section (replace any existing one) with:
   - Date
   - Task summary
   - Status (completed / in-progress / blocked)
   - Next steps

3. **Save Detailed State** (if substantial work was done):
   - Create/update topic-specific memory files for major learnings
   - Link from MEMORY.md

4. Confirm what was saved.
