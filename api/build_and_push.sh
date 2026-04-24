#!/usr/bin/env bash
#
# Build da imagem Docker da API e push pro ECR criado pela stack 03-ecs.
#
# Uso:
#   ./build_and_push.sh [--region us-east-1] [--project efs-api-lab] [--tag latest]
#
set -euo pipefail

REGION="us-east-1"
PROJECT="efs-api-lab"
TAG="latest"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)  REGION="$2";  shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --tag)     TAG="$2";     shift 2 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${PROJECT}-api"

echo "==> Login no ECR"
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Build"
docker build --platform linux/amd64 -t "${PROJECT}-api:${TAG}" .

echo "==> Tag"
docker tag "${PROJECT}-api:${TAG}" "${REPO}:${TAG}"

echo "==> Push"
docker push "${REPO}:${TAG}"

echo
echo "Imagem disponivel em: ${REPO}:${TAG}"
