# Arquiteturas · EFS → S3 · 3 Fases

Diagramas em [Mermaid](https://mermaid.js.org/) — renderizam direto no GitHub,
VSCode (extensão Markdown Preview Mermaid) e em qualquer leitor Markdown
moderno.

## 1. Visão geral — jornada em 3 fases

```mermaid
flowchart LR
  subgraph F1["Fase 1 · ANTES"]
    direction TB
    ALB1[ALB] --> ECS1[ECS Fargate<br/>variant=efs]
    ECS1 --> EFS1[(EFS)]
    POP1[EC2 populator] --> EFS1
  end

  subgraph F2["Fase 2 · DURANTE"]
    direction LR
    EFS2[(EFS ro)] --> MIG[EC2 migrator] --> S3A[(S3 Files)]
  end

  subgraph F3["Fase 3 · DEPOIS"]
    direction TB
    ALB3[ALB] --> ECS3[ECS on EC2<br/>variant=s3]
    ECS3 --> S3B[(S3 Files)]
  end

  F1 -- migrate.sh --> F2
  F2 -- cutover --> F3

  OBS[[Observabilidade transversal<br/>CloudWatch · X-Ray · S3 Bench Results]]
  F1 -.-> OBS
  F2 -.-> OBS
  F3 -.-> OBS

  classDef phase fill:#FFF8E1,stroke:#EF6C00,color:#263238
  classDef obs   fill:#F3E5F5,stroke:#8E24AA,color:#263238
  class F1,F2,F3 phase
  class OBS obs
```

---

## 2. Fase 1 · ECS Fargate + EFS (ANTES)

```mermaid
flowchart LR
  USER([Usuários]) --> ALB[ALB · HTTP 80]

  subgraph VPC["VPC · us-east-1"]
    direction TB
    ALB --> ECS[ECS Fargate<br/>api + ADOT sidecar]
    ECS -- NFS + TLS + IAM --> EFS[(EFS<br/>access point /data)]
    ECS -.-> ECR[[ECR<br/>imagem da API]]
    ECS -.-> SSM[[SSM Parameter Store<br/>VPC · EFS · obs]]
  end

  subgraph OBS["Observabilidade"]
    direction TB
    CW[CloudWatch Logs + Metrics]
    XR[X-Ray]
    BENCH[(S3 Bench Results<br/>results/api/efs/)]
  end

  ECS -. awslogs .-> CW
  ECS -. EMF stdout .-> CW
  ECS -. OTLP via ADOT .-> XR
  ECS -. boto3 PutObject .-> BENCH

  classDef vpc fill:#FAFBFF,stroke:#1565C0
  classDef obs fill:#F3E5F5,stroke:#8E24AA
  class VPC vpc
  class OBS obs
```

---

## 3. Fase 1 · Populator (setup de dados)

```mermaid
flowchart LR
  OP([Operador<br/>SSM Session]) --> EP[[VPC Endpoints<br/>ssm · ssmmessages · ec2messages]]
  EP --> POP[EC2 Nitro c6in.2xlarge<br/>populate_efs.py]
  POP -- NFS 2049 · mount tls+iam --> EFS[(EFS · access point /data)]
  EFS --> DATA[[datasets/fiap-data/<br/>part-NNNNN.jsonl · ~100 GB<br/>manifest.json]]

  subgraph OBS["Observabilidade"]
    CW[CloudWatch<br/>/bench/populator]
    HOST[EfsS3Bench/Host<br/>cpu · mem · disk · net]
    METRICS[EfsS3Bench<br/>Populator*Metrics]
    BENCH[(S3 Bench Results<br/>results/populator/)]
  end

  POP -. logs JSON .-> CW
  POP -. CW Agent .-> HOST
  POP -. EMF stdout .-> METRICS
  POP -. boto3 final .-> BENCH

  classDef obs fill:#F3E5F5,stroke:#8E24AA
  class OBS obs
```

---

## 4. Fase 2 · Migrator (EFS → S3 via 2 mounts POSIX)

```mermaid
flowchart LR
  OP([Operador<br/>SSM]) --> MIG

  subgraph VPC["VPC · us-east-1"]
    direction LR
    EFS[(EFS origem<br/>mount /mnt/efs ro)] -- leitura --> MIG[EC2 migrator<br/>c6in.2xlarge]
    MIG -- escrita via FUSE --> S3[(S3 Files destino<br/>mount /mnt/s3)]
    S3 -. sem NAT .-> GW[[VPC Gateway Endpoint · S3]]

    MIG -.- NOTE["migrate.sh<br/>rsync -a --inplace<br/>xargs -P 4<br/>valida SRC/DST"]
  end

  subgraph OBS["Observabilidade"]
    LOG[CloudWatch<br/>/bench/migrator]
    MET[EfsS3Bench<br/>MigrateThroughputMBps<br/>MigrateBytes]
    HOST[EfsS3Bench/Host<br/>IOPS · NET · CPU]
    BENCH[(S3 Bench Results<br/>results/migrator/)]
  end

  MIG -. logs .-> LOG
  MIG -. EMF .-> MET
  MIG -. CW Agent .-> HOST
  MIG -. aws s3 cp final .-> BENCH

  classDef vpc fill:#FAFBFF,stroke:#1565C0
  classDef obs fill:#F3E5F5,stroke:#8E24AA
  classDef note fill:#FFFDE7,stroke:#F9A825
  class VPC vpc
  class OBS obs
  class NOTE note
```

---

## 5. Fase 3 · ECS EC2 + S3 via Mountpoint (DEPOIS)

```mermaid
flowchart LR
  USER([Usuários]) --> ALB[ALB · HTTP 80]

  subgraph VPC["VPC · us-east-1"]
    direction TB
    ALB -- dynamic port --> HOST[EC2 host<br/>ECS agent]
    HOST -- bridge net --> TASK[ECS task<br/>api + ADOT]
    TASK -- bind-mount /mnt/s3 → /mnt/efs --> S3[(S3 Files)]
    S3 -. sem NAT .-> GW[[VPC Gateway Endpoint]]
    HOST -.- SVC["systemd mount-s3.service<br/>--uid 1000 --allow-delete"]
    HOST -.-> ECR[[ECR · mesma imagem!]]
  end

  subgraph OBS["Observabilidade"]
    CW[CloudWatch Logs<br/>/ecs/s3-api]
    MET[EfsS3Bench<br/>Bench*ThroughputMBps<br/>FileOpLatencyMs]
    XR[X-Ray · variant=s3]
    BENCH[(S3 Bench Results<br/>results/api/s3/<br/>+ relatório HTML)]
  end

  TASK -. awslogs .-> CW
  TASK -. EMF .-> MET
  TASK -. OTLP via ADOT .-> XR
  TASK -. boto3 .-> BENCH

  classDef vpc fill:#E8F5E9,stroke:#2E7D32
  classDef obs fill:#F3E5F5,stroke:#8E24AA
  classDef note fill:#FFFDE7,stroke:#F9A825
  class VPC vpc
  class OBS obs
  class SVC note
```

---

## Legenda

- `[rect]` = serviço / componente AWS
- `[(cilindro)]` = storage (EFS, S3)
- `[[caixa dupla]]` = recurso de infraestrutura (ECR, endpoint, SSM, etc.)
- `([pastilha])` = ator externo (usuário, operador)
- `-->` = fluxo de dados principal (HTTP, NFS, POSIX)
- `-. pontilhado .->` = fluxo de observabilidade ou lateral

Cores:

- **Laranja** (`#FFF8E1`) — fase ANTES (EFS)
- **Verde** (`#E8F5E9`) — fase DEPOIS (S3)
- **Azul claro** (`#FAFBFF`) — VPC
- **Roxo claro** (`#F3E5F5`) — observabilidade
- **Amarelo claro** (`#FFFDE7`) — notas / callouts
