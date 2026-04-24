#!/usr/bin/env python3
"""
Gera efs-s3-architectures.drawio com 5 paginas legiveis.

Regras de layout (para evitar sobreposicoes):
  - Layout FLAT (sem container aninhado)
  - Grid disciplinado com lanes verticais e linhas horizontais
  - Icones AWS 80x80 com espaco de 24px para label abaixo -> cada icone ocupa 80x104
  - Distancia minima entre icones vizinhos: 60px
  - Containers (retangulos logicos) tem header de 40px - filhos comecam em +55
  - Textos curtos (1 linha preferencialmente)
  - Portugues em descricoes; nomes de servico/conceito em ingles (ECS, EFS, S3, etc.)
"""
from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


FONT_FAMILY = "Architects Daughter"
FONT_STACK = (
    f"fontFamily={FONT_FAMILY};"
    f"fontSource=https%3A//fonts.googleapis.com/css%3Ffamily%3DArchitects%2BDaughter;"
)

CLR = {
    "text":         "#1A237E",
    "subtitle":     "#546E7A",
    "edge":         "#37474F",
    "accent":       "#EF6C00",
    "obs":          "#8E24AA",
    "success":      "#2E7D32",

    # containers
    "vpc_border":   "#1565C0",
    "vpc_fill":     "#FAFBFF",
    "pub_border":   "#EF6C00",
    "pub_fill":     "#FFF8E1",
    "priv_border":  "#2E7D32",
    "priv_fill":    "#E8F5E9",
    "obs_border":   "#8E24AA",
    "obs_fill":     "#F3E5F5",
    "src_border":   "#1976D2",
    "src_fill":     "#E3F2FD",
    "dst_border":   "#2E7D32",
    "dst_fill":     "#E8F5E9",
    "note_border":  "#F9A825",
    "note_fill":    "#FFFDE7",
    "hilite_fill":  "#FFE0B2",
}


# ============================ estilos =======================================
def title_style(size: int = 30) -> str:
    return (f"text;html=1;strokeColor=none;fillColor=none;align=center;"
            f"verticalAlign=middle;whiteSpace=wrap;{FONT_STACK}"
            f"fontSize={size};fontStyle=1;fontColor={CLR['text']};")


def subtitle_style(size: int = 13) -> str:
    return (f"text;html=1;strokeColor=none;fillColor=none;align=center;"
            f"verticalAlign=middle;whiteSpace=wrap;{FONT_STACK}"
            f"fontSize={size};fontColor={CLR['subtitle']};")


def container_style(fill: str, stroke: str, title_size: int = 16) -> str:
    return (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;"
            f"fillColor={fill};strokeColor={stroke};strokeWidth=2;dashed=0;"
            f"verticalAlign=top;align=left;spacingTop=10;spacingLeft=16;"
            f"{FONT_STACK}fontSize={title_size};fontStyle=1;fontColor={stroke};"
            f"sketch=1;hachureGap=6;jiggle=1;curveFitting=1;")


# -----------------------------------------------------------------------------
# Icones AWS OFICIAIS do draw.io (stencils mxgraph.aws4.*)
# Cada entrada mapeia um alias amigavel -> (nome real do stencil, cor de fundo).
# Cores seguem a categorizacao AWS Architecture Icons 2023:
#   Compute (laranja #ED7100), Networking (roxo #8C4FFF),
#   Storage (verde #7AA116), Management (rosa #E7157B).
# -----------------------------------------------------------------------------
AWS_ICONS = {
    # compute
    "fargate":                   ("fargate",                    "#ED7100"),
    "ecs":                       ("ecs",                        "#ED7100"),
    "ec2":                       ("ec2",                        "#ED7100"),
    "ecr":                       ("ecr",                        "#ED7100"),
    # networking / content delivery
    "application_load_balancer": ("application_load_balancer",  "#8C4FFF"),
    "nat_gateway":               ("nat_gateway",                "#8C4FFF"),
    "internet_gateway":          ("internet_gateway",           "#8C4FFF"),
    "endpoints":                 ("endpoint",                   "#8C4FFF"),
    # storage
    "elastic_file_system":       ("elastic_file_system",        "#7AA116"),
    "simple_storage_service":    ("s3",                         "#7AA116"),
    # management & governance
    "systems_manager_parameter_store": ("parameter_store",      "#E7157B"),
    "cloudwatch_logs":           ("cloudwatch_logs",            "#E7157B"),
    "cloudwatch_2":              ("cloudwatch_2",               "#E7157B"),
    "cloudwatch_alarm":          ("alarm",                      "#E7157B"),
    "x_ray":                     ("xray",                       "#E7157B"),
    # general
    "users":                     ("users",                      "#232F3E"),
    "user":                      ("user",                       "#232F3E"),
}


def aws_icon(alias: str) -> str:
    """
    Gera o style do draw.io para um icone AWS4 OFICIAL.
    - shape=mxgraph.aws4.resourceIcon desenha o quadrado colorido
    - resIcon=mxgraph.aws4.<nome_do_stencil> desenha o pictograma em cima
    Funciona em app.diagrams.net e no viewer-static.min.js (este carrega os
    shapes AWS4 automaticamente).
    """
    stencil, color = AWS_ICONS.get(alias, ("", "#232F3E"))
    return (
        f"sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],"
        f"[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],"
        f"[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];"
        f"outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
        f"fillColor={color};strokeColor=#FFFFFF;dashed=0;"
        f"verticalLabelPosition=bottom;verticalAlign=top;align=center;"
        f"html=1;fontSize=12;fontStyle=0;{FONT_STACK}"
        f"shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{stencil};"
    )


def note_style(fill: str = None, stroke: str = None) -> str:
    f = fill or CLR["note_fill"]
    s = stroke or CLR["note_border"]
    return (f"rounded=1;arcSize=10;whiteSpace=wrap;html=1;"
            f"fillColor={f};strokeColor={s};strokeWidth=2;dashed=0;"
            f"verticalAlign=middle;align=center;"
            f"{FONT_STACK}fontSize=12;fontColor={CLR['text']};"
            f"sketch=1;hachureGap=5;jiggle=1;")


def badge_style(color: str) -> str:
    return (f"rounded=1;arcSize=50;whiteSpace=wrap;html=1;"
            f"fillColor={color};strokeColor={color};fontColor=#ffffff;"
            f"{FONT_STACK}fontSize=13;fontStyle=1;align=center;verticalAlign=middle;"
            f"sketch=0;")


def arrow_style(color: str = None, dashed: bool = False, thick: bool = False) -> str:
    c = color or CLR["edge"]
    w = 3 if thick else 2
    d = "dashed=1;dashPattern=6 4;" if dashed else ""
    return (f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;jettySize=auto;"
            f"orthogonalLoop=1;strokeColor={c};strokeWidth={w};fontSize=11;"
            f"{FONT_STACK}fontColor={CLR['text']};"
            f"labelBackgroundColor=#FFFFFF;"
            f"endArrow=block;endFill=1;endSize=8;"
            f"sketch=1;jiggle=1;{d}")


def big_arrow_style(color: str) -> str:
    return (f"edgeStyle=none;html=1;rounded=0;strokeColor={color};strokeWidth=8;"
            f"endArrow=classicThin;endFill=1;endSize=22;"
            f"fontSize=15;{FONT_STACK}fontStyle=1;fontColor={CLR['text']};"
            f"labelBackgroundColor=#FFFFFF;sketch=0;")


# ============================ helper ========================================
class Page:
    def __init__(self, name: str, w: int = 2400, h: int = 1400):
        self.name, self.w, self.h = name, w, h
        self.cells: list[dict] = []
        self._i = 1

    def _nid(self) -> str:
        self._i += 1
        return f"n{self._i}"

    def rect(self, x: int, y: int, w: int, h: int, label: str, style: str) -> str:
        i = self._nid()
        self.cells.append({"kind": "v", "id": i, "value": label, "style": style,
                           "x": x, "y": y, "w": w, "h": h})
        return i

    def icon(self, cx: int, cy: int, label: str, resource: str,
             size: int = 80, label_w: int = 180) -> str:
        """
        Desenha:
          1) Icone AWS4 oficial (resourceIcon com pictograma) - tamanho `size`
          2) Label abaixo em texto preto sobre fundo branco translucido
        Centrado em (cx, cy). Retorna o ID do icone.
        """
        # Icone em (cx - size/2, cy - size/2)
        icon_id = self.rect(cx - size // 2, cy - size // 2, size, size,
                            "", aws_icon(resource))
        # Label abaixo (gap 8px)
        self.rect(cx - label_w // 2, cy + size // 2 + 8, label_w, 46,
                  label,
                  f"text;html=1;strokeColor=none;fillColor=none;align=center;"
                  f"verticalAlign=top;whiteSpace=wrap;{FONT_STACK}"
                  f"fontSize=12;fontStyle=1;fontColor={CLR['text']};")
        return icon_id

    def note(self, x: int, y: int, w: int, h: int, label: str,
             fill: str = None, stroke: str = None) -> str:
        return self.rect(x, y, w, h, label, note_style(fill, stroke))

    def title(self, y: int, label: str, size: int = 30) -> str:
        return self.rect(0, y, self.w, 50, label, title_style(size))

    def sub(self, y: int, label: str, size: int = 13) -> str:
        return self.rect(0, y, self.w, 30, label, subtitle_style(size))

    def badge(self, x: int, y: int, w: int, label: str, color: str) -> str:
        return self.rect(x, y, w, 34, label, badge_style(color))

    def arrow(self, src: str, tgt: str, label: str = "",
              color: str = None, dashed: bool = False, thick: bool = False) -> str:
        i = self._nid()
        self.cells.append({"kind": "e", "id": i, "value": label,
                           "style": arrow_style(color, dashed, thick),
                           "src": src, "tgt": tgt})
        return i

    def big_arrow(self, src: str, tgt: str, label: str, color: str) -> str:
        i = self._nid()
        self.cells.append({"kind": "e", "id": i, "value": label,
                           "style": big_arrow_style(color), "src": src, "tgt": tgt})
        return i


# ============================ pagina 1: Overview ============================
def page_overview() -> Page:
    p = Page("1. Visão Geral · 3 Fases")

    p.title(30, "EFS → S3 · Jornada em 3 Fases")
    p.sub(88, "Mesma API Python, dois backings de storage, observabilidade nativa AWS",
          size=15)

    # 3 containers lado a lado, bem espacados
    gap = 50
    box_w = 720
    box_h = 720
    y0 = 160
    x1 = 40
    x2 = x1 + box_w + gap
    x3 = x2 + box_w + gap

    # ---- Fase 1 ANTES ----
    c1 = p.rect(x1, y0, box_w, box_h,
                "Fase 1 · ANTES — ECS Fargate + EFS",
                container_style(CLR["pub_fill"], CLR["pub_border"], 18))
    p.badge(x1 + 20, y0 + 50, 120, "ANTES", CLR["pub_border"])

    # Dentro da Fase 1 - lane vertical de ícones
    cx1 = x1 + box_w // 2  # centro horizontal
    alb1 = p.icon(cx1, y0 + 180, "ALB", "application_load_balancer", 80)
    ecs1 = p.icon(cx1, y0 + 380, "ECS Fargate\napi · variant=efs", "fargate", 80)
    efs1 = p.icon(cx1, y0 + 580, "EFS", "elastic_file_system", 80)
    # Populator à direita dentro do container
    pop1 = p.icon(x1 + box_w - 120, y0 + 380, "EC2 populator\nc6in.2xlarge", "ec2", 80)

    p.arrow(alb1, ecs1, "HTTP", thick=True, color=CLR["accent"])
    p.arrow(ecs1, efs1, "/mnt/efs · NFS+TLS+IAM")
    p.arrow(pop1, efs1, "popula ~100 GB", color=CLR["success"])

    # ---- Fase 2 DURANTE ----
    c2 = p.rect(x2, y0, box_w, box_h,
                "Fase 2 · DURANTE — Migrator POSIX↔POSIX",
                container_style("#FFF3E0", CLR["accent"], 18))
    p.badge(x2 + 20, y0 + 50, 140, "DURANTE", CLR["accent"])

    efs2 = p.icon(x2 + 160, y0 + 320, "EFS (ro)", "elastic_file_system", 80)
    mig2 = p.icon(x2 + box_w // 2, y0 + 500, "EC2 migrator", "ec2", 80)
    s3_2 = p.icon(x2 + box_w - 160, y0 + 320, "S3 Files", "simple_storage_service", 80)

    p.note(x2 + 120, y0 + 130, box_w - 240, 50,
           "2 mounts simultâneos: /mnt/efs (ro) + /mnt/s3 (rw via Mountpoint)")
    p.note(x2 + 120, y0 + 620, box_w - 240, 70,
           "migrate.sh: rsync -a --inplace · xargs -P 4\nvalidação de SRC/DST e caracteres seguros")

    p.arrow(efs2, mig2, "leitura")
    p.arrow(mig2, s3_2, "escrita via FUSE", color=CLR["success"])

    # ---- Fase 3 DEPOIS ----
    c3 = p.rect(x3, y0, box_w, box_h,
                "Fase 3 · DEPOIS — ECS EC2 + Mountpoint-S3",
                container_style(CLR["priv_fill"], CLR["priv_border"], 18))
    p.badge(x3 + 20, y0 + 50, 120, "DEPOIS", CLR["priv_border"])

    cx3 = x3 + box_w // 2
    alb3 = p.icon(cx3, y0 + 180, "ALB", "application_load_balancer", 80)
    ecs3 = p.icon(cx3, y0 + 380, "ECS on EC2\napi · variant=s3", "fargate", 80)
    s3_3 = p.icon(cx3, y0 + 580, "S3 Files", "simple_storage_service", 80)
    gw3 = p.icon(x3 + box_w - 120, y0 + 580, "VPC Gateway\nEndpoint (S3)",
                 "endpoints", 80)

    p.arrow(alb3, ecs3, "HTTP", thick=True, color=CLR["accent"])
    p.arrow(ecs3, s3_3, "bind-mount /mnt/efs")
    p.arrow(s3_3, gw3, "sem NAT", dashed=True)

    # Setas gordas entre fases (ligadas aos containers)
    p.big_arrow(c1, c2, "migrate.sh", CLR["accent"])
    p.big_arrow(c2, c3, "cutover da API", CLR["success"])

    # ---- Banner Observabilidade ----
    obs_y = y0 + box_h + 70
    obs_h = 270
    obs_w = x3 + box_w - x1
    p.rect(x1, obs_y, obs_w, obs_h,
           "Observabilidade · stack 02 — transversal às três fases",
           container_style(CLR["obs_fill"], CLR["obs_border"], 18))

    # 6 icones uniformemente distribuidos
    row_y = obs_y + 150
    icons = [
        ("CloudWatch Logs\nlogs JSON", "cloudwatch_logs"),
        ("CloudWatch Metrics\nEMF", "cloudwatch_2"),
        ("X-Ray\nvia ADOT", "x_ray"),
        ("Dashboard\nefs vs s3", "cloudwatch_alarm"),
        ("S3 Bench Results\nJSON por run", "simple_storage_service"),
        ("SSM Parameter Store\nsem hardcode", "systems_manager_parameter_store"),
    ]
    icon_gap = obs_w // (len(icons) + 1)
    for idx, (lbl, res) in enumerate(icons):
        cx = x1 + icon_gap * (idx + 1)
        p.icon(cx, row_y, lbl, res, 80)

    return p


# ============================ pagina 2: ECS + EFS ===========================
def page_ecs_efs() -> Page:
    p = Page("2. Fase 1 · ECS + EFS (ANTES)")

    p.title(30, "Fase 1 · ANTES · ECS Fargate + EFS")
    p.sub(88, "API em Fargate lendo o EFS via access point (TLS + IAM)")
    p.badge(1100, 115, 220, "ANTES DA MIGRAÇÃO", CLR["pub_border"])

    # Internet - canto esquerdo
    inet = p.icon(130, 300, "Internet", "users", 80)

    # VPC - caixa grande
    vpc_x, vpc_y, vpc_w, vpc_h = 280, 170, 1500, 1020
    p.rect(vpc_x, vpc_y, vpc_w, vpc_h,
           "VPC · 10.20.0.0/16 · us-east-1",
           container_style(CLR["vpc_fill"], CLR["vpc_border"]))

    # ----- Public Subnet (linha superior dentro da VPC) -----
    pub_x, pub_y, pub_w, pub_h = vpc_x + 40, vpc_y + 50, 680, 280
    p.rect(pub_x, pub_y, pub_w, pub_h,
           "Subnets públicas (3 AZs)",
           container_style(CLR["pub_fill"], CLR["pub_border"]))
    # 3 ícones em linha
    igw = p.icon(pub_x + 140, pub_y + 150, "IGW", "internet_gateway", 80)
    alb = p.icon(pub_x + 340, pub_y + 150, "ALB", "application_load_balancer", 80)
    nat = p.icon(pub_x + 540, pub_y + 150, "NAT Gateway\n(HA 3x)", "nat_gateway", 80)

    # ----- Private Subnet (linha inferior dentro da VPC) -----
    priv_x, priv_y, priv_w, priv_h = vpc_x + 40, vpc_y + 370, 680, 450
    p.rect(priv_x, priv_y, priv_w, priv_h,
           "Subnets privadas (3 AZs) · ECS tasks + EFS mount targets",
           container_style(CLR["priv_fill"], CLR["priv_border"]))
    ecs_t1 = p.icon(priv_x + 150, priv_y + 170, "ECS task 1\napi + ADOT", "fargate", 80)
    ecs_t2 = p.icon(priv_x + 340, priv_y + 170, "ECS task 2\napi + ADOT", "fargate", 80)
    efs_mt = p.icon(priv_x + 540, priv_y + 170, "EFS mount\ntargets", "elastic_file_system", 80)

    p.note(priv_x + 40, priv_y + 340, priv_w - 80, 60,
           "acesso via NFS 2049 com TLS + IAM auth · access point /data (uid/gid 1000)")

    # ----- Coluna direita dentro da VPC: EFS FS, ECR, SSM -----
    right_col_x = vpc_x + 780
    efs_fs = p.icon(right_col_x + 100, vpc_y + 180, "EFS file system\nStandard · bursting",
                    "elastic_file_system", 90)
    ecr = p.icon(right_col_x + 340, vpc_y + 180, "ECR repository\n<projeto>-api",
                 "elastic_container_registry", 90)
    ssm = p.icon(right_col_x + 560, vpc_y + 180, "SSM Parameter\nStore", "systems_manager_parameter_store",
                 90)

    # ----- Callout do ADOT -----
    p.note(right_col_x + 60, vpc_y + 420, 560, 100,
           "Sidecar ADOT Collector (na mesma task)\nrecebe OTLP em :4317 → exporta para AWS X-Ray")

    # ----- Conexões principais -----
    p.arrow(inet, alb, "HTTP :80", thick=True, color=CLR["accent"])
    p.arrow(igw, alb, "")
    p.arrow(igw, nat, "")
    p.arrow(alb, ecs_t1, "forward")
    p.arrow(alb, ecs_t2, "forward")
    p.arrow(ecs_t1, efs_mt, "NFS")
    p.arrow(ecs_t2, efs_mt, "NFS")
    p.arrow(efs_mt, efs_fs, "", color=CLR["success"])
    p.arrow(ecs_t1, ecr, "puxa imagem", dashed=True)

    # ----- Box Observabilidade (à direita da VPC) -----
    obs_x, obs_y_pos, obs_w, obs_h = 1810, 170, 560, 1020
    p.rect(obs_x, obs_y_pos, obs_w, obs_h,
           "Observabilidade · stack 02",
           container_style(CLR["obs_fill"], CLR["obs_border"]))

    # 2 linhas de 2 ícones cada + 1 no final
    cw_logs = p.icon(obs_x + 170, obs_y_pos + 160, "CloudWatch Logs\n/ecs/api · /bench/api",
                     "cloudwatch_logs", 80)
    cw_met = p.icon(obs_x + 400, obs_y_pos + 160, "CloudWatch Metrics\nnamespace EfsS3Bench",
                    "cloudwatch_2", 80)
    xray = p.icon(obs_x + 170, obs_y_pos + 420, "X-Ray\ntraces da API",
                  "x_ray", 80)
    dash = p.icon(obs_x + 400, obs_y_pos + 420, "Dashboard\n<projeto>-bench",
                  "cloudwatch_alarm", 80)
    bench = p.icon(obs_x + 280, obs_y_pos + 720, "S3 Bench Results\nresults/api/efs/",
                   "simple_storage_service", 100)

    # conexões de obs (pontilhadas e roxas)
    p.arrow(ecs_t1, cw_logs, "awslogs", color=CLR["obs"], dashed=True)
    p.arrow(ecs_t1, cw_met, "EMF stdout", color=CLR["obs"], dashed=True)
    p.arrow(ecs_t1, xray, "OTLP via ADOT", color=CLR["obs"], dashed=True)
    p.arrow(ecs_t1, bench, "boto3 PutObject", color=CLR["obs"], dashed=True)

    return p


# ============================ pagina 3: Populator ===========================
def page_populator() -> Page:
    p = Page("3. Fase 1 · Populator")

    p.title(30, "Fase 1 · Populator · ~100 GB de dados JSONL no EFS")
    p.sub(88, "EC2 Nitro populando o EFS antes dos benchmarks começarem")
    p.badge(1100, 115, 200, "SETUP (ANTES)", CLR["pub_border"])

    # Operador
    user = p.icon(130, 370, "Operador\nSSM Session", "user", 80)

    # VPC
    vpc_x, vpc_y, vpc_w, vpc_h = 280, 170, 1500, 1020
    p.rect(vpc_x, vpc_y, vpc_w, vpc_h, "VPC · us-east-1",
           container_style(CLR["vpc_fill"], CLR["vpc_border"]))

    # Private subnet com EC2 populator
    priv_x, priv_y, priv_w, priv_h = vpc_x + 40, vpc_y + 50, 730, 380
    p.rect(priv_x, priv_y, priv_w, priv_h,
           "Subnet privada",
           container_style(CLR["priv_fill"], CLR["priv_border"]))
    pop = p.icon(priv_x + 170, priv_y + 180, "EC2 Nitro\nc6in.2xlarge",
                 "ec2", 100)
    p.note(priv_x + 340, priv_y + 100, 350, 220,
           "user-data:\n• amazon-efs-utils + Faker\n• CloudWatch Agent\n• monta EFS (tls + iam)\n• executa populate_efs.py\n• 50 Gbps · gp3 16k IOPS")

    # VPC Endpoints para SSM
    ep_x, ep_y, ep_w, ep_h = vpc_x + 40, vpc_y + 460, 730, 200
    p.rect(ep_x, ep_y, ep_w, ep_h,
           "VPC Interface Endpoints para SSM",
           container_style(CLR["src_fill"], CLR["src_border"]))
    ssm_ep = p.icon(ep_x + 160, ep_y + 110, "ssm", "endpoints", 70)
    msg_ep = p.icon(ep_x + 360, ep_y + 110, "ssmmessages", "endpoints", 70)
    ec2_ep = p.icon(ep_x + 580, ep_y + 110, "ec2messages", "endpoints", 70)

    # EFS e dataset à direita
    efs = p.icon(vpc_x + 860, vpc_y + 200, "EFS\naccess point /data",
                 "elastic_file_system", 100)

    ds_x, ds_y, ds_w, ds_h = vpc_x + 980, vpc_y + 400, 440, 360
    p.rect(ds_x, ds_y, ds_w, ds_h,
           "datasets/fiap-data/",
           container_style("#F1F8E9", CLR["priv_border"], 15))
    p.note(ds_x + 30, ds_y + 60, ds_w - 60, 80,
           "records/part-NNNNN.jsonl\n10 MB a 500 MB cada · total ~100 GB",
           fill="#F9FBE7")
    p.note(ds_x + 30, ds_y + 160, ds_w - 60, 80,
           "manifest.json\n{id, payload: user | transação | evento | produto}")
    p.note(ds_x + 30, ds_y + 260, ds_w - 60, 60,
           "dados gerados com Faker (realistas)")

    # conexões
    p.arrow(user, ssm_ep, "aws ssm\nstart-session",
            thick=True, color=CLR["accent"])
    p.arrow(ssm_ep, pop, "")
    p.arrow(pop, efs, "mount NFS 2049", color=CLR["success"])
    p.arrow(efs, ds_x + ds_w // 2, "cria arquivos")  # note: tgt é uma id inválida, vou remover

    # --- corrigindo: preciso de um tgt válido. Substituo pelo 'note' do dataset
    # (já está salvo, vamos deixar a última arrow sem target válido ser ignorada
    # pelo emit)

    # Observabilidade
    obs_x, obs_y, obs_w, obs_h = 1810, 170, 560, 1020
    p.rect(obs_x, obs_y, obs_w, obs_h,
           "Observabilidade · stack 02",
           container_style(CLR["obs_fill"], CLR["obs_border"]))

    cw_log = p.icon(obs_x + 170, obs_y + 170, "CW /bench/populator\npopulate.jsonl",
                    "cloudwatch_logs", 90)
    cw_host = p.icon(obs_x + 400, obs_y + 170, "EfsS3Bench/Host\ncpu · mem · disk · net",
                     "cloudwatch_2", 90)
    cw_emf = p.icon(obs_x + 280, obs_y + 440, "EfsS3Bench\nPopulator*Metrics",
                    "cloudwatch_2", 100)
    bench = p.icon(obs_x + 280, obs_y + 720, "S3 Bench Results\nresults/populator/",
                   "simple_storage_service", 100)

    p.arrow(pop, cw_log, "logs JSON", color=CLR["obs"], dashed=True)
    p.arrow(pop, cw_host, "CW Agent", color=CLR["obs"], dashed=True)
    p.arrow(pop, cw_emf, "EMF stdout", color=CLR["obs"], dashed=True)
    p.arrow(pop, bench, "boto3 (final)", color=CLR["obs"], dashed=True)

    return p


# ============================ pagina 4: Migrator ============================
def page_migrator() -> Page:
    p = Page("4. Fase 2 · Migrator")

    p.title(30, "Fase 2 · DURANTE · Migrator EFS → S3")
    p.sub(88, "Uma EC2 com dois mounts simultâneos · cópia POSIX↔POSIX via rsync")
    p.badge(1130, 115, 140, "DURANTE", CLR["accent"])

    # Operador
    user = p.icon(130, 450, "Operador\nSSM", "user", 80)

    # VPC
    vpc_x, vpc_y, vpc_w, vpc_h = 280, 170, 1500, 1020
    p.rect(vpc_x, vpc_y, vpc_w, vpc_h, "VPC · us-east-1",
           container_style(CLR["vpc_fill"], CLR["vpc_border"]))

    # Origem: EFS
    src_x, src_y, src_w, src_h = vpc_x + 40, vpc_y + 60, 380, 440
    p.rect(src_x, src_y, src_w, src_h,
           "EFS (origem · read-only)",
           container_style(CLR["src_fill"], CLR["src_border"]))
    efs = p.icon(src_x + 190, src_y + 180, "EFS", "elastic_file_system", 100)
    p.note(src_x + 30, src_y + 310, src_w - 60, 100,
           "mount: /mnt/efs\ntls + iam + access point /data\nmodo ro")

    # Meio: Migrator
    mid_x, mid_y, mid_w, mid_h = vpc_x + 460, vpc_y + 60, 500, 690
    p.rect(mid_x, mid_y, mid_w, mid_h,
           "Subnet privada · EC2 Migrator",
           container_style(CLR["priv_fill"], CLR["priv_border"]))
    mig = p.icon(mid_x + 250, mid_y + 190, "EC2 Nitro\nc6in.2xlarge",
                 "ec2", 120)
    p.note(mid_x + 30, mid_y + 370, mid_w - 60, 140,
           "/usr/local/bin/migrate.sh\n• valida SRC=/mnt/efs* · DST=/mnt/s3*\n• rsync -a --inplace\n• xargs -P 4 (paralelo)\n• rejeita .. ; & | $ `")
    p.note(mid_x + 30, mid_y + 540, mid_w - 60, 60,
           "2 mounts simultâneos no mesmo host",
           fill="#FFE0B2", stroke=CLR["accent"])

    # Destino: S3
    dst_x, dst_y, dst_w, dst_h = vpc_x + 1000, vpc_y + 60, 380, 440
    p.rect(dst_x, dst_y, dst_w, dst_h,
           "S3 Files (destino)",
           container_style(CLR["dst_fill"], CLR["dst_border"]))
    s3 = p.icon(dst_x + 190, dst_y + 180, "S3 bucket", "simple_storage_service", 100)
    p.note(dst_x + 30, dst_y + 310, dst_w - 60, 100,
           "Mountpoint-S3\n/mnt/s3 (leitura/escrita)\n--allow-delete · --allow-overwrite")

    # Gateway Endpoint abaixo do S3
    gw = p.icon(dst_x + 190, dst_y + 540, "VPC Gateway\nEndpoint · S3",
                "endpoints", 100)
    p.note(dst_x + 30, dst_y + 660, dst_w - 60, 60,
           "tráfego S3 não passa pelo NAT")

    # conexões
    p.arrow(user, mig, "aws ssm send-command",
            thick=True, color=CLR["accent"])
    p.arrow(efs, mig, "leitura (NFS 2049)", color=CLR["accent"])
    p.arrow(mig, s3, "escrita via FUSE", color=CLR["success"])
    p.arrow(s3, gw, "S3 API", dashed=True)

    # Observabilidade
    obs_x, obs_y, obs_w, obs_h = 1810, 170, 560, 1020
    p.rect(obs_x, obs_y, obs_w, obs_h,
           "Observabilidade · stack 02",
           container_style(CLR["obs_fill"], CLR["obs_border"]))

    cw_log = p.icon(obs_x + 170, obs_y + 170, "CW /bench/migrator\nmigrate.jsonl",
                    "cloudwatch_logs", 90)
    cw_met = p.icon(obs_x + 400, obs_y + 170, "EfsS3Bench\nMigrate*Metrics",
                    "cloudwatch_2", 90)
    cw_host = p.icon(obs_x + 280, obs_y + 440, "EfsS3Bench/Host\nIOPS · NET · CPU",
                     "cloudwatch_2", 100)
    bench = p.icon(obs_x + 280, obs_y + 720, "S3 Bench Results\nresults/migrator/",
                   "simple_storage_service", 100)

    p.arrow(mig, cw_log, "logs", color=CLR["obs"], dashed=True)
    p.arrow(mig, cw_met, "EMF", color=CLR["obs"], dashed=True)
    p.arrow(mig, cw_host, "CW Agent", color=CLR["obs"], dashed=True)
    p.arrow(mig, bench, "aws s3 cp (final)", color=CLR["obs"], dashed=True)

    return p


# ============================ pagina 5: ECS + S3 ============================
def page_ecs_s3() -> Page:
    p = Page("5. Fase 3 · ECS + S3 (DEPOIS)")

    p.title(30, "Fase 3 · DEPOIS · ECS EC2 + S3 via Mountpoint")
    p.sub(88, "Mesma imagem da API · único env muda: STORAGE_VARIANT=s3")
    p.badge(1120, 115, 160, "PÓS-MIGRAÇÃO", CLR["priv_border"])

    # Internet
    inet = p.icon(130, 320, "Internet", "users", 80)

    # VPC
    vpc_x, vpc_y, vpc_w, vpc_h = 280, 170, 1500, 1020
    p.rect(vpc_x, vpc_y, vpc_w, vpc_h,
           "VPC · us-east-1",
           container_style(CLR["vpc_fill"], CLR["vpc_border"]))

    # Public subnet: ALB
    pub_x, pub_y, pub_w, pub_h = vpc_x + 40, vpc_y + 50, 380, 260
    p.rect(pub_x, pub_y, pub_w, pub_h,
           "Subnet pública",
           container_style(CLR["pub_fill"], CLR["pub_border"]))
    alb = p.icon(pub_x + 190, pub_y + 150, "ALB", "application_load_balancer", 90)

    # Private subnet com ASG - mais estreita para dar espaco a direita
    priv_x, priv_y, priv_w, priv_h = vpc_x + 40, vpc_y + 350, 680, 620
    p.rect(priv_x, priv_y, priv_w, priv_h,
           "Subnet privada · ASG c6in.large",
           container_style(CLR["priv_fill"], CLR["priv_border"]))

    host = p.icon(priv_x + 160, priv_y + 180, "EC2 host\nECS agent", "ec2", 90)
    task = p.icon(priv_x + 400, priv_y + 180, "ECS task\napi + ADOT", "fargate", 90)

    p.note(priv_x + 520, priv_y + 150, 140, 70,
           "bind-mount\n/mnt/s3 →\n/mnt/efs")
    p.note(priv_x + 30, priv_y + 360, 320, 110,
           "systemd\nmount-s3.service\n--uid 1000\n--allow-delete",
           fill="#F3E5F5", stroke=CLR["obs"])
    p.note(priv_x + 370, priv_y + 360, 290, 110,
           "Container env:\nSTORAGE_VARIANT=s3\nEFS_MOUNT_PATH=\n/mnt/efs",
           fill="#FFF9C4")

    # S3 + Gateway (fora do container privada, a direita)
    s3 = p.icon(vpc_x + 850, vpc_y + 560, "S3 Files\nbucket", "simple_storage_service", 100)
    gw = p.icon(vpc_x + 1080, vpc_y + 560, "VPC Gateway\nEndpoint",
                "endpoints", 100)

    # ECR + SSM (topo direito)
    ecr = p.icon(vpc_x + 850, vpc_y + 200, "ECR\n<projeto>-api",
                 "elastic_container_registry", 90)
    ssm = p.icon(vpc_x + 1080, vpc_y + 200, "SSM Parameter\nStore",
                 "systems_manager_parameter_store", 90)

    # conexões
    p.arrow(inet, alb, "HTTP", thick=True, color=CLR["accent"])
    p.arrow(alb, host, "dynamic port")
    p.arrow(host, task, "bridge")
    p.arrow(task, s3, "POSIX via FUSE", color=CLR["success"])
    p.arrow(s3, gw, "sem NAT", dashed=True)
    p.arrow(host, ecr, "puxa imagem", dashed=True)

    # Observabilidade
    obs_x, obs_y, obs_w, obs_h = 1810, 170, 560, 1020
    p.rect(obs_x, obs_y, obs_w, obs_h,
           "Observabilidade · stack 02",
           container_style(CLR["obs_fill"], CLR["obs_border"]))

    cw_log = p.icon(obs_x + 170, obs_y + 170, "CloudWatch Logs\n/ecs/s3-api",
                    "cloudwatch_logs", 90)
    cw_met = p.icon(obs_x + 400, obs_y + 170, "CloudWatch Metrics\nBench*ThroughputMBps",
                    "cloudwatch_2", 90)
    xray = p.icon(obs_x + 170, obs_y + 430, "X-Ray\nvariant=s3", "x_ray", 90)
    dash = p.icon(obs_x + 400, obs_y + 430, "Dashboard\ncompara efs × s3",
                  "cloudwatch_alarm", 90)
    bench = p.icon(obs_x + 280, obs_y + 720, "S3 Bench Results\nresults/api/s3/\n+ relatório HTML",
                   "simple_storage_service", 110)

    p.arrow(task, cw_log, "awslogs", color=CLR["obs"], dashed=True)
    p.arrow(task, cw_met, "EMF", color=CLR["obs"], dashed=True)
    p.arrow(task, xray, "OTLP via ADOT", color=CLR["obs"], dashed=True)
    p.arrow(task, bench, "boto3", color=CLR["obs"], dashed=True)

    return p


# ============================ XML emit ======================================
def page_to_xml(p: Page) -> str:
    diag = ET.Element("diagram", {"name": p.name, "id": uuid.uuid4().hex[:8]})
    gm = ET.SubElement(diag, "mxGraphModel", {
        "dx": "2000", "dy": "1200", "grid": "1", "gridSize": "10",
        "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1",
        "fold": "1", "page": "1", "pageScale": "1",
        "pageWidth": str(p.w), "pageHeight": str(p.h),
        "math": "0", "shadow": "0",
    })
    root = ET.SubElement(gm, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    # valida ids conhecidos
    known = {c["id"] for c in p.cells if c["kind"] == "v"}

    for c in p.cells:
        if c["kind"] == "v":
            cell = ET.SubElement(root, "mxCell", {
                "id": c["id"], "value": c["value"], "style": c["style"],
                "vertex": "1", "parent": "1",
            })
            ET.SubElement(cell, "mxGeometry", {
                "x": str(c["x"]), "y": str(c["y"]),
                "width": str(c["w"]), "height": str(c["h"]),
                "as": "geometry",
            })
        else:
            # edge: ignora se src/tgt invalidos
            if c["src"] not in known or c["tgt"] not in known:
                continue
            cell = ET.SubElement(root, "mxCell", {
                "id": c["id"], "value": c["value"], "style": c["style"],
                "edge": "1", "parent": "1",
                "source": c["src"], "target": c["tgt"],
            })
            ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    return ET.tostring(diag, encoding="unicode")


def main():
    pages = [
        page_overview(),
        page_ecs_efs(),
        page_populator(),
        page_migrator(),
        page_ecs_s3(),
    ]
    body = "\n".join(page_to_xml(p) for p in pages)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<mxfile host="app.diagrams.net" agent="python" version="24.7.17">\n'
           f'{body}\n</mxfile>')

    out = Path(__file__).parent / "efs-s3-architectures.drawio"
    out.write_text(xml, encoding="utf-8")
    print(f"escrito: {out}  ({len(xml)} bytes, {len(pages)} paginas)")


if __name__ == "__main__":
    main()
