resource "aws_cloudwatch_dashboard" "bench" {
  dashboard_name = "${var.project}-bench"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Bench Write - throughput (MB/s) por variant"
          region = var.aws_region
          metrics = [
            [var.metric_namespace, "BenchWriteThroughputMBps", "variant", "efs"],
            [".", ".", ".", "s3"],
          ]
          view   = "timeSeries"
          stat   = "Average"
          period = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Bench Read - throughput (MB/s) por variant"
          region = var.aws_region
          metrics = [
            [var.metric_namespace, "BenchReadThroughputMBps", "variant", "efs"],
            [".", ".", ".", "s3"],
          ]
          view   = "timeSeries"
          stat   = "Average"
          period = 60
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Latencia por operacao (p50/p99, ms)"
          region = var.aws_region
          metrics = [
            [var.metric_namespace, "FileOpLatencyMs", "op", "write", "variant", "efs", { stat = "p50", label = "efs p50" }],
            ["...", { stat = "p99", label = "efs p99" }],
            [var.metric_namespace, "FileOpLatencyMs", "op", "write", "variant", "s3", { stat = "p50", label = "s3 p50" }],
            ["...", { stat = "p99", label = "s3 p99" }],
          ]
          view   = "timeSeries"
          period = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Migracao - bytes transferidos"
          region = var.aws_region
          metrics = [
            [var.metric_namespace, "MigrateBytes"],
          ]
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
        }
      },
    ]
  })
}
