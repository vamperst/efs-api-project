#!/usr/bin/env bash
#
# Configura git-secrets no repo local.
# - Instala os hooks (pre-commit, commit-msg, prepare-commit-msg)
# - Registra os providers padrao AWS (AKIA/ASIA keys etc)
# - Adiciona padroes EXTRAS deste projeto (SSO URLs, account id, profile)
# - Adiciona allowed-patterns para os placeholders que a gente usa nos exemplos
#
# Idempotente: rode quantas vezes quiser.
#
# Uso:  ./hooks/setup-git-secrets.sh
# Requer: brew install git-secrets  (ou equivalente)

set -euo pipefail

if ! command -v git-secrets >/dev/null 2>&1; then
  echo "ERRO: git-secrets nao encontrado."
  echo "instale: brew install git-secrets  (macOS)"
  echo "         apt install git-secrets   (Debian/Ubuntu, se disponivel)"
  echo "ou: https://github.com/awslabs/git-secrets"
  exit 1
fi

cd "$(git rev-parse --show-toplevel)"

echo "==> instalando hooks (pre-commit, commit-msg, prepare-commit-msg)"
git secrets --install -f

echo "==> registrando providers AWS padrao (AKIA, ASIA, account id patterns)"
git secrets --register-aws

# ============================================================================
# PADROES EXTRAS — bloqueia coisas deste projeto
# ============================================================================

# SSO start URLs reais (org-xxxx.awsapps.com/start)
git secrets --add 'https?://[a-z0-9-]+\.awsapps\.com/start' || true

# start URLs d-xxxxxxxxxx (IAM Identity Center instance)
git secrets --add 'https?://d-[a-z0-9]{10}\.awsapps\.com' || true

# Keys privadas
git secrets --add -- '-----BEGIN (RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY-----' || true

# GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_)
git secrets --add 'gh[pousr]_[A-Za-z0-9_]{20,}' || true

# Slack tokens
git secrets --add 'xox[abprs]-[0-9A-Za-z-]{10,}' || true

# ============================================================================
# IDENTIDADE / RECURSOS UNICOS — regra do projeto: NADA pessoal no repo
# ============================================================================

# ARNs completos com account id (12 digitos consecutivos)
git secrets --add 'arn:aws(-[a-z]+)?:[a-zA-Z0-9-]+:[a-z0-9-]*:[0-9]{12}:' || true

# ECR registry URL (sempre tem account id)
git secrets --add '[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com' || true

# ELB/ALB DNS (internal-<nome>-<id>.<region>.elb.amazonaws.com)
git secrets --add '[a-z0-9.-]+\.elb\.amazonaws\.com' || true

# S3 bucket direto pelo dominio (real ou endpoint)
git secrets --add '[a-z0-9][a-z0-9.-]+\.s3[.-][a-z0-9-]+\.amazonaws\.com' || true

# IDs de recursos AWS - usa ancoras baseadas em contexto (=, espaco, aspas, inicio linha)
# NAO usa \b porque BSD grep nao suporta
git secrets --add '(^|[^a-zA-Z0-9])fs-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])vpc-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])subnet-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])sg-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])eni-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])i-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])ami-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])vol-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])snap-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])igw-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])nat-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])rtb-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true
git secrets --add '(^|[^a-zA-Z0-9])vpce-[0-9a-f]{8,17}([^a-zA-Z0-9]|$)' || true

# Hosted zone IDs (Z + caracteres uppercase/digit)
git secrets --add '(^|[^A-Z0-9])Z[A-Z0-9]{9,20}([^A-Z0-9]|$)' || true

# nome do profile pessoal (vamos descobrir do ~/.aws/config)
if [ -f "$HOME/.aws/config" ]; then
  # extrai todos os nomes de profile SSO que aparecem no config local
  # e bloqueia cada um (evita esquecer no .env ou em scripts)
  grep -E '^\[profile ' "$HOME/.aws/config" 2>/dev/null | \
    sed 's/\[profile //;s/\]//' | while read -r p; do
      if [ -n "$p" ] && [ "$p" != "default" ]; then
        git secrets --add "$p" || true
      fi
    done
  # SSO session names tambem
  grep -E '^\[sso-session ' "$HOME/.aws/config" 2>/dev/null | \
    sed 's/\[sso-session //;s/\]//' | while read -r s; do
      if [ -n "$s" ]; then
        git secrets --add "$s" || true
      fi
    done
fi

# Account ID ATIVO (via STS) - so bloqueia se o usuario estiver logado
if command -v aws >/dev/null 2>&1; then
  acc=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
  if [ -n "$acc" ] && [ "$acc" != "None" ]; then
    git secrets --add "$acc" || true
    echo "    bloqueando account $acc"
  fi
fi

# ============================================================================
# ALLOWED PATTERNS — placeholders aceitos nos exemplos do repo
# ============================================================================
git secrets --add --allowed '<SEU_PROFILE_AQUI>'           || true
git secrets --add --allowed '<your-profile>'                || true
git secrets --add --allowed '<sua-org>'                     || true
git secrets --add --allowed '<your-org>'                    || true
git secrets --add --allowed '<account>'                     || true
git secrets --add --allowed '<account_id>'                  || true
git secrets --add --allowed '\$\{account_id\}'              || true
git secrets --add --allowed 'data\.aws_caller_identity'     || true
git secrets --add --allowed '123456789012'                  || true
git secrets --add --allowed 'EXAMPLE[A-Z0-9]+'              || true
# placeholder canonico AWS docs
git secrets --add --allowed '111122223333'                  || true

# evita falso positivo em docs/comentarios
git secrets --add --allowed 'placeholder'                   || true

# placeholders de ID/hash em exemplos (xxxx, xxxxxxxxx, etc)
git secrets --add --allowed '(i|fs|vpc|sg|subnet|eni|ami|vol|snap|igw|nat|rtb|vpce)-x+' || true
git secrets --add --allowed '\-x{3,}\.'                     || true   # elb-xxxx. / s3-xxxx.
git secrets --add --allowed 'x{5,}'                         || true   # xxxxxx... em dominios exemplo

# Os proprios arquivos que CONTEM os regexes de deteccao (scanner + setup)
# geram falsos positivos - whitelist por prefixo de path
git secrets --add --allowed 'hooks/setup-git-secrets\.sh'   || true
git secrets --add --allowed 'tests/check_secrets\.py'       || true
git secrets --add --allowed 'tests/check_refs\.py'          || true
# o proprio .gitallowed list pode conter qualquer coisa
git secrets --add --allowed '\.gitallowed'                  || true

echo
echo "==> listagem de padroes bloqueados"
git secrets --list 2>&1 | sed 's/^/  /' | head -40
echo
echo "ok · git-secrets configurado. Proximos commits serao validados."
echo
echo "para escanear o repo inteiro agora:"
echo "  git secrets --scan"
echo "para escanear a historia toda:"
echo "  git secrets --scan-history"
