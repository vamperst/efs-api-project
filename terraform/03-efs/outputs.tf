output "efs_id" {
  value = aws_efs_file_system.this.id
}

output "efs_arn" {
  value = aws_efs_file_system.this.arn
}

output "efs_access_point_id" {
  value = aws_efs_access_point.data.id
}

output "efs_access_point_arn" {
  value = aws_efs_access_point.data.arn
}

output "efs_sg_id" {
  value = aws_security_group.efs.id
}

output "efs_dns_name" {
  value = aws_efs_file_system.this.dns_name
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.api.repository_url
  description = "URL do ECR onde a imagem da API deve ser publicada antes do deploy da stack 03-ecs"
}

output "ecr_repository_name" {
  value = aws_ecr_repository.api.name
}
