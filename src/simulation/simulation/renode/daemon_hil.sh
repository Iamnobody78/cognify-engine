#!/bin/bash
# Start Renode HIL bridge as persistent daemon
RESC="/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/simulation/renode/hil_startup.resc"
LOGFILE="/tmp/renode_hil.log"
PIDFILE="/tmp/renode_hil.pid"

# Kill any existing renode
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    kill $OLD_PID 2>/dev/null || true
    sleep 1
fi

echo "Starting Renode in background..."
nohup renode --port 3333 --disable-xwt -e "i @${RESC}" > "$LOGFILE" 2>&1 &
RENODE_PID=$!
echo "$RENODE_PID" > "$PIDFILE"

echo "Renode PID: $RENODE_PID"
echo "Waiting for monitor port..."

for i in $(seq 1 30); do
    if nc -w1 127.0.0.1 3333 < /dev/null 2>/dev/null; then
        echo "Port 3333 ready after ${i}s"
        break
    fi
    if ! kill -0 $RENODE_PID 2>/dev/null; then
        echo "ERROR: Renode exited early. Last log lines:"
        tail -20 "$LOGFILE"
        exit 1
    fi
    sleep 1
done

# Quick connectivity test
echo 'mach set "F407"' | timeout 2 nc -w2 127.0.0.1 3333 > /dev/null 2>&1 && echo "Monitor responsive" || echo "Monitor NOT responsive"

echo "READY"
