output "bucket_name" {
  value = aws_s3_bucket.files.id
}

output "bucket_arn" {
  value = aws_s3_bucket.files.arn
}

output "bucket_regional_domain_name" {
  value = aws_s3_bucket.files.bucket_regional_domain_name
}

output "s3_gateway_endpoint_id" {
  value       = try(aws_vpc_endpoint.s3[0].id, null)
  description = "ID do Gateway Endpoint de S3 (null se desabilitado)"
}
