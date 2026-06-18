#!/usr/bin/env bash
# Instalacja Job Search na EC2 (Ubuntu 22.04 / Amazon Linux 2023).
#
# Uruchom na serwerze po sklonowaniu repozytorium:
#   chmod +x infra/aws/install_ec2.sh infra/aws/run_daily_pipeline.sh
#   ./infra/aws/install_ec2.sh
#
# Wymaga: git clone już wykonany, plik .env skonfigurowany.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

log() { echo "[install] $*"; }

if [[ "$(id -u)" -eq 0 ]]; then
  log "Uruchom skrypt jako zwykły użytkownik (ubuntu/ec2-user), nie root."
  exit 1
fi

log "Instalacja w: $REPO_ROOT"

# Python 3.11+
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y python3 python3-venv python3-pip git cron
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip git cronie
  sudo systemctl enable crond
  sudo systemctl start crond
else
  log "Nieobsługiwana dystrybucja — zainstaluj ręcznie: python3, venv, git, cron"
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  log "Tworzenie venv..."
  python3 -m venv .venv
fi

log "pip install..."
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

mkdir -p data logs

if [[ ! -f ".env" ]]; then
  log "UWAGA: Skopiuj infra/aws/env.ec2.example → .env i uzupełnij sekrety."
  cp infra/aws/env.ec2.example .env
fi

log "init-db + migrate..."
python -m job_search.cli init-db || true
python -m job_search.cli migrate

chmod +x infra/aws/run_daily_pipeline.sh infra/aws/setup_eventbridge.sh 2>/dev/null || true

# SSM Agent (wymagany do EventBridge → Lambda → SSM)
if command -v amazon-ssm-agent >/dev/null 2>&1; then
  log "SSM Agent: zainstalowany"
elif command -v snap >/dev/null 2>&1; then
  log "Instalacja SSM Agent (snap)..."
  sudo snap install amazon-ssm-agent --classic || true
  sudo systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service || true
  sudo systemctl start snap.amazon-ssm-agent.amazon-ssm-agent.service || true
else
  log "UWAGA: Zainstaluj SSM Agent — wymagany do harmonogramu EventBridge."
  log "  Na EC2 przy tworzeniu instancji dołącz IAM role: AmazonSSMManagedInstanceCore"
fi

chmod +x infra/aws/run_daily_pipeline.sh

log ""
log "=== Następny krok: EventBridge (raz dziennie, free tier) ==="
log "  Na laptopie (z AWS CLI):"
log "    export AWS_REGION=eu-central-1"
log "    export EC2_INSTANCE_ID=i-..."
log "    ./infra/aws/setup_eventbridge.sh"
log ""
log "  Alternatywa: cron — infra/aws/crontab.example"
log ""
log "Test ręczny na EC2:"
log "  ./infra/aws/run_daily_pipeline.sh"
log "  tail -f logs/latest.log"
