#!/usr/bin/env bash
#
# Le os outputs da stack 00-backend e escreve backend.hcl em todas as stacks
# filhas. Rode apos 'cd 00-backend && terraform apply'.
#
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

BUCKET=$(cd "$SCRIPT_DIR/00-backend" && terraform output -raw state_bucket)
TABLE=$(cd "$SCRIPT_DIR/00-backend" && terraform output -raw lock_table)
REGION=$(cd "$SCRIPT_DIR/00-backend" && terraform output -raw region)

for stack in 01-vpc 02-observability 03-efs 04-ecs 05-ec2-populator 06-s3files 07-ecs-s3 08-ec2-migrator; do
  cat > "$SCRIPT_DIR/$stack/backend.hcl" <<EOF
bucket         = "$BUCKET"
dynamodb_table = "$TABLE"
region         = "$REGION"
encrypt        = true
EOF
  echo "  escrito: $stack/backend.hcl"
done

echo
echo "Pronto. Agora inicialize cada stack com:"
echo "  cd <stack> && terraform init -backend-config=backend.hcl"
