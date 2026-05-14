# Deploy — tutoriais por parte

Cada tutorial cobre um bloco lógico de deploy. Siga a ordem.

| # | Parte | Stacks | Custo $/mês | Tempo |
|---|---|---|---|---|
| 1 | [Bootstrap · VPC · Observabilidade](01-bootstrap.md) | 00 · 01 · 02 | ~$100 (NATs) | ~10 min |
| 2 | *(em breve)* EFS + Populator + ECS Fargate | 03 · 05 · 04 | +~$45 | ~90 min (populate 100 GB) |
| 3 | *(em breve)* S3 Files + Migrator + ECS EC2 | 06 · 08 · 07 | +~$75 | ~30 min |
| 4 | *(em breve)* Benchmarks + Relatório HTML | — | +~$0 | ~40 min |

## Fluxo rápido (sem explicação)

```bash
# 1) login
aws sso login --profile <SEU_PROFILE>
export AWS_PROFILE=<SEU_PROFILE>

# 2) hooks
make install-hooks

# 3) bootstrap
cd terraform/00-backend && terraform init && terraform apply -auto-approve
cd ..
./write-backend-hcl.sh

# 4) vpc + obs
for s in 01-vpc 02-observability; do
  cd "$s"
  terraform init -backend-config=backend.hcl
  terraform apply -auto-approve
  cd ..
done

# 5) validar
cd ..
make check
```
