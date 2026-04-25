# Parte 1 · Bootstrap · Backend + VPC + Observabilidade

Esse é o **primeiro dos blocos de deploy**. Ao final desta parte, você tem:

- **State remoto Terraform** funcionando (bucket S3 + lock DynamoDB)
- **VPC** com 3 AZs, NAT Gateways, IGW e Flow Logs
- **Observabilidade** pronta (bucket de resultados, log groups, IAM policies,
  dashboard CloudWatch)

Todas as stacks seguintes (EFS, ECS, S3, etc.) **consomem** SSM Parameters
publicados por essas três, então elas **precisam rodar nessa ordem**.

---

## 0 · Pré-requisitos

### Ferramentas locais

```bash
# Validar o que ja existe (nenhum erro = ok)
terraform -version | head -1
aws --version
docker info >/dev/null 2>&1 && echo "docker rodando"
checkov --version
jq --version
# git-secrets nao tem --version; basta confirmar o binario
command -v git-secrets && echo "git-secrets instalado"
```

Se faltar algo no macOS:

```bash
brew install terraform awscli docker jq checkov git-secrets
```

### Sessão AWS SSO

O projeto assume que você já tem um profile SSO em `~/.aws/config`. Faça login:

```bash
# Substitua <SEU_PROFILE> pelo nome do seu profile SSO
aws sso login --profile <SEU_PROFILE>

# Exporta no shell atual (cada nova aba precisa disso ou fonte do .env)
export AWS_PROFILE=<SEU_PROFILE>
export AWS_REGION=us-east-1

# Valida
aws sts get-caller-identity
```

### Hooks de segurança (uma vez)

Instala `git-secrets` com patterns extras do projeto. Sem isso, você pode
commitar sem querer ARN, account id, bucket name real, etc.

```bash
make install-hooks
make check-secrets   # confirma que o repo atual está limpo
```

### `.env` local (gitignored)

```bash
cp .env.example .env
# edite .env preenchendo AWS_PROFILE com seu profile real
```

Carregue no shell:

```bash
set -a; source .env; set +a
```

---

## 1 · Stack `00-backend` · State remoto S3 + DynamoDB

Única stack que **não** usa backend remoto — ela cria o backend! Por isso
tem state local (commit em `.gitignore`, NUNCA sobe para o repo).

### Deploy

```bash
cd terraform/00-backend

terraform init                 # state local
terraform plan                 # revise antes de aplicar
terraform apply -auto-approve
```

### Saídas esperadas

```bash
terraform output state_bucket    # <project>-tfstate-<account>-us-east-1
terraform output lock_table      # <project>-tfstate-lock
terraform output region          # us-east-1
```

Guarde o `terraform.tfstate` local em lugar seguro (ou use um bucket privado
pessoal para backup). Ele é a única fonte da verdade para essa stack.

### Gerar os `backend.hcl` de todas as outras stacks

Esse script lê os outputs acima e escreve `backend.hcl` dentro de cada stack
(gitignored) para que `terraform init` saiba onde guardar o state remoto:

```bash
cd ..                   # volta para terraform/
./write-backend-hcl.sh
```

Agora `01-vpc/backend.hcl`, `02-observability/backend.hcl`, etc. existem
localmente mas **nunca serão commitados** (estão em `.gitignore`).

### Validação

```bash
# no AWS Console: S3 -> deve existir 1 bucket novo com versioning + SSE
# DynamoDB -> tabela <project>-tfstate-lock (PAY_PER_REQUEST, PITR ativo)
aws s3 ls | grep tfstate
aws dynamodb list-tables | grep tfstate-lock
```

---

## 2 · Stack `01-vpc` · VPC + Subnets + NAT + Flow Logs

### Deploy

```bash
cd 01-vpc
terraform init -backend-config=backend.hcl    # usa backend remoto S3+DynamoDB
terraform plan
terraform apply -auto-approve
```

**Demora ~3-5 min** (NAT Gateways são o gargalo — cada um leva ~2 min).

### O que foi criado

| Recurso | Quantidade | Observação |
|---|---|---|
| VPC `10.20.0.0/16` | 1 | DNS hostnames + DNS support habilitados |
| Subnets públicas (3 AZs) | 3 | `10.20.X.0/22` |
| Subnets privadas (3 AZs) | 3 | `10.20.X.0/22` |
| Internet Gateway | 1 | Anexado na VPC |
| NAT Gateway | **3** (1 por AZ) | HA — cada AZ tem saída própria |
| Elastic IPs | 3 | Associados aos NATs |
| Route Tables | 4 | 1 pública + 3 privadas |
| VPC Flow Logs | 1 | destino `/vpc/<project>-flow-logs` |
| Default SG travado | sim | nega todo tráfego (boa prática) |

### Custos que começam a rodar

- **3 NAT Gateways** ≈ **$100/mês** (maior custo da infra)
- **3 EIPs** attached (grátis enquanto attached)
- VPC Flow Logs → CloudWatch: centavos para um lab

> **Dica lab**: se quiser economizar, edite `01-vpc/main.tf`, altere os
> `count = length(local.azs)` dos NAT Gateways para `count = 1` e reaponte
> todas as route tables privadas para ele. Cai para ~$33/mês mas perde HA.

### SSM Parameters publicados

```bash
aws ssm get-parameters-by-path \
  --path "/efs-api-lab/dev/vpc/" \
  --query 'Parameters[].Name' --output table
```

Você deve ver:

- `/efs-api-lab/dev/vpc/vpc_id`
- `/efs-api-lab/dev/vpc/vpc_cidr`
- `/efs-api-lab/dev/vpc/public_subnet_ids`
- `/efs-api-lab/dev/vpc/private_subnet_ids`
- `/efs-api-lab/dev/vpc/azs`

### Saídas úteis

```bash
terraform output vpc_id
terraform output private_subnet_ids
```

---

## 3 · Stack `02-observability` · Results bucket + Log groups + IAM + Dashboard

Essa stack **precisa existir** antes de qualquer compute, porque ela cria as
IAM managed policies (`bench-results-write`, `cw-emf-metrics`, `xray-write`)
que as tasks ECS, populator e migrator vão usar.

### Deploy

```bash
cd ../02-observability
terraform init -backend-config=backend.hcl
terraform plan
terraform apply -auto-approve
```

Bem rápido (~30s), não cria recursos caros.

### O que foi criado

- **S3 bucket** `<project>-bench-results-<account>-us-east-1` (versionado, SSE)
- **Log groups** `/bench/api`, `/bench/populator`, `/bench/migrator`, `/otel/<project>`
- **IAM policies managed** (reutilizadas pelas próximas stacks)
- **CloudWatch Dashboard** `<project>-bench` com 4 widgets (throughput, latência, etc.)

### SSM Parameters publicados

```bash
aws ssm get-parameters-by-path \
  --path "/efs-api-lab/dev/obs/" \
  --query 'Parameters[].Name' --output table
```

Você verá `results_bucket`, `metric_namespace`, `log_group_*`,
`policy_bench_results_arn`, `policy_cw_emf_arn`, `policy_xray_arn`,
`dashboard_name`.

### Abra o dashboard (ainda vazio)

```bash
terraform output dashboard_url
# abra no navegador - vira os widgets vazios (metricas aparecem quando as
# outras stacks começarem a emitir)
```

---

## 4 · Validação final da Parte 1

Rode os checks locais para garantir que nada quebrou:

```bash
cd ../..                    # volta para efs-api-project/
make check                  # fmt + refs + checkov
```

Esperado:

```text
==> 9 stacks | 28 SSM produzidos | 50 consumos
ok - sem referencias quebradas
Passed checks: 229, Failed checks: 0, Skipped checks: 0
```

Confira que os SSM params estão publicados na conta:

```bash
aws ssm describe-parameters \
  --parameter-filters "Key=Name,Option=BeginsWith,Values=/efs-api-lab/dev/" \
  --query 'length(Parameters)'
# esperado: >= 16 (5 da vpc + 11 da obs)
```

---

## 5 · Troubleshooting

### `Error: NoCredentialProviders` em qualquer stack

Sua sessão SSO expirou (padrão 8h):

```bash
aws sso login --profile <SEU_PROFILE>
export AWS_PROFILE=<SEU_PROFILE>
```

### `terraform init` reclama de backend

Faltou gerar o `backend.hcl` após a stack 00:

```bash
cd terraform
./write-backend-hcl.sh
# e depois no diretório da stack:
rm -rf .terraform && terraform init -backend-config=backend.hcl
```

### `checkov` achou algo

Confira se é regra nova ou bug. Todos os achados passados estão justificados
no `tests/.checkov.yml`. Se for legítimo, arrume o código antes de seguir.

### Pre-commit bloqueando arquivo novo

O `git-secrets` ou o hook do projeto pegou algo. Veja o que foi detectado:

```bash
git secrets --scan --cached
```

Se for **falso positivo**, adicione um padrão à `--allowed` em
`hooks/setup-git-secrets.sh` e rode `make install-hooks` de novo.

---

## 6 · Próxima parte

Com a Parte 1 pronta, a Parte 2 (em breve) cobre:

- Stack `03-efs` — EFS + Access Point + ECR repo
- Stack `05-ec2-populator` — EC2 Nitro que popula ~100 GB no EFS
- Stack `04-ecs` — ALB + ECS Fargate com a API EFS-backed + ADOT sidecar
- Build + push da imagem Docker da API
- Primeiro `curl` no `/health` e `/bench/write`

### Custos acumulados após a Parte 1

| Item | $/mês estimado |
|---|---|
| 3 NAT Gateways | ~$100 |
| VPC Flow Logs (CloudWatch) | ~$0.50 |
| S3 buckets (state + bench results, vazios) | ~$0 |
| DynamoDB lock table (on-demand, pouco uso) | ~$0 |
| **Total Parte 1** | **~$100/mês** |

---

## 7 · Destruir a Parte 1 (se quiser desfazer)

**Ordem reversa** — NUNCA destrua a 00 antes das outras, senão você perde
o state remoto das seguintes.

```bash
cd terraform/02-observability && terraform destroy
cd ../01-vpc                   && terraform destroy    # ~3 min (espera NATs)
cd ../00-backend               && terraform destroy    # por último
```

Depois apague os arquivos locais gerados:

```bash
rm terraform/*/backend.hcl
rm -rf terraform/*/.terraform terraform/*/.terraform.lock.hcl
```
