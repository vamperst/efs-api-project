output "alb_url" {
  value       = "http://${aws_lb.api.dns_name}"
  description = "Endpoint da API S3-backed"
}

output "alb_dns_name" {
  value = aws_lb.api.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  value = aws_ecs_service.api.name
}

output "s3files_file_system_id" {
  value = aws_s3files_file_system.this.id
}

output "s3files_file_system_arn" {
  value = aws_s3files_file_system.this.arn
}

output "s3files_access_point_arn" {
  value = aws_s3files_access_point.this.arn
}

output "s3files_mount_target_ids" {
  value = aws_s3files_mount_target.this[*].id
}
