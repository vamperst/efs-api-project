# Bucket onde todos os jobs (API, populator, migrator) publicam seus resultados
# em JSON. O report_generator.py baixa tudo e monta o HTML.
#
# Prefixos:
#   results/api/<variant>/<bench_id>.json      <-- /bench/write e /bench/read
#   results/populator/<run_id>.json            <-- populate_efs.py
#   results/migrator/<run_id>.json             <-- migrate.sh

resource "aws_s3_bucket" "results" {
  bucket        = local.bucket
  force_destroy = true

  tags = merge(local.common_tags, {
    Name = local.bucket
  })
}

resource "aws_s3_bucket_versioning" "results" {
  bucket = aws_s3_bucket.results.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "results" {
  bucket = aws_s3_bucket.results.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "results" {
  bucket                  = aws_s3_bucket.results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
