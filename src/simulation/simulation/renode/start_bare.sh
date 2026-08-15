#!/bin/bash
renode --port 3333 --disable-xwt &
RPID=$!
echo "PID=$RPID"
for i in $(seq 1 30); do
  if nc -w1 127.0.0.1 3333 </dev/null 2>/dev/null; then
    echo "READY after ${i}s"
    exit 0
  fi
  sleep 1
done
echo "FAILED"
exit 1
