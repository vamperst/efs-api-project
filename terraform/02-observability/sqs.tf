# SQS para dispatch de benchmarks em fan-out por task Fargate.
# Uma fila separada por variant (efs, s3) para nao precisar filtrar no
# consumer. Cada task Fargate faz long-poll em 1 fila (definida por env).
# DLQ para mensagens que falharem 3 vezes.

resource "aws_sqs_queue" "bench_dlq" {
  name                      = "${var.project}-bench-dlq"
  message_retention_seconds = 1209600 # 14 dias

  tags = local.common_tags
}

resource "aws_sqs_queue" "bench_efs" {
  name                       = "${var.project}-bench-efs"
  visibility_timeout_seconds = 3600 # 1h, bench pode ser demorado
  message_retention_seconds  = 3600
  receive_wait_time_seconds  = 20 # long-poll

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.bench_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.common_tags
}

resource "aws_sqs_queue" "bench_s3" {
  name                       = "${var.project}-bench-s3"
  visibility_timeout_seconds = 3600
  message_retention_seconds  = 3600
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.bench_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.common_tags
}

# IAM policy que da SendMessage/ReceiveMessage/DeleteMessage nas duas filas.
data "aws_iam_policy_document" "bench_sqs" {
  statement {
    sid = "UseBenchQueues"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [
      aws_sqs_queue.bench_efs.arn,
      aws_sqs_queue.bench_s3.arn,
    ]
  }
}

resource "aws_iam_policy" "bench_sqs" {
  name   = "${var.project}-bench-sqs"
  policy = data.aws_iam_policy_document.bench_sqs.json
  tags   = local.common_tags
}

# SSM outputs para as stacks 04 e 07 lerem
resource "aws_ssm_parameter" "sqs_bench_efs_url" {
  name  = "${local.ssm_prefix}/sqs_bench_efs_url"
  type  = "String"
  value = aws_sqs_queue.bench_efs.url
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "sqs_bench_s3_url" {
  name  = "${local.ssm_prefix}/sqs_bench_s3_url"
  type  = "String"
  value = aws_sqs_queue.bench_s3.url
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "sqs_bench_dlq_url" {
  name  = "${local.ssm_prefix}/sqs_bench_dlq_url"
  type  = "String"
  value = aws_sqs_queue.bench_dlq.url
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "policy_bench_sqs_arn" {
  name  = "${local.ssm_prefix}/policy_bench_sqs_arn"
  type  = "String"
  value = aws_iam_policy.bench_sqs.arn
  tags  = local.common_tags
}
