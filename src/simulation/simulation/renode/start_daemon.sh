#!/bin/bash
# Start Renode as a background daemon that survives bash session end
nohup renode --port 3333 --disable-xwt > /tmp/renode_bg.log 2>&1 &
RPID=$!
echo "PID=$RPID"
echo "$RPID" > /tmp/renode_bg.pid

for i in $(seq 1 30); do
  if nc -w1 127.0.0.1 3333 </dev/null 2>/dev/null; then
    echo "READY after ${i}s"
    exit 0
  fi
  if ! kill -0 $RPID 2>/dev/null; then
    echo "Renode died. Log:"
    tail -10 /tmp/renode_bg.log
    exit 1
  fi
  sleep 1
done
echo "TIMEOUT"
exit 1
