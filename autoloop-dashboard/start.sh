#!/bin/bash
# Start the autoloop dashboard server
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/server.pid"
PORT=$(node -e "try{console.log(require('$DIR/config.json').port)}catch{console.log(7890)}" 2>/dev/null || echo 7890)

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Dashboard already running (PID: $PID)"
        [ "$1" = "--open" ] && open "http://localhost:$PORT"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# Start server
cd "$DIR"
nohup node server.js > "$DIR/server.log" 2>&1 &
echo $! > "$PID_FILE"
echo "Dashboard started (PID: $!)"
# Wait for server to be ready (up to 6 seconds)
for i in $(seq 1 30); do
    curl -s "http://localhost:$PORT" > /dev/null 2>&1 && break
    sleep 0.2
done
open "http://localhost:$PORT"
