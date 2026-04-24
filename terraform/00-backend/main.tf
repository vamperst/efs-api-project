data "aws_caller_identity" "current" {}

locals {
  bucket = var.state_bucket_name != "" ? var.state_bucket_name : "${var.project}-tfstate-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  table  = var.lock_table_name != "" ? var.lock_table_name : "${var.project}-tfstate-lock"
  common_tags = {
    project = var.project
    env     = var.env
    purpose = "terraform-backend"
  }
}

# -----------------------------------------------------------------------------
# S3 bucket para guardar os tfstates de todas as stacks
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "state" {
  bucket        = local.bucket
  force_destroy = false

  tags = merge(local.common_tags, {
    Name = local.bucket
  })
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# -----------------------------------------------------------------------------
# DynamoDB table para state locking
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "lock" {
  name         = local.table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = local.table
  })
}
