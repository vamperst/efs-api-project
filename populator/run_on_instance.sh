#!/usr/bin/env bash
#
# Wrapper para enviar o populator para a EC2 e disparar via SSM Send-Command.
# Alternativa: conecte via 'aws ssm start-session' e rode manualmente.
#
# Uso:
#   ./run_on_instance.sh <instance-id> [--region us-east-1] [--target-gb 100] [--dataset fiap-data]
#
set -euo pipefail

INSTANCE_ID=""
REGION="us-east-1"
TARGET_GB="100"
DATASET="fiap-data"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)    REGION="$2";    shift 2 ;;
    --target-gb) TARGET_GB="$2"; shift 2 ;;
    --dataset)   DATASET="$2";   shift 2 ;;
    i-*)         INSTANCE_ID="$1"; shift ;;
    *) echo "argumento desconhecido: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$INSTANCE_ID" ]] && { echo "informe o instance-id (i-xxxx)"; exit 1; }

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# 1) Copia o script via S3 transient (SSM send-command nao transfere arquivos grandes)
#    Usamos 'aws ssm send-command' com o conteudo embutido em base64.
CONTENT_B64=$(base64 < "$SCRIPT_DIR/populate_efs.py" | tr -d '\n')

CMD=$(cat <<EOF
set -euxo pipefail
sudo dnf install -y python3-pip
sudo pip3 install Faker
echo "$CONTENT_B64" | base64 -d > /tmp/populate_efs.py
chmod +x /tmp/populate_efs.py
cd /mnt/efs
sudo -u ec2-user python3 /tmp/populate_efs.py --target-gb $TARGET_GB --dataset $DATASET --efs-root /mnt/efs 2>&1 | tee /tmp/populate.log
EOF
)

echo "==> Disparando populator na instancia $INSTANCE_ID"
CMD_ID=$(aws ssm send-command \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "populate EFS with $TARGET_GB GB" \
  --parameters "commands=[\"$(echo "$CMD" | sed 's/"/\\"/g' | tr '\n' ';')\"]" \
  --query "Command.CommandId" --output text)

echo "CommandId: $CMD_ID"
echo
echo "Acompanhe com:"
echo "  aws ssm list-command-invocations --command-id $CMD_ID --details --region $REGION"
echo "  aws ssm get-command-invocation --command-id $CMD_ID --instance-id $INSTANCE_ID --region $REGION"
echo
echo "Ou conecte via SSM e acompanhe /tmp/populate.log:"
echo "  aws ssm start-session --target $INSTANCE_ID --region $REGION"
echo "  tail -f /tmp/populate.log"
