# Publica outputs de EFS e ECR no SSM.
# Convencao: /<project>/<env>/efs/<key>  e  /<project>/<env>/ecr/<key>

locals {
  ssm_efs_prefix = "/${var.project}/${var.env}/efs"
  ssm_ecr_prefix = "/${var.project}/${var.env}/ecr"
}

# --- EFS ---
resource "aws_ssm_parameter" "efs_file_system_id" {
  name  = "${local.ssm_efs_prefix}/file_system_id"
  type  = "String"
  value = aws_efs_file_system.this.id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "efs_file_system_arn" {
  name  = "${local.ssm_efs_prefix}/file_system_arn"
  type  = "String"
  value = aws_efs_file_system.this.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "efs_access_point_id" {
  name  = "${local.ssm_efs_prefix}/access_point_id"
  type  = "String"
  value = aws_efs_access_point.data.id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "efs_access_point_arn" {
  name  = "${local.ssm_efs_prefix}/access_point_arn"
  type  = "String"
  value = aws_efs_access_point.data.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "efs_security_group_id" {
  name  = "${local.ssm_efs_prefix}/security_group_id"
  type  = "String"
  value = aws_security_group.efs.id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "efs_dns_name" {
  name  = "${local.ssm_efs_prefix}/dns_name"
  type  = "String"
  value = aws_efs_file_system.this.dns_name
  tags  = local.common_tags
}

# --- ECR ---
resource "aws_ssm_parameter" "ecr_repository_url" {
  name  = "${local.ssm_ecr_prefix}/api_repository_url"
  type  = "String"
  value = aws_ecr_repository.api.repository_url
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "ecr_repository_arn" {
  name  = "${local.ssm_ecr_prefix}/api_repository_arn"
  type  = "String"
  value = aws_ecr_repository.api.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "ecr_repository_name" {
  name  = "${local.ssm_ecr_prefix}/api_repository_name"
  type  = "String"
  value = aws_ecr_repository.api.name
  tags  = local.common_tags
}
