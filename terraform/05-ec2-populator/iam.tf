data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "populator" {
  name               = "${var.project}-populator-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# SSM Session Manager
# -----------------------------------------------------------------------------
# AmazonSSMManagedInstanceCore contem as acoes necessarias para:
#   - ssm:UpdateInstanceInformation  (registra no SSM)
#   - ssmmessages:CreateControlChannel / CreateDataChannel / OpenControlChannel /
#     OpenDataChannel                (Session Manager funciona)
#   - ec2messages:*                  (heartbeat do agente)
#   - s3:GetObject em buckets do SSM (para distribution/updates do agente)
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.populator.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Permissao extra para que o proprio SSM Agent possa se auto-atualizar sem
# depender de buckets publicos. Nao e estritamente necessaria com AL2023
# (que tem o agente pre-instalado), mas ajuda em updates automaticos.
data "aws_iam_policy_document" "ssm_agent_update" {
  statement {
    actions = [
      "ssm:UpdateInstanceInformation",
      "ssm:ListAssociations",
      "ssm:ListInstanceAssociations",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ssm_agent_update" {
  name   = "${var.project}-populator-ssm-extra"
  policy = data.aws_iam_policy_document.ssm_agent_update.json
}

resource "aws_iam_role_policy_attachment" "ssm_agent_update" {
  role       = aws_iam_role.populator.name
  policy_arn = aws_iam_policy.ssm_agent_update.arn
}

# -----------------------------------------------------------------------------
# Acesso ao EFS via IAM (ClientMount/Write)
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "efs" {
  statement {
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:ClientWrite",
      "elasticfilesystem:ClientRootAccess",
      "elasticfilesystem:DescribeMountTargets",
      "elasticfilesystem:DescribeFileSystems",
    ]
    resources = [local.efs_file_system_arn]
  }
}

resource "aws_iam_policy" "efs" {
  name   = "${var.project}-populator-efs"
  policy = data.aws_iam_policy_document.efs.json
}

resource "aws_iam_role_policy_attachment" "efs" {
  role       = aws_iam_role.populator.name
  policy_arn = aws_iam_policy.efs.arn
}

# Observability (ARNs via SSM da stack 02)
resource "aws_iam_role_policy_attachment" "bench_results" {
  role       = aws_iam_role.populator.name
  policy_arn = local.policy_bench_results_arn
}

resource "aws_iam_role_policy_attachment" "cw_metrics" {
  role       = aws_iam_role.populator.name
  policy_arn = local.policy_cw_emf_arn
}

resource "aws_iam_role_policy_attachment" "cw_agent" {
  role       = aws_iam_role.populator.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "populator" {
  name = "${var.project}-populator-profile"
  role = aws_iam_role.populator.name
}
