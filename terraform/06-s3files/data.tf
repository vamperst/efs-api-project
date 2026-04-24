data "aws_caller_identity" "current" {}

# VPC via SSM
data "aws_ssm_parameter" "vpc_id" {
  name = "/${var.project}/${var.env}/vpc/vpc_id"
}

data "aws_vpc" "this" {
  id = data.aws_ssm_parameter.vpc_id.value
}

# Route tables privadas (para associar ao Gateway Endpoint de S3).
# Filtro por VPC + tag Tier=Private (definida pela stack 01).
data "aws_route_tables" "private" {
  vpc_id = data.aws_vpc.this.id

  filter {
    name   = "tag:Tier"
    values = ["Private"]
  }
}

locals {
  # Nome do bucket usa padrao determinista porque e a PRIMEIRA criacao -
  # nada pode ler antes dele existir. Depois de criado, publicamos no SSM.
  # O usuario pode sobrescrever via var.bucket_name.
  bucket = var.bucket_name != "" ? var.bucket_name : "${var.project}-files-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  common_tags = {
    env     = var.env
    project = var.project
  }
}
