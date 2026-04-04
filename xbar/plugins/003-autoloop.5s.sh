#!/bin/bash

# xbar metadata
# <xbar.title>Autoloop Monitor</xbar.title>
# <xbar.desc>Monitor autonomous code optimization loops</xbar.desc>
# <xbar.version>1.0</xbar.version>

DASHBOARD_DIR="$HOME/.claude/autoloop-dashboard"
CONFIG="$DASHBOARD_DIR/config.json"
SERVER_PID_FILE="$DASHBOARD_DIR/server.pid"
PORT=7890

# Read config
if [ ! -f "$CONFIG" ]; then
    echo "AL"
    echo "---"
    echo "No config found | color=#8b949e"
    exit 0
fi

# Check server status
server_running=false
if [ -f "$SERVER_PID_FILE" ]; then
    srv_pid=$(cat "$SERVER_PID_FILE")
    if kill -0 "$srv_pid" 2>/dev/null; then
        server_running=true
    fi
fi

# Parse directories from config
dirs=$(python3 -c "
import json, sys
try:
    c = json.load(open('$CONFIG'))
    for d in c.get('directories', []):
        print(d)
except:
    pass
" 2>/dev/null)

total=0
running=0
completed=0
phases=""

while IFS= read -r dir; do
    [ -z "$dir" ] && continue
    total=$((total + 1))

    autoloop_dir="$dir/.autoloop"
    phase="--"
    status="stopped"
    name=$(basename "$dir")

    if [ -d "$autoloop_dir" ]; then
        # Read phase
        if [ -f "$autoloop_dir/phase.txt" ]; then
            phase=$(cat "$autoloop_dir/phase.txt" 2>/dev/null | tr -d '[:space:]')
            [ -z "$phase" ] && phase="unknown"
        fi

        # Check if running
        if [ -f "$autoloop_dir/harness.pid" ]; then
            h_pid=$(cat "$autoloop_dir/harness.pid" 2>/dev/null)
            if [ -n "$h_pid" ] && kill -0 "$h_pid" 2>/dev/null; then
                status="running"
                running=$((running + 1))
            fi
        fi

        if [ "$phase" = "complete" ]; then
            status="completed"
            completed=$((completed + 1))
        fi
    fi

    phases="$phases$name|$phase|$status\n"
done <<< "$dirs"

# Menu bar icon
if [ "$running" -gt 0 ]; then
    echo "AL:$running | color=#3fb950"
elif [ "$completed" -gt 0 ] && [ "$running" -eq 0 ]; then
    echo "AL | color=#3fb950"
else
    echo "AL | color=#8b949e"
fi

echo "---"

# Per-project status
if [ "$total" -eq 0 ]; then
    echo "No projects monitored | color=#8b949e"
else
    echo -e "$phases" | while IFS='|' read -r name phase status; do
        [ -z "$name" ] && continue
        case "$status" in
            running)   icon="🟢" ;;
            completed) icon="✅" ;;
            *)         icon="⚫" ;;
        esac
        echo "$icon $name: $phase"
    done
fi

echo "---"

# Dashboard link — open directly if running, start server first if not
if $server_running; then
    echo "Open Dashboard | href=http://localhost:$PORT"
else
    echo "Open Dashboard | bash='$DASHBOARD_DIR/start.sh' param1='--open' terminal=false"
fi

echo "---"
echo "Refresh | refresh=true"
