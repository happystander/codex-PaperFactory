#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROLLER="$PLUGIN_ROOT/scripts/researchctl.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CODEX_BIN="${CODEX_BIN:-codex}"
RESEARCH_DIR=".research"
TASK=""
UNTIL=""
INTERVAL="1800"
ONCE="0"

usage() {
  cat <<'EOF'
Usage:
  autonomous_loop.sh --task "research task" --until "YYYY-MM-DD HH:MM:SS" [--interval 1800]
  autonomous_loop.sh --once

Environment:
  PYTHON_BIN   Python executable, default python3
  CODEX_BIN    Codex CLI executable, default codex
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      TASK="$2"; shift 2 ;;
    --until)
      UNTIL="$2"; shift 2 ;;
    --interval)
      INTERVAL="$2"; shift 2 ;;
    --research-dir)
      RESEARCH_DIR="$2"; shift 2 ;;
    --once)
      ONCE="1"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2 ;;
  esac
done

if [[ ! -f "$RESEARCH_DIR/state.json" ]]; then
  if [[ -z "$TASK" ]]; then
    echo "No $RESEARCH_DIR/state.json found. Provide --task to initialize." >&2
    exit 2
  fi
  "$PYTHON_BIN" "$CONTROLLER" --research-dir "$RESEARCH_DIR" init --task "$TASK"
fi

mkdir -p "$RESEARCH_DIR/logs"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Loop start: until=${UNTIL:-once-or-manual-stop} interval=${INTERVAL}s" >> "$RESEARCH_DIR/logs/research.log"

run_once() {
  local prompt_file
  prompt_file="$(mktemp)"
  "$PYTHON_BIN" "$CONTROLLER" --research-dir "$RESEARCH_DIR" next-prompt > "$prompt_file"
  "$CODEX_BIN" exec --full-auto --skip-git-repo-check "$(cat "$prompt_file")" >> "$RESEARCH_DIR/logs/codex-loop.out" 2>&1 || {
    local rc=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Codex cycle failed: rc=$rc" >> "$RESEARCH_DIR/logs/research.log"
  }
  rm -f "$prompt_file"
  "$PYTHON_BIN" "$CONTROLLER" --research-dir "$RESEARCH_DIR" status >> "$RESEARCH_DIR/logs/codex-loop.out" 2>&1 || true
}

if [[ "$ONCE" == "1" ]]; then
  run_once
  exit 0
fi

if [[ -z "$UNTIL" ]]; then
  echo "--until is required unless --once is used." >&2
  exit 2
fi

while true; do
  if [[ "$(date +%s)" -ge "$(date -d "$UNTIL" +%s)" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Loop stop: reached until=$UNTIL" >> "$RESEARCH_DIR/logs/research.log"
    exit 0
  fi
  run_once
  sleep "$INTERVAL"
done
