#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# run_mcp_servers.sh - Sprint 13 A1: MCP server standalone deployment (stdio + HTTP)
#
# Three MCP servers, launchable independently for external workloads:
#   - meta_cognition        : metacognition (hypothesis stats / reasoning / gate) -> :18010
#   - semantic_retrieval    : semantic retrieval (bge-m3 three-source lineage)    -> :18011
#   - environment_bootstrap : env bootstrap (snapshot / write-scope validation)   -> :18012
#
# Usage:
#   ./run_mcp_servers.sh start [http|stdio]   # start all (default http)
#   ./run_mcp_servers.sh start-one <name> [http|stdio]
#   ./run_mcp_servers.sh stop [<name>]        # stop all or one
#   ./run_mcp_servers.sh status               # process/port status
#   ./run_mcp_servers.sh probe                # curl HTTP health probe
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3

declare -A PORTS=(
  [meta_cognition]=18010
  [semantic_retrieval]=18011
  [environment_bootstrap]=18012
)
SERVER_NAMES=(meta_cognition semantic_retrieval environment_bootstrap)
PID_DIR="${SCRIPT_DIR}/.mcp_pids"

log() { echo "[run_mcp_servers] $*"; }

pid_file() { echo "${PID_DIR}/$1.pid"; }

ensure_pid_dir() { mkdir -p "$PID_DIR"; }

is_running() {
  local pf="$1"
  [[ -f "$pf" ]] || return 1
  local pid
  pid="$(cat "$pf" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

wait_http_ready() {
  local port="$1"
  local i
  for i in $(seq 1 20); do
    if (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null; then
      exec 3>&- 3<&- 2>/dev/null || true
      return 0
    fi
    sleep 0.5
  done
  return 1
}

start_one() {
  local name="$1" transport="${2:-http}"
  ensure_pid_dir
  local pf; pf="$(pid_file "$name")"
  if is_running "$pf"; then
    log "$name already running (pid $(cat "$pf"))"
    return 0
  fi
  local args=(--server "$name")
  local label="stdio"
  if [[ "$transport" == "http" ]]; then
    args+=(--transport streamable-http --host 127.0.0.1 --port "${PORTS[$name]}")
    label="http://127.0.0.1:${PORTS[$name]}/mcp"
  fi
  nohup "$PY" -m mcp_servers "${args[@]}" \
      >"${SCRIPT_DIR}/.mcp_logs_${name}.log" 2>&1 &
  echo $! > "$pf"
  sleep 1
  if ! is_running "$pf"; then
    log "$name failed to start, see .mcp_logs_${name}.log"
    return 1
  fi
  if [[ "$transport" == "http" ]]; then
    if wait_http_ready "${PORTS[$name]}"; then
      log "$name ready @ $label (pid $(cat "$pf"))"
      return 0
    else
      log "$name HTTP port not ready, see .mcp_logs_${name}.log"
      return 1
    fi
  fi
  log "$name ready @ $label (pid $(cat "$pf"))"
  return 0
}

stop_one() {
  local name="$1"
  local pf; pf="$(pid_file "$name")"
  if ! is_running "$pf"; then
    log "$name not running"
    rm -f "$pf" 2>/dev/null || true
    return 0
  fi
  local pid; pid="$(cat "$pf")"
  kill "$pid" 2>/dev/null && log "$name stopped (pid $pid)" || log "$name stop failed (pid $pid)"
  rm -f "$pf"
}

start_all() { local t="${1:-http}"; local n; for n in "${SERVER_NAMES[@]}"; do start_one "$n" "$t"; done; }
stop_all()  { local n; for n in "${SERVER_NAMES[@]}"; do stop_one "$n"; done; }

status_all() {
  local any=0 n
  for n in "${SERVER_NAMES[@]}"; do
    local pf; pf="$(pid_file "$n")"
    if is_running "$pf"; then
      echo "  [RUN ] $n pid=$(cat "$pf") port=${PORTS[$n]}"
      any=1
    else
      echo "  [STOP] $n"
    fi
  done
  [[ $any -eq 1 ]] || echo "  (none running)"
}

probe_all() {
  local n port
  for n in "${SERVER_NAMES[@]}"; do
    port="${PORTS[$n]}"
    echo "--- $n @ http://127.0.0.1:${port}/mcp ---"
    curl -sS -m 5 "http://127.0.0.1:${port}/mcp" \
      -H "Accept: application/json, text/event-stream" \
      || echo "  (HTTP probe failed)"
    echo
  done
}

cmd="${1:-}"
case "$cmd" in
  start)     start_all "${2:-http}" ;;
  start-one) start_one "${2:-}" "${3:-http}" ;;
  stop)      if [[ -n "${2:-}" ]]; then stop_one "$2"; else stop_all; fi ;;
  status)    status_all ;;
  probe)     probe_all ;;
  *)
    echo "Usage: $0 {start [http|stdio]|start-one <name> [http|stdio]|stop [<name>]|status|probe}"
    exit 1
    ;;
esac
