#!/bin/bash
# Start Renode HIL bridge, wait for monitor port
set -e

RESC="/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/simulation/renode/hil_startup.resc"

echo "=== Starting Renode with HIL startup ==="
renode --port 3333 --disable-xwt -e "i @${RESC}" &
RENODE_PID=$!
echo "Renode PID: ${RENODE_PID}"

# Wait for monitor port to be ready
for i in $(seq 1 30); do
  if echo "" | nc -w1 127.0.0.1 3333 2>/dev/null; then
    echo "Renode monitor port ready after ${i}s"
    break
  fi
  if ! kill -0 ${RENODE_PID} 2>/dev/null; then
    echo "ERROR: Renode process died"
    exit 1
  fi
  sleep 1
done

# Verify both machines
echo "=== Verifying machines ==="
echo 'mach set "F407"' | nc -w2 127.0.0.1 3333
echo 'cpu PC' | nc -w2 127.0.0.1 3333
echo "---"
echo 'mach set "F103"' | nc -w2 127.0.0.1 3333
echo 'cpu PC' | nc -w2 127.0.0.1 3333

echo "=== HIL Bridge Ready ==="
echo "PID=${RENODE_PID}" > /tmp/renode_hil.pid
