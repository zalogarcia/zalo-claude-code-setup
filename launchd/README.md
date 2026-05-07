# launchd jobs

macOS-specific background scheduling for Claude Code workflows. Plists are tracked here and symlinked into `~/Library/LaunchAgents/` so they're version-controlled across machines.

## Bootstrap on a new Mac

```bash
# Symlink each plist into LaunchAgents
for plist in ~/.claude/launchd/*.plist; do
  ln -sf "$plist" ~/Library/LaunchAgents/$(basename "$plist")
  launchctl load ~/Library/LaunchAgents/$(basename "$plist")
done

# Verify all loaded
launchctl list | grep "com.zalo.claude"
```

## Current jobs

| Plist                                | Schedule             | Runs                 | Purpose                                                                              |
| ------------------------------------ | -------------------- | -------------------- | ------------------------------------------------------------------------------------ |
| `com.zalo.claude.dream-weekly.plist` | Sunday 9:00 AM local | `claude -p "/dream"` | Weekly memory consolidation (writes proposal to `~/.claude/dreams/<id>/` for review) |

## Common ops

```bash
# Status
launchctl list | grep "com.zalo.claude"

# Trigger a one-shot run now (smoke test)
launchctl start com.zalo.claude.dream-weekly

# Tail latest run logs
tail -f ~/.claude/dreams/.scheduled-stdout.log

# Pause a job
launchctl unload ~/Library/LaunchAgents/com.zalo.claude.dream-weekly.plist

# Resume
launchctl load ~/Library/LaunchAgents/com.zalo.claude.dream-weekly.plist

# After editing a plist: unload, then load (launchd doesn't hot-reload)
launchctl unload ~/Library/LaunchAgents/com.zalo.claude.dream-weekly.plist
launchctl load ~/Library/LaunchAgents/com.zalo.claude.dream-weekly.plist
```

## Why symlinks instead of copies

The plist source of truth lives here in the repo. The symlink in `~/Library/LaunchAgents/` is what launchd reads. Editing the source updates both. Single source of truth, version-controlled, easy to add/remove jobs across machines.

## Path assumptions

The plist hardcodes `/Users/zalo/.local/bin/claude` and `/Users/zalo/.claude/dreams/...`. If your username differs, edit the plist before the first `launchctl load`.
