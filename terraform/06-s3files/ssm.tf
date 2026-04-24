# Publica outputs do bucket S3 de files no SSM.
# Convencao: /<project>/<env>/s3files/<key>

locals {
  ssm_prefix = "/${var.project}/${var.env}/s3files"
}

resource "aws_ssm_parameter" "bucket_name" {
  name  = "${local.ssm_prefix}/bucket_name"
  type  = "String"
  value = aws_s3_bucket.files.id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "bucket_arn" {
  name  = "${local.ssm_prefix}/bucket_arn"
  type  = "String"
  value = aws_s3_bucket.files.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "bucket_regional_domain_name" {
  name  = "${local.ssm_prefix}/bucket_regional_domain_name"
  type  = "String"
  value = aws_s3_bucket.files.bucket_regional_domain_name
  tags  = local.common_tags
}
