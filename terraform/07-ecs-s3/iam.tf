data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role - puxa imagem do ECR, manda logs
resource "aws_iam_role" "task_execution" {
  name               = "${var.project}-s3-ecs-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "task_execution_attach" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task role - a task precisa montar e escrever no S3 Files + ler objetos direto
resource "aws_iam_role" "task" {
  name               = "${var.project}-s3-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.common_tags
}

# Permissoes para a task montar o filesystem S3 Files (s3files:ClientMount/Write)
# e ler objetos direto do bucket (otimizacao).
# Referencia: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-files-prereq-policies.html#s3-files-prereq-iam-compute-role
data "aws_iam_policy_document" "s3files_client" {
  statement {
    sid = "S3FilesMount"
    actions = [
      "s3files:ClientMount",
      "s3files:ClientWrite",
      "s3files:ClientRootAccess",
      "s3files:DescribeMountTargets",
    ]
    resources = [
      aws_s3files_file_system.this.arn,
      aws_s3files_access_point.this.arn,
    ]
  }

  statement {
    sid = "S3ObjectRead"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = ["${local.s3files_bucket_arn}/*"]
  }

  statement {
    sid       = "S3BucketList"
    actions   = ["s3:ListBucket"]
    resources = [local.s3files_bucket_arn]
  }
}

resource "aws_iam_policy" "s3files_client" {
  name   = "${var.project}-s3files-client"
  policy = data.aws_iam_policy_document.s3files_client.json
}

resource "aws_iam_role_policy_attachment" "task_s3files" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.s3files_client.arn
}

# Observability (SSM da stack 02)
resource "aws_iam_role_policy_attachment" "task_bench_results" {
  role       = aws_iam_role.task.name
  policy_arn = local.policy_bench_results_arn
}

resource "aws_iam_role_policy_attachment" "task_cw" {
  role       = aws_iam_role.task.name
  policy_arn = local.policy_cw_emf_arn
}

resource "aws_iam_role_policy_attachment" "task_xray" {
  role       = aws_iam_role.task.name
  policy_arn = local.policy_xray_arn
}

resource "aws_iam_role_policy_attachment" "task_bench_sqs" {
  role       = aws_iam_role.task.name
  policy_arn = local.policy_bench_sqs_arn
}

resource "aws_iam_role_policy_attachment" "exec_cw" {
  role       = aws_iam_role.task_execution.name
  policy_arn = local.policy_cw_emf_arn
}
