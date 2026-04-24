data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# -----------------------------------------------------------------------------
# Execution role da task (puxa imagem do ECR, envia logs)
# -----------------------------------------------------------------------------
resource "aws_iam_role" "task_execution" {
  name               = "${var.project}-s3-ecs-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "task_execution_attach" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# -----------------------------------------------------------------------------
# Task role - a API em si nao precisa de S3 porque le/escreve via POSIX
# (o Mountpoint e quem fala com S3). Deixamos minimo por defesa em profundidade.
# -----------------------------------------------------------------------------
resource "aws_iam_role" "task" {
  name               = "${var.project}-s3-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.common_tags
}

# -----------------------------------------------------------------------------
# Instance role da EC2 do cluster ECS:
#   - AmazonEC2ContainerServiceforEC2Role (registrar no cluster)
#   - AmazonSSMManagedInstanceCore (Session Manager)
#   - Acesso s3:* no bucket de files (para o Mountpoint montar)
# -----------------------------------------------------------------------------
resource "aws_iam_role" "ecs_instance" {
  name               = "${var.project}-s3-ecs-instance-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_instance_ecs" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "ecs_instance_ssm" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Permissoes para Mountpoint for S3 montar o bucket.
# Referencia: https://github.com/awslabs/mountpoint-s3/blob/main/doc/CONFIGURATION.md
data "aws_iam_policy_document" "mountpoint_s3" {
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.s3files_bucket_arn]
  }
  statement {
    sid = "ReadWriteObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = ["${local.s3files_bucket_arn}/*"]
  }
}

resource "aws_iam_policy" "mountpoint_s3" {
  name   = "${var.project}-mountpoint-s3"
  policy = data.aws_iam_policy_document.mountpoint_s3.json
}

resource "aws_iam_role_policy_attachment" "ecs_instance_s3" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = aws_iam_policy.mountpoint_s3.arn
}

# Observability (ARNs via SSM publicado pela stack 02)
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

resource "aws_iam_role_policy_attachment" "exec_cw" {
  role       = aws_iam_role.task_execution.name
  policy_arn = local.policy_cw_emf_arn
}

# CloudWatch Agent nas EC2 do cluster (metricas de host: EBS IOPS, NET, mem)
resource "aws_iam_role_policy_attachment" "ecs_instance_cw_agent" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "ecs_instance" {
  name = "${var.project}-s3-ecs-instance-profile"
  role = aws_iam_role.ecs_instance.name
}
