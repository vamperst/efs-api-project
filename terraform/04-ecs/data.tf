# Tudo lido do SSM Parameter Store - nenhum nome reconstruido.

# VPC + subnets
data "aws_ssm_parameter" "vpc_id" {
  name = "/${var.project}/${var.env}/vpc/vpc_id"
}

data "aws_ssm_parameter" "public_subnet_ids" {
  name = "/${var.project}/${var.env}/vpc/public_subnet_ids"
}

data "aws_ssm_parameter" "private_subnet_ids" {
  name = "/${var.project}/${var.env}/vpc/private_subnet_ids"
}

# EFS
data "aws_ssm_parameter" "efs_file_system_id" {
  name = "/${var.project}/${var.env}/efs/file_system_id"
}

data "aws_ssm_parameter" "efs_file_system_arn" {
  name = "/${var.project}/${var.env}/efs/file_system_arn"
}

data "aws_ssm_parameter" "efs_access_point_id" {
  name = "/${var.project}/${var.env}/efs/access_point_id"
}

data "aws_ssm_parameter" "efs_security_group_id" {
  name = "/${var.project}/${var.env}/efs/security_group_id"
}

# ECR
data "aws_ssm_parameter" "ecr_repository_url" {
  name = "/${var.project}/${var.env}/ecr/api_repository_url"
}

# Observabilidade
data "aws_ssm_parameter" "results_bucket" {
  name = "/${var.project}/${var.env}/obs/results_bucket"
}

data "aws_ssm_parameter" "metric_namespace" {
  name = "/${var.project}/${var.env}/obs/metric_namespace"
}

data "aws_ssm_parameter" "policy_bench_results_arn" {
  name = "/${var.project}/${var.env}/obs/policy_bench_results_arn"
}

data "aws_ssm_parameter" "policy_cw_emf_arn" {
  name = "/${var.project}/${var.env}/obs/policy_cw_emf_arn"
}

data "aws_ssm_parameter" "policy_xray_arn" {
  name = "/${var.project}/${var.env}/obs/policy_xray_arn"
}

data "aws_ssm_parameter" "log_group_otel" {
  name = "/${var.project}/${var.env}/obs/log_group_otel"
}

locals {
  vpc_id             = data.aws_ssm_parameter.vpc_id.value
  public_subnet_ids  = split(",", data.aws_ssm_parameter.public_subnet_ids.value)
  private_subnet_ids = split(",", data.aws_ssm_parameter.private_subnet_ids.value)

  efs_file_system_id  = data.aws_ssm_parameter.efs_file_system_id.value
  efs_file_system_arn = data.aws_ssm_parameter.efs_file_system_arn.value
  efs_ap_id           = data.aws_ssm_parameter.efs_access_point_id.value
  efs_sg_id           = data.aws_ssm_parameter.efs_security_group_id.value

  ecr_repository_url = data.aws_ssm_parameter.ecr_repository_url.value

  results_bucket   = data.aws_ssm_parameter.results_bucket.value
  metric_namespace = data.aws_ssm_parameter.metric_namespace.value
  log_group_otel   = data.aws_ssm_parameter.log_group_otel.value

  policy_bench_results_arn = data.aws_ssm_parameter.policy_bench_results_arn.value
  policy_cw_emf_arn        = data.aws_ssm_parameter.policy_cw_emf_arn.value
  policy_xray_arn          = data.aws_ssm_parameter.policy_xray_arn.value

  common_tags = {
    env     = var.env
    project = var.project
  }
}

# Necessario para pegar cidr_block da VPC (usado em SGs)
data "aws_vpc" "this" {
  id = local.vpc_id
}
