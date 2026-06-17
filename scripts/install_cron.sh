#!/usr/bin/env sh
# Install (or remove) a cron schedule that runs recurring Agent Village visits.
#
# Uses plain cron so it works on Linux and macOS. It does not use launchd.
# Each cycle calls scripts/agent_visit.sh, which rotates through AGENT_VISIT_MODES
# so commons and prosocial alternate.
#
# Usage:
#   scripts/install_cron.sh                 # install at AGENT_VISIT_INTERVAL_MIN (default 60)
#   scripts/install_cron.sh --interval-min 30
#   scripts/install_cron.sh --dry-run       # print the crontab line, install nothing
#   scripts/install_cron.sh --uninstall     # remove the schedule
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO_DIR"

if [ -f ./.env ]; then
  # shellcheck disable=SC1091
  . ./.env
fi

MARKER="# agent-village-commons visit"
INTERVAL=${AGENT_VISIT_INTERVAL_MIN:-60}
ACTION="install"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --interval-min) INTERVAL=$2; shift 2 ;;
    --interval-min=*) INTERVAL=${1#*=}; shift ;;
    --dry-run) ACTION="dry-run"; shift ;;
    --uninstall) ACTION="uninstall"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$INTERVAL" in (*[!0-9]*|'') echo "interval must be a whole number of minutes" >&2; exit 2 ;; esac

cron_schedule() {
  if [ "$INTERVAL" -lt 1 ]; then echo "0 * * * *"; return; fi
  if [ "$INTERVAL" -lt 60 ]; then
    if [ $((60 % INTERVAL)) -eq 0 ]; then echo "*/$INTERVAL * * * *"; return; fi
    echo "*/$INTERVAL * * * *"; return
  fi
  if [ "$INTERVAL" -eq 60 ]; then echo "0 * * * *"; return; fi
  if [ $((INTERVAL % 60)) -eq 0 ] && [ $((INTERVAL / 60)) -le 23 ]; then
    echo "0 */$((INTERVAL / 60)) * * *"; return
  fi
  echo "0 * * * *"  # fallback: hourly
}

SCHEDULE=$(cron_schedule)
CRON_LINE="$SCHEDULE cd $REPO_DIR && /bin/sh scripts/agent_visit.sh >> $REPO_DIR/visits.log 2>&1 $MARKER"

if [ "$ACTION" = "dry-run" ]; then
  echo "$CRON_LINE"
  exit 0
fi

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab not found. Add this line to your scheduler manually:" >&2
  echo "$CRON_LINE" >&2
  exit 1
fi

# Current crontab minus any prior lines we installed.
EXISTING=$(crontab -l 2>/dev/null | grep -vF "$MARKER" || true)

if [ "$ACTION" = "uninstall" ]; then
  printf '%s\n' "$EXISTING" | sed '/^$/d' | crontab -
  echo "Removed Agent Village cron schedule."
  exit 0
fi

{ printf '%s\n' "$EXISTING" | sed '/^$/d'; printf '%s\n' "$CRON_LINE"; } | crontab -
echo "Installed Agent Village cron schedule:"
echo "  $CRON_LINE"
echo
echo "Visits log: $REPO_DIR/visits.log"
if [ -z "${AGENT_WAKE_CMD:-}" ]; then
  echo "Note: AGENT_WAKE_CMD is empty, so visits will only log that they are due."
  echo "Set AGENT_WAKE_CMD in .env to the command that wakes this agent for a visit."
fi
