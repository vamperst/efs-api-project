# -----------------------------------------------------------------------------
# Recursos S3 Files:
#   - IAM role que o servico S3 Files assume para falar com o bucket
#   - File System
#   - Mount target em cada subnet privada
#   - Access point com POSIX 1000:1000 (mesmo uid do container da API)
# -----------------------------------------------------------------------------

# Trust policy: S3 Files usa o mesmo service principal do EFS.
# Referencia: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-files-prereq-policies.html
data "aws_iam_policy_document" "s3files_trust" {
  statement {
    sid     = "AllowS3FilesAssumeRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["elasticfilesystem.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:s3files:${var.aws_region}:${data.aws_caller_identity.current.account_id}:file-system/*"]
    }
  }
}

data "aws_iam_policy_document" "s3files_bucket_access" {
  statement {
    sid = "BucketLevel"
    actions = [
      "s3:ListBucket",
      "s3:ListBucketVersions",
    ]
    resources = [local.s3files_bucket_arn]
  }

  statement {
    sid = "ObjectLevel"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:GetObjectAcl",
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${local.s3files_bucket_arn}/*"]
  }
}

resource "aws_iam_role" "s3files_service" {
  name               = "${var.project}-s3files-service"
  assume_role_policy = data.aws_iam_policy_document.s3files_trust.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "s3files_service_bucket" {
  name   = "bucket-access"
  role   = aws_iam_role.s3files_service.id
  policy = data.aws_iam_policy_document.s3files_bucket_access.json
}

# SG do mount target - aceita NFS/2049 apenas da SG da task Fargate.
resource "aws_security_group" "s3files_mt" {
  name        = "${var.project}-s3files-mt-sg"
  description = "Mount targets do S3 Files"
  vpc_id      = local.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-s3files-mt-sg"
  })
}

resource "aws_s3files_file_system" "this" {
  bucket                = local.s3files_bucket_arn
  role_arn              = aws_iam_role.s3files_service.arn
  accept_bucket_warning = true

  tags = merge(local.common_tags, {
    Name = "${var.project}-s3files"
  })

  # O File System so consegue ser criado depois que a role consegue acessar o
  # bucket - forcar ordem evita race condition.
  depends_on = [aws_iam_role_policy.s3files_service_bucket]
}

# Um mount target por subnet privada (AZ).
resource "aws_s3files_mount_target" "this" {
  count           = length(local.private_subnet_ids)
  file_system_id  = aws_s3files_file_system.this.id
  subnet_id       = local.private_subnet_ids[count.index]
  security_groups = [aws_security_group.s3files_mt.id]
}

# Access point - define uid/gid e raiz do container.
resource "aws_s3files_access_point" "this" {
  file_system_id = aws_s3files_file_system.this.id

  posix_user {
    uid = var.posix_uid
    gid = var.posix_gid
  }

  # Usamos /bench-root para que os subdirs criados pelo container virem
  # prefixos em bench-root/<p001>... no bucket S3. Isso nos permite medir
  # se distribuir em prefixos (teoricamente contornando o limite de 5500
  # GET/s/prefixo) muda o throughput.
  # Ref: https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
  root_directory {
    path = "/bench-root"
    creation_permissions {
      owner_uid   = var.posix_uid
      owner_gid   = var.posix_gid
      permissions = "0755"
    }
  }

  tags = local.common_tags
}
