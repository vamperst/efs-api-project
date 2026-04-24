data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "migrator" {
  name               = "${var.project}-migrator-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = local.common_tags
}

# SSM Session Manager
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.migrator.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# EFS read (o migrator so LE o EFS - nao precisa de write)
data "aws_iam_policy_document" "efs_ro" {
  statement {
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:DescribeMountTargets",
      "elasticfilesystem:DescribeFileSystems",
    ]
    resources = [local.efs_file_system_arn]
  }
}

resource "aws_iam_policy" "efs_ro" {
  name   = "${var.project}-migrator-efs-ro"
  policy = data.aws_iam_policy_document.efs_ro.json
}

resource "aws_iam_role_policy_attachment" "efs_ro" {
  role       = aws_iam_role.migrator.name
  policy_arn = aws_iam_policy.efs_ro.arn
}

# S3 read/write no bucket de destino (Mountpoint precisa de ListBucket +
# Get/Put/Delete/AbortMultipartUpload em /*)
data "aws_iam_policy_document" "s3_files" {
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [local.s3files_bucket_arn]
  }
  statement {
    sid = "Objects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${local.s3files_bucket_arn}/*"]
  }
}

resource "aws_iam_policy" "s3_files" {
  name   = "${var.project}-migrator-s3"
  policy = data.aws_iam_policy_document.s3_files.json
}

resource "aws_iam_role_policy_attachment" "s3_files" {
  role       = aws_iam_role.migrator.name
  policy_arn = aws_iam_policy.s3_files.arn
}

# Observability (ARNs via SSM publicado pela stack 02)
resource "aws_iam_role_policy_attachment" "bench_results" {
  role       = aws_iam_role.migrator.name
  policy_arn = local.policy_bench_results_arn
}

resource "aws_iam_role_policy_attachment" "cw_metrics" {
  role       = aws_iam_role.migrator.name
  policy_arn = local.policy_cw_emf_arn
}

resource "aws_iam_role_policy_attachment" "cw_agent" {
  role       = aws_iam_role.migrator.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "migrator" {
  name = "${var.project}-migrator-profile"
  role = aws_iam_role.migrator.name
}
