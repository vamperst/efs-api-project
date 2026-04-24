# Publica outputs da VPC no SSM Parameter Store.
# Convencao: /<project>/<env>/vpc/<key>
#
# As outras stacks leem esses parametros via data "aws_ssm_parameter" - sem
# reconstrucao de nomes, sem hardcode.

locals {
  ssm_prefix = "/${var.project}/${var.env}/vpc"
}

resource "aws_ssm_parameter" "vpc_id" {
  name  = "${local.ssm_prefix}/vpc_id"
  type  = "String"
  value = aws_vpc.this.id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "vpc_cidr" {
  name  = "${local.ssm_prefix}/vpc_cidr"
  type  = "String"
  value = aws_vpc.this.cidr_block
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "public_subnet_ids" {
  name        = "${local.ssm_prefix}/public_subnet_ids"
  type        = "StringList"
  value       = join(",", aws_subnet.public[*].id)
  description = "Subnet IDs publicos separados por virgula"
  tags        = local.common_tags
}

resource "aws_ssm_parameter" "private_subnet_ids" {
  name        = "${local.ssm_prefix}/private_subnet_ids"
  type        = "StringList"
  value       = join(",", aws_subnet.private[*].id)
  description = "Subnet IDs privados separados por virgula"
  tags        = local.common_tags
}

resource "aws_ssm_parameter" "azs" {
  name  = "${local.ssm_prefix}/azs"
  type  = "StringList"
  value = join(",", local.azs)
  tags  = local.common_tags
}
