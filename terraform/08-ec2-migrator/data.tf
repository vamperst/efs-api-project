data "aws_ssm_parameter" "vpc_id" {
  name = "/${var.project}/${var.env}/vpc/vpc_id"
}

data "aws_ssm_parameter" "private_subnet_ids" {
  name = "/${var.project}/${var.env}/vpc/private_subnet_ids"
}

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

data "aws_ssm_parameter" "s3files_bucket" {
  name = "/${var.project}/${var.env}/s3files/bucket_name"
}

data "aws_ssm_parameter" "s3files_bucket_arn" {
  name = "/${var.project}/${var.env}/s3files/bucket_arn"
}

data "aws_ssm_parameter" "results_bucket" {
  name = "/${var.project}/${var.env}/obs/results_bucket"
}

data "aws_ssm_parameter" "policy_bench_results_arn" {
  name = "/${var.project}/${var.env}/obs/policy_bench_results_arn"
}

data "aws_ssm_parameter" "policy_cw_emf_arn" {
  name = "/${var.project}/${var.env}/obs/policy_cw_emf_arn"
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

locals {
  vpc_id               = data.aws_ssm_parameter.vpc_id.value
  private_subnet_ids   = split(",", data.aws_ssm_parameter.private_subnet_ids.value)
  efs_file_system_id   = data.aws_ssm_parameter.efs_file_system_id.value
  efs_file_system_arn  = data.aws_ssm_parameter.efs_file_system_arn.value
  efs_ap_id            = data.aws_ssm_parameter.efs_access_point_id.value
  efs_sg_id            = data.aws_ssm_parameter.efs_security_group_id.value
  s3files_bucket       = data.aws_ssm_parameter.s3files_bucket.value
  s3files_bucket_arn   = data.aws_ssm_parameter.s3files_bucket_arn.value
  bench_results_bucket = data.aws_ssm_parameter.results_bucket.value

  policy_bench_results_arn = data.aws_ssm_parameter.policy_bench_results_arn.value
  policy_cw_emf_arn        = data.aws_ssm_parameter.policy_cw_emf_arn.value

  common_tags = { env = var.env, project = var.project, role = "migrator" }
}
