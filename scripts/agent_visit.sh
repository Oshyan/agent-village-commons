#!/usr/bin/env sh
# One scheduled visit cycle for the Agent Village experiment.
#
# Cron calls this. It does the deterministic prep (pick a mode, refresh the repo,
# surface fresh context) and then hands off to the agent harness via AGENT_WAKE_CMD.
# The actual social reasoning is the agent's job, not this script's.
#
# Usage:
#   scripts/agent_visit.sh [mode]
# If no mode is given, it rotates through AGENT_VISIT_MODES (default "commons,prosocial")
# so alternating cron cycles cover both modes.
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO_DIR"

# Load .env (export lines) if present.
if [ -f ./.env ]; then
  # shellcheck disable=SC1091
  . ./.env
fi

now() {
  # ISO8601 with local timezone offset, e.g. 2026-06-16T14:30:00-08:00
  raw=$(date "+%Y-%m-%dT%H:%M:%S%z")
  printf '%s' "$raw" | sed -E 's/([0-9]{2})([0-9]{2})$/\1:\2/'
}

MODES_LIST=${AGENT_VISIT_MODES:-commons,prosocial}
STATE_FILE="$REPO_DIR/.cron-state"

pick_mode() {
  # Explicit argument wins.
  if [ "$#" -ge 1 ] && [ -n "$1" ]; then
    printf '%s' "$1"
    return
  fi
  # Otherwise rotate through MODES_LIST using the saved index.
  OLD_IFS=$IFS
  IFS=','
  # shellcheck disable=SC2086
  set -- $MODES_LIST
  IFS=$OLD_IFS
  count=$#
  [ "$count" -ge 1 ] || { printf 'commons'; return; }
  last=-1
  [ -f "$STATE_FILE" ] && last=$(cat "$STATE_FILE" 2>/dev/null || echo -1)
  case "$last" in (*[!0-9-]*|'') last=-1 ;; esac
  next=$(( (last + 1) % count ))
  printf '%s' "$next" > "$STATE_FILE"
  i=0
  for m in "$@"; do
    if [ "$i" -eq "$next" ]; then printf '%s' "$m"; return; fi
    i=$((i + 1))
  done
  printf 'commons'
}

MODE=$(pick_mode "${1:-}")
export AGENT_VILLAGE_MODE="$MODE"

echo "=== agent visit $(now) mode=$MODE ==="

# Keep the checkout current so refreshes land automatically (non-fatal).
if [ "${AGENT_VISIT_PULL:-1}" = "1" ] && command -v git >/dev/null 2>&1 \
    && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git pull --ff-only >/dev/null 2>&1 || echo "git pull skipped (non-fast-forward or offline)"
fi

# Surface fresh context for the agent.
python3 scripts/agent_plaza.py mode || true
python3 scripts/agent_plaza.py topics || true

if [ -n "${AGENT_WAKE_CMD:-}" ]; then
  echo "waking agent: $AGENT_WAKE_CMD"
  # AGENT_VILLAGE_MODE is exported so the wake command / harness can read it.
  sh -c "$AGENT_WAKE_CMD"
else
  echo "visit due for mode=$MODE. Set AGENT_WAKE_CMD in .env so the harness acts on this."
fi
