#!/bin/bash
# Stop the autoloop dashboard server
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/server.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill "$PID" 2>/dev/null; then
        echo "Dashboard stopped (PID: $PID)"
    else
        echo "Process $PID already dead"
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file found"
fi
