data "aws_caller_identity" "current" {}

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

# Bucket S3 Files (criado pela stack 06)
data "aws_ssm_parameter" "s3files_bucket" {
  name = "/${var.project}/${var.env}/s3files/bucket_name"
}

data "aws_ssm_parameter" "s3files_bucket_arn" {
  name = "/${var.project}/${var.env}/s3files/bucket_arn"
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

data "aws_ssm_parameter" "sqs_bench_s3_url" {
  name = "/${var.project}/${var.env}/obs/sqs_bench_s3_url"
}

data "aws_ssm_parameter" "policy_bench_sqs_arn" {
  name = "/${var.project}/${var.env}/obs/policy_bench_sqs_arn"
}

locals {
  vpc_id             = data.aws_ssm_parameter.vpc_id.value
  public_subnet_ids  = split(",", data.aws_ssm_parameter.public_subnet_ids.value)
  private_subnet_ids = split(",", data.aws_ssm_parameter.private_subnet_ids.value)

  s3files_bucket     = data.aws_ssm_parameter.s3files_bucket.value
  s3files_bucket_arn = data.aws_ssm_parameter.s3files_bucket_arn.value

  ecr_repository_url = data.aws_ssm_parameter.ecr_repository_url.value

  results_bucket       = data.aws_ssm_parameter.results_bucket.value
  metric_namespace     = data.aws_ssm_parameter.metric_namespace.value
  log_group_otel       = data.aws_ssm_parameter.log_group_otel.value
  sqs_bench_url        = data.aws_ssm_parameter.sqs_bench_s3_url.value
  policy_bench_sqs_arn = data.aws_ssm_parameter.policy_bench_sqs_arn.value

  policy_bench_results_arn = data.aws_ssm_parameter.policy_bench_results_arn.value
  policy_cw_emf_arn        = data.aws_ssm_parameter.policy_cw_emf_arn.value
  policy_xray_arn          = data.aws_ssm_parameter.policy_xray_arn.value

  common_tags = {
    env     = var.env
    project = var.project
    variant = "s3"
  }
}

data "aws_vpc" "this" {
  id = local.vpc_id
}
