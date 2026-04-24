# Publica outputs da stack de observabilidade no SSM.
# Convencao: /<project>/<env>/obs/<key>
#
# As stacks 03, 04, 05, 07 e 08 leem essas chaves para saber qual bucket usar,
# qual policy attachar e qual namespace emitir.

locals {
  ssm_prefix = "/${var.project}/${var.env}/obs"
}

resource "aws_ssm_parameter" "results_bucket" {
  name  = "${local.ssm_prefix}/results_bucket"
  type  = "String"
  value = aws_s3_bucket.results.id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "results_bucket_arn" {
  name  = "${local.ssm_prefix}/results_bucket_arn"
  type  = "String"
  value = aws_s3_bucket.results.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "metric_namespace" {
  name  = "${local.ssm_prefix}/metric_namespace"
  type  = "String"
  value = var.metric_namespace
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "log_group_api" {
  name  = "${local.ssm_prefix}/log_group_api"
  type  = "String"
  value = aws_cloudwatch_log_group.bench_api.name
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "log_group_populator" {
  name  = "${local.ssm_prefix}/log_group_populator"
  type  = "String"
  value = aws_cloudwatch_log_group.bench_populator.name
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "log_group_migrator" {
  name  = "${local.ssm_prefix}/log_group_migrator"
  type  = "String"
  value = aws_cloudwatch_log_group.bench_migrator.name
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "log_group_otel" {
  name  = "${local.ssm_prefix}/log_group_otel"
  type  = "String"
  value = aws_cloudwatch_log_group.otel.name
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "policy_bench_results_arn" {
  name  = "${local.ssm_prefix}/policy_bench_results_arn"
  type  = "String"
  value = aws_iam_policy.bench_results_write.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "policy_cw_emf_arn" {
  name  = "${local.ssm_prefix}/policy_cw_emf_arn"
  type  = "String"
  value = aws_iam_policy.cw_metrics.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "policy_xray_arn" {
  name  = "${local.ssm_prefix}/policy_xray_arn"
  type  = "String"
  value = aws_iam_policy.xray.arn
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "dashboard_name" {
  name  = "${local.ssm_prefix}/dashboard_name"
  type  = "String"
  value = aws_cloudwatch_dashboard.bench.dashboard_name
  tags  = local.common_tags
}
