# VPC Flow Logs -> CloudWatch Logs
# Auditoria de todo trafego IP na VPC (ACCEPT/REJECT).

resource "aws_cloudwatch_log_group" "flow" {
  name              = "/vpc/${var.project}-flow-logs"
  retention_in_days = 14
  tags              = local.common_tags
}

data "aws_iam_policy_document" "flow_logs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "flow_logs" {
  name               = "${var.project}-vpc-flow-logs"
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "flow_logs_write" {
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.flow.arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow_logs_write" {
  role   = aws_iam_role.flow_logs.id
  policy = data.aws_iam_policy_document.flow_logs_write.json
}

resource "aws_flow_log" "this" {
  iam_role_arn    = aws_iam_role.flow_logs.arn
  log_destination = aws_cloudwatch_log_group.flow.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${var.project}-flow-logs"
  })
}

# Restringe o SG default da VPC (nega todo trafego). Boa pratica AWS.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  # sem ingress / sem egress = nega tudo

  tags = merge(local.common_tags, {
    Name = "${var.project}-default-sg-locked"
  })
}
