#!/usr/bin/env bash
#
# Pre-flight check: valida se o ambiente esta pronto para rodar cada stack
# SEM fazer apply.
#
# O que checa:
#   1) Credenciais AWS + regiao
#   2) Pacotes instalados (terraform, aws, docker, python3, checkov, tflint)
#   3) Em cada stack: terraform fmt, terraform init (backend=false) + validate
#   4) "Contrato SSM": cada stack consumidora so deve referenciar chaves que
#      alguma stack produtora realmente cria.
#   5) Se voce passar --live, checa no SSM da sua conta se as chaves ja
#      existem - util antes de aplicar 03/04/05 etc.
#
# Uso:
#   ./tests/preflight.sh                # checa codigo, nao fala com AWS
#   ./tests/preflight.sh --live         # tambem verifica SSM params na conta
#   ./tests/preflight.sh --stack 04-ecs # checa so uma stack
#
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TF_DIR="$SCRIPT_DIR/../terraform"
LIVE=false
ONLY_STACK=""
FAIL=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}ok${NC}    %s\n" "$*"; }
warn() { printf "${YELLOW}warn${NC}  %s\n" "$*"; }
fail() { printf "${RED}fail${NC}  %s\n" "$*"; FAIL=$((FAIL+1)); }
info() { printf "${BLUE}info${NC}  %s\n" "$*"; }
head() { printf "\n\033[1m%s\033[0m\n" "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live) LIVE=true; shift ;;
    --stack) ONLY_STACK="$2"; shift 2 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) fail "argumento desconhecido: $1"; exit 2 ;;
  esac
done

ALL_STACKS=(00-backend 01-vpc 02-observability 03-efs 04-ecs 05-ec2-populator 06-s3files 07-ecs-s3 08-ec2-migrator)
STACKS=("${ALL_STACKS[@]}")
if [[ -n "$ONLY_STACK" ]]; then STACKS=("$ONLY_STACK"); fi

# ---------------------------- 1. ambiente -----------------------------------
head "1. ambiente"
for cmd in terraform aws jq python3; do
  if command -v "$cmd" >/dev/null; then ok "$cmd: $(command -v $cmd)"; else fail "$cmd nao encontrado"; fi
done
for cmd in tflint checkov; do
  if command -v "$cmd" >/dev/null; then ok "$cmd: $(command -v $cmd)"; else warn "$cmd nao encontrado (opcional)"; fi
done

if [[ "$LIVE" == "true" ]]; then
  ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
  REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")
  if [[ -z "$ACCOUNT" ]]; then
    fail "credenciais AWS nao configuradas"
  else
    ok "AWS account=$ACCOUNT region=$REGION"
  fi
fi

# ---------------------------- 2. fmt + validate -----------------------------
head "2. terraform fmt + validate por stack"
for s in "${STACKS[@]}"; do
  d="$TF_DIR/$s"
  [[ -d "$d" ]] || { warn "stack nao encontrada: $s"; continue; }
  pushd "$d" >/dev/null

  if terraform fmt -check -recursive >/dev/null 2>&1; then
    ok "$s: fmt"
  else
    fail "$s: fmt (rode 'terraform fmt -recursive')"
  fi

  rm -rf .terraform .terraform.lock.hcl 2>/dev/null
  if timeout 60 terraform init -backend=false -input=false -no-color >/tmp/tf-init.log 2>&1; then
    if timeout 30 terraform validate -no-color >/tmp/tf-validate.log 2>&1; then
      ok "$s: validate"
    else
      fail "$s: validate - veja /tmp/tf-validate.log"
      tail -5 /tmp/tf-validate.log | sed 's/^/       /'
    fi
  else
    warn "$s: init falhou (sem rede?) - pulando validate"
  fi
  popd >/dev/null
done

# ---------------------------- 3. contrato SSM -------------------------------
# Cada stack que consome SSM so deve referenciar prefixos/keys que alguma
# stack produtora de fato cria. Extraimos:
#   - PRODUCED: chaves em "aws_ssm_parameter" "..." {}
#   - CONSUMED: nomes em data "aws_ssm_parameter" "..." {}
head "3. contrato SSM (produced vs consumed)"

python3 - <<'PY'
import os, re, sys, pathlib, json

root = pathlib.Path(__file__).resolve().parents[1] / "terraform" if False else pathlib.Path(os.environ.get("TF_DIR", "terraform"))
# na verdade pegamos de argv:
import sys
tf_dir = pathlib.Path(sys.argv[1])

produced = {}  # stack -> set(keys)
consumed = {}  # stack -> set(keys)

re_producer = re.compile(r'resource\s+"aws_ssm_parameter"\s+"[^"]+"\s*\{[^}]*?name\s*=\s*"([^"]+)"', re.S)
re_consumer = re.compile(r'data\s+"aws_ssm_parameter"\s+"[^"]+"\s*\{[^}]*?name\s*=\s*"([^"]+)"', re.S)

for stack in sorted(tf_dir.iterdir()):
    if not stack.is_dir(): continue
    p = set(); c = set()
    for tf in stack.glob("*.tf"):
        txt = tf.read_text()
        p.update(re_producer.findall(txt))
        c.update(re_consumer.findall(txt))
    produced[stack.name] = p
    consumed[stack.name] = c

# Normaliza keys - substitui interpolacoes simples por coringas para comparar
def norm(k):
    # interpolacoes ${var.project} e ${var.env} viram <P> e <E>
    k = re.sub(r'\$\{var\.project\}', '<P>', k)
    k = re.sub(r'\$\{var\.env\}', '<E>', k)
    return k

all_produced = set()
for s, ks in produced.items():
    all_produced |= {norm(k) for k in ks}

# AWS-managed SSM params (nao precisam ser produced)
aws_managed_prefixes = ["/aws/"]

missing = {}
for stack, ks in consumed.items():
    for k in ks:
        nk = norm(k)
        if any(nk.startswith(p) for p in aws_managed_prefixes):
            continue
        if nk not in all_produced:
            missing.setdefault(stack, set()).add(nk)

print("\nproduced:")
for s in sorted(produced):
    if produced[s]:
        print(f"  {s}: {len(produced[s])} params")

print("\nconsumed:")
for s in sorted(consumed):
    if consumed[s]:
        print(f"  {s}: {len(consumed[s])} params")

if missing:
    print("\nERRO: chaves consumidas que ninguem produz:")
    for s, ks in missing.items():
        for k in sorted(ks):
            print(f"  {s}  <- {k}")
    sys.exit(1)
else:
    print("\nok - todas as chaves SSM consumidas tem um producer")
PY
if [[ $? -ne 0 ]]; then
  fail "contrato SSM quebrado"
fi

# ---------------------------- 4. live SSM check -----------------------------
if [[ "$LIVE" == "true" ]]; then
  head "4. SSM params presentes na conta (live check)"
  # Descobre o prefixo lendo um var do 01-vpc
  PROJECT=$(cd "$TF_DIR/01-vpc" && terraform console <<< "var.project" 2>/dev/null | tr -d '"' || echo "efs-api-lab")
  ENV=$(cd "$TF_DIR/01-vpc" && terraform console <<< "var.env" 2>/dev/null | tr -d '"' || echo "dev")
  info "listando /$PROJECT/$ENV/* ..."
  COUNT=$(aws ssm describe-parameters --parameter-filters "Key=Name,Option=BeginsWith,Values=/$PROJECT/$ENV/" --query 'length(Parameters)' --output text 2>/dev/null || echo 0)
  if [[ "$COUNT" -gt 0 ]]; then
    ok "$COUNT params publicados"
  else
    warn "nenhum param publicado ainda (normal antes do primeiro apply)"
  fi
fi

# ---------------------------- resumo ----------------------------------------
head "resumo"
if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${RED}$FAIL erro(s)${NC}"
  exit 1
fi
echo -e "${GREEN}tudo OK${NC}"
