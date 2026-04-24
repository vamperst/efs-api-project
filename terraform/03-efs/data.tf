# Le VPC e subnets do SSM (publicados pela stack 01).
# Usamos aws_vpc/aws_subnet para ter os atributos (cidr_block etc) alem do id.

data "aws_ssm_parameter" "vpc_id" {
  name = "/${var.project}/${var.env}/vpc/vpc_id"
}

data "aws_ssm_parameter" "private_subnet_ids" {
  name = "/${var.project}/${var.env}/vpc/private_subnet_ids"
}

data "aws_vpc" "this" {
  id = data.aws_ssm_parameter.vpc_id.value
}

locals {
  private_subnet_ids = split(",", data.aws_ssm_parameter.private_subnet_ids.value)
  common_tags = {
    env     = var.env
    project = var.project
  }
}
