#!/usr/bin/env bash
# Codzienny pipeline Job Search (scrape → match → email).
# Uruchamiany przez cron RAZ na dzień — patrz crontab.example.
#
# Użycie ręczne:
#   ./infra/aws/run_daily_pipeline.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="${JOB_SEARCH_LOG_DIR:-$REPO_ROOT/logs}"
DATA_DIR="${JOB_SEARCH_DATA_DIR:-$REPO_ROOT/data}"
mkdir -p "$LOG_DIR" "$DATA_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/job_search_${TIMESTAMP}.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

exec >>"$LOG_FILE" 2>&1

log "=== Job Search daily run ==="
log "Repo: $REPO_ROOT"

VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  log "ERROR: Brak .venv — uruchom infra/aws/install_ec2.sh"
  exit 1
fi

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  log "ERROR: Brak pliku .env w $REPO_ROOT"
  exit 1
fi

# Parametry z .env lub domyślne (nadpisz w .env: JOB_SEARCH_SECTOR=...)
# shellcheck disable=SC1091
set -a
source "$REPO_ROOT/.env"
set +a

SECTOR="${JOB_SEARCH_SECTOR:-data}"
PROFILE="${JOB_SEARCH_PROFILE:-config/profiles/default.json}"
SOURCE="${JOB_SEARCH_SOURCE:-justjoin}"
MAX_OFFERS="${JOB_SEARCH_MAX_OFFERS:-30}"
MATCH_LIMIT="${JOB_SEARCH_MATCH_LIMIT:-20}"

log "Sector=$SECTOR Profile=$PROFILE Source=$SOURCE MaxOffers=$MAX_OFFERS MatchLimit=$MATCH_LIMIT"
log "NOTIFIER_ENABLED=${NOTIFIER_ENABLED:-false}"

log "migrate..."
"$VENV_PYTHON" -m job_search.cli migrate

log "run pipeline..."
set +e
"$VENV_PYTHON" -m job_search.cli run \
  --sector "$SECTOR" \
  --profile "$PROFILE" \
  --source "$SOURCE" \
  --max-offers "$MAX_OFFERS" \
  --match-limit "$MATCH_LIMIT"
EXIT_CODE=$?
set -e

log "Finished with exit code $EXIT_CODE"
log "Log file: $LOG_FILE"

# Symlink do ostatniego logu (wygodne przy SSH)
ln -sf "$LOG_FILE" "$LOG_DIR/latest.log"

exit "$EXIT_CODE"
