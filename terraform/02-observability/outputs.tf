output "results_bucket_name" {
  value = aws_s3_bucket.results.id
}

output "results_bucket_arn" {
  value = aws_s3_bucket.results.arn
}

output "bench_results_write_policy_arn" {
  value = aws_iam_policy.bench_results_write.arn
}

output "cw_metrics_policy_arn" {
  value = aws_iam_policy.cw_metrics.arn
}

output "xray_policy_arn" {
  value = aws_iam_policy.xray.arn
}

output "metric_namespace" {
  value = var.metric_namespace
}

output "log_group_api" {
  value = aws_cloudwatch_log_group.bench_api.name
}

output "log_group_populator" {
  value = aws_cloudwatch_log_group.bench_populator.name
}

output "log_group_migrator" {
  value = aws_cloudwatch_log_group.bench_migrator.name
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.bench.dashboard_name
}

output "dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.bench.dashboard_name}"
}
