# Policies reutilizadas pelas outras stacks (API, populator, migrator).
# Elas referenciam essas policies via data source (nome estavel).

# 1) Write no bucket de results
data "aws_iam_policy_document" "bench_results_write" {
  statement {
    sid       = "ListResults"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.results.arn]
  }
  statement {
    sid = "PutResults"
    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:GetObject",
      "s3:AbortMultipartUpload",
    ]
    resources = ["${aws_s3_bucket.results.arn}/*"]
  }
}

resource "aws_iam_policy" "bench_results_write" {
  name        = "${var.project}-bench-results-write"
  description = "Permite escrever JSONs de resultado no bucket de observabilidade"
  policy      = data.aws_iam_policy_document.bench_results_write.json

  tags = local.common_tags
}

# 2) Publicar metricas EMF no namespace do projeto
data "aws_iam_policy_document" "cw_metrics" {
  statement {
    actions = [
      "cloudwatch:PutMetricData",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [var.metric_namespace]
    }
  }
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/bench/*",
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/bench/*:*",
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/otel/*",
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/otel/*:*",
    ]
  }
}

resource "aws_iam_policy" "cw_metrics" {
  name        = "${var.project}-cw-emf-metrics"
  description = "Permite enviar metricas EMF no namespace ${var.metric_namespace}"
  policy      = data.aws_iam_policy_document.cw_metrics.json

  tags = local.common_tags
}

# 3) X-Ray (tracing)
resource "aws_iam_policy" "xray" {
  name        = "${var.project}-xray-write"
  description = "Permite enviar segments para X-Ray"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "xray:GetSamplingRules",
        "xray:GetSamplingTargets",
        "xray:GetSamplingStatisticSummaries",
      ]
      Resource = "*"
    }]
  })

  tags = local.common_tags
}
