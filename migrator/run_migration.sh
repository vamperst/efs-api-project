#!/usr/bin/env bash
#
# Dispara a migracao EFS -> S3 na EC2 migrator via SSM send-command.
# O script /usr/local/bin/migrate.sh ja foi colocado na instancia pelo user-data
# e faz copia POSIX de /mnt/efs (EFS real) -> /mnt/s3 (bucket montado com
# Mountpoint for S3), usando rsync em paralelo.
#
# Uso:
#   ./run_migration.sh <instance-id> [--region us-east-1]
#
set -euo pipefail

INSTANCE_ID=""
REGION="us-east-1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    i-*)      INSTANCE_ID="$1"; shift ;;
    *) echo "argumento desconhecido: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$INSTANCE_ID" ]] && {
  echo "informe o instance-id:"
  echo "  cd terraform/07-ec2-migrator && terraform output instance_id"
  exit 1
}

echo "==> Disparando /usr/local/bin/migrate.sh em tmux na $INSTANCE_ID"

CMD_ID=$(aws ssm send-command \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "EFS -> S3 via POSIX mount (rsync paralelo)" \
  --parameters 'commands=["sudo -u ec2-user tmux new-session -d -s mig /usr/local/bin/migrate.sh && echo started"]' \
  --query "Command.CommandId" --output text)

echo "CommandId: $CMD_ID"
echo
echo "Acompanhe o progresso em tempo real:"
echo "  aws ssm start-session --target $INSTANCE_ID --region $REGION"
echo "  # dentro da EC2:"
echo "  sudo tmux attach -t mig"
echo "  # ou:"
echo "  sudo tail -f /var/log/migrator/migrate.jsonl"
echo
echo "Ao final:"
echo "  - logs em CloudWatch log-group /bench/migrator"
echo "  - metricas host em CloudWatch namespace EfsS3Bench/Host"
echo "  - metricas de migracao em CloudWatch namespace EfsS3Bench"
echo "  - resultado JSON em s3://<bench-results-bucket>/results/migrator/"
