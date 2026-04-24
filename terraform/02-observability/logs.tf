# Log groups dedicados. A API usa /ecs/efs-api-lab-api (EFS) e
# /ecs/efs-api-lab-s3-api (S3) das stacks 03 e 06. Aqui criamos grupos
# extras para os *benchmarks* (logs estruturados de runs) e para os
# collectors OTel.

resource "aws_cloudwatch_log_group" "bench_api" {
  name              = "/bench/api"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "bench_populator" {
  name              = "/bench/populator"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "bench_migrator" {
  name              = "/bench/migrator"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "otel" {
  name              = "/otel/efs-api-lab"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}
