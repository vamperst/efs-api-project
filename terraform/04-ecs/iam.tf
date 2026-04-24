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
  name               = "${var.project}-ecs-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "task_execution_attach" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task role - as permissoes que a aplicacao usa em runtime.
# Incluimos acesso ao EFS (ClientMount/ClientWrite) para o access point.
resource "aws_iam_role" "task" {
  name               = "${var.project}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "efs_access" {
  statement {
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:ClientWrite",
      "elasticfilesystem:ClientRootAccess",
      "elasticfilesystem:DescribeMountTargets",
    ]
    resources = [local.efs_file_system_arn]
  }
}

resource "aws_iam_policy" "efs_access" {
  name   = "${var.project}-efs-access"
  policy = data.aws_iam_policy_document.efs_access.json
}

resource "aws_iam_role_policy_attachment" "task_efs" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.efs_access.arn
}

# Observability (ARNs vindos do SSM, publicados pela stack 02)
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

# Execution role tambem precisa da cw_metrics (para o sidecar ADOT publicar)
resource "aws_iam_role_policy_attachment" "exec_cw" {
  role       = aws_iam_role.task_execution.name
  policy_arn = local.policy_cw_emf_arn
}
