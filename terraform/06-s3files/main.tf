# Stack 05 - S3 bucket que vai substituir o EFS como storage da API.
#
# A API e exatamente a mesma (mesmo codigo Python). No ECS novo (stack 06),
# usamos Mountpoint for Amazon S3 no host EC2 para montar esse bucket em
# /mnt/efs dentro do container - assim a API le/escreve igual, mas o backing
# store e S3.

resource "aws_s3_bucket" "files" {
  bucket        = local.bucket
  force_destroy = false

  tags = merge(local.common_tags, {
    Name    = local.bucket
    purpose = "api-storage"
  })
}

resource "aws_s3_bucket_versioning" "files" {
  bucket = aws_s3_bucket.files.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "files" {
  bucket = aws_s3_bucket.files.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# -----------------------------------------------------------------------------
# Gateway Endpoint para S3 - trafego nao sai da VPC, economiza NAT
# -----------------------------------------------------------------------------
resource "aws_vpc_endpoint" "s3" {
  count             = var.create_gateway_endpoint ? 1 : 0
  vpc_id            = data.aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.private.ids

  tags = merge(local.common_tags, {
    Name = "${var.project}-s3-gateway-endpoint"
  })
}
