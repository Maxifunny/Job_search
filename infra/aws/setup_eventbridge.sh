#!/usr/bin/env bash
# Tworzy EventBridge Scheduler + Lambda + IAM (harmonogram: RAZ NA DZIEN).
#
# Wymagania: AWS CLI skonfigurowane (aws configure), EC2 z SSM Agent i rolą
# AmazonSSMManagedInstanceCore, aplikacja zainstalowana (install_ec2.sh).
#
# Użycie (z laptopa, NIE z EC2):
#   export AWS_REGION=eu-central-1
#   export EC2_INSTANCE_ID=i-0123456789abcdef0
#   export RUN_AS_USER=ubuntu
#   export PIPELINE_SCRIPT=/home/ubuntu/Job_search/infra/aws/run_daily_pipeline.sh
#   ./infra/aws/setup_eventbridge.sh
#
# Koszt free tier:
#   - EventBridge Scheduler: darmowe (miliony wywołań/mies.)
#   - Lambda: 1x/dzień = darmowe
#   - SSM Run Command: darmowe
#   - EC2 t3.micro: 750 h/mies. przez 12 mies. (wystarczy na 24/7)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

AWS_REGION="${AWS_REGION:-eu-central-1}"
EC2_INSTANCE_ID="${EC2_INSTANCE_ID:-}"
RUN_AS_USER="${RUN_AS_USER:-ubuntu}"
PIPELINE_SCRIPT="${PIPELINE_SCRIPT:-/home/ubuntu/Job_search/infra/aws/run_daily_pipeline.sh}"
SCHEDULE_HOUR="${SCHEDULE_HOUR:-8}"
SCHEDULE_TIMEZONE="${SCHEDULE_TIMEZONE:-Europe/Warsaw}"

FUNCTION_NAME="job-search-daily-trigger"
SCHEDULE_NAME="job-search-daily"
LAMBDA_ROLE_NAME="JobSearchDailyLambdaRole"
SCHEDULER_ROLE_NAME="JobSearchSchedulerRole"

log() { echo "[eventbridge-setup] $*"; }

if [[ -z "$EC2_INSTANCE_ID" ]]; then
  log "ERROR: Ustaw EC2_INSTANCE_ID (np. i-0abc123...)"
  log "  aws ec2 describe-instances --query 'Reservations[].Instances[].InstanceId'"
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  log "ERROR: Zainstaluj AWS CLI: https://aws.amazon.com/cli/"
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
log "Account: $ACCOUNT_ID Region: $AWS_REGION Instance: $EC2_INSTANCE_ID"

# --- Lambda IAM role ---
if ! aws iam get-role --role-name "$LAMBDA_ROLE_NAME" >/dev/null 2>&1; then
  log "Tworzenie roli Lambda: $LAMBDA_ROLE_NAME"
  aws iam create-role \
    --role-name "$LAMBDA_ROLE_NAME" \
    --assume-role-policy-document "file://$SCRIPT_DIR/iam/lambda-trust-policy.json"
  aws iam put-role-policy \
    --role-name "$LAMBDA_ROLE_NAME" \
    --policy-name JobSearchLambdaSsmPolicy \
    --policy-document "file://$SCRIPT_DIR/iam/lambda-ssm-policy.json"
  log "Czekam 10s na propagację IAM..."
  sleep 10
fi

LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"

# --- Package Lambda ---
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
cp "$SCRIPT_DIR/lambda/trigger_daily_pipeline.py" "$BUILD_DIR/"
(
  cd "$BUILD_DIR"
  zip -q function.zip trigger_daily_pipeline.py
)

log "Deploy Lambda: $FUNCTION_NAME"
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$BUILD_DIR/function.zip" \
    --region "$AWS_REGION" >/dev/null
  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "Variables={EC2_INSTANCE_ID=$EC2_INSTANCE_ID,RUN_AS_USER=$RUN_AS_USER,PIPELINE_SCRIPT=$PIPELINE_SCRIPT}" \
    --timeout 60 \
    --region "$AWS_REGION" >/dev/null
else
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.12 \
    --role "$LAMBDA_ROLE_ARN" \
    --handler trigger_daily_pipeline.lambda_handler \
    --zip-file "fileb://$BUILD_DIR/function.zip" \
    --timeout 60 \
    --environment "Variables={EC2_INSTANCE_ID=$EC2_INSTANCE_ID,RUN_AS_USER=$RUN_AS_USER,PIPELINE_SCRIPT=$PIPELINE_SCRIPT}" \
    --region "$AWS_REGION" >/dev/null
fi

LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"

# --- Scheduler IAM role ---
SCHEDULER_POLICY="$(sed "s/REGION/$AWS_REGION/g; s/ACCOUNT_ID/$ACCOUNT_ID/g" \
  "$SCRIPT_DIR/iam/scheduler-invoke-lambda-policy.json")"

if ! aws iam get-role --role-name "$SCHEDULER_ROLE_NAME" >/dev/null 2>&1; then
  log "Tworzenie roli Scheduler: $SCHEDULER_ROLE_NAME"
  aws iam create-role \
    --role-name "$SCHEDULER_ROLE_NAME" \
    --assume-role-policy-document "file://$SCRIPT_DIR/iam/scheduler-trust-policy.json"
  aws iam put-role-policy \
    --role-name "$SCHEDULER_ROLE_NAME" \
    --policy-name JobSearchSchedulerInvokeLambda \
    --policy-document "$SCHEDULER_POLICY"
  sleep 10
fi

SCHEDULER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${SCHEDULER_ROLE_NAME}"

# --- EventBridge Scheduler (raz dziennie) ---
CRON_EXPR="cron(0 ${SCHEDULE_HOUR} * * ? *)"
TARGET_JSON="$(cat <<EOF
{
  "Arn": "${LAMBDA_ARN}",
  "RoleArn": "${SCHEDULER_ROLE_ARN}",
  "Input": "{}"
}
EOF
)"

log "Harmonogram: ${CRON_EXPR} (${SCHEDULE_TIMEZONE})"

if aws scheduler get-schedule --name "$SCHEDULE_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  aws scheduler update-schedule \
    --name "$SCHEDULE_NAME" \
    --schedule-expression "$CRON_EXPR" \
    --schedule-expression-timezone "$SCHEDULE_TIMEZONE" \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target "$TARGET_JSON" \
    --region "$AWS_REGION" >/dev/null
else
  aws scheduler create-schedule \
    --name "$SCHEDULE_NAME" \
    --schedule-expression "$CRON_EXPR" \
    --schedule-expression-timezone "$SCHEDULE_TIMEZONE" \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target "$TARGET_JSON" \
    --region "$AWS_REGION" >/dev/null
fi

# Lambda resource policy — pozwól Scheduler wywołać funkcję
aws lambda add-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id "AllowEventBridgeScheduler" \
  --action "lambda:InvokeFunction" \
  --principal scheduler.amazonaws.com \
  --source-arn "arn:aws:scheduler:${AWS_REGION}:${ACCOUNT_ID}:schedule/${SCHEDULE_NAME}" \
  --region "$AWS_REGION" 2>/dev/null || true

log ""
log "=== Gotowe ==="
log "Harmonogram: $SCHEDULE_NAME — raz dziennie o ${SCHEDULE_HOUR}:00 ${SCHEDULE_TIMEZONE}"
log "Lambda: $FUNCTION_NAME → SSM → EC2 $EC2_INSTANCE_ID"
log ""
log "Test ręczny Lambda:"
log "  aws lambda invoke --function-name $FUNCTION_NAME --region $AWS_REGION /tmp/out.json && cat /tmp/out.json"
log ""
log "Logi pipeline na EC2:"
log "  ssh ... 'tail -100 ~/Job_search/logs/latest.log'"
log ""
log "Logi Lambda:"
log "  aws logs tail /aws/lambda/$FUNCTION_NAME --region $AWS_REGION --follow"
