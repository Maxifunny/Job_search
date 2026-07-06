#!/usr/bin/env bash
# Instalacja Job Search na Azure VM (Ubuntu 22.04).
#
# Uruchom na VM po sklonowaniu repozytorium:
#   chmod +x infra/azure/install_vm.sh infra/azure/run_daily_pipeline.sh
#   ./infra/azure/install_vm.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

log() { echo "[install] $*"; }

if [[ "$(id -u)" -eq 0 ]]; then
  log "Uruchom skrypt jako zwykły użytkownik (azureuser), nie root."
  exit 1
fi

log "Instalacja w: $REPO_ROOT"

sudo apt-get update -qq
sudo apt-get install -y python3 python3-venv python3-pip git

if [[ ! -d ".venv" ]]; then
  log "Tworzenie venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

mkdir -p data logs

if [[ ! -f ".env" ]]; then
  log "UWAGA: Skopiuj infra/azure/env.vm.example → .env i uzupełnij sekrety."
  cp infra/azure/env.vm.example .env
fi

log "init-db + migrate..."
python -m job_search.cli init-db || true
python -m job_search.cli migrate

chmod +x infra/azure/run_daily_pipeline.sh

log ""
log "=== Następny krok: harmonogram (raz dziennie) ==="
log "  Na laptopie (PowerShell + Az module):"
log "    ./infra/azure/Setup-DailySchedule.ps1 -ResourceGroupName job-search-rg -VMName job-search-vm"
log ""
log "  Lub: Logic Apps w portalu Azure — docs/agents/azure-deployment-agent.md"
log ""
log "Test ręczny na VM:"
log "  ./infra/azure/run_daily_pipeline.sh"
log "  tail -f logs/latest.log"
