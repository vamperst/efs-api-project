output "ecr_repository_url" {
  value       = local.ecr_repository_url
  description = "URL do ECR (criado pela stack 03-efs, lido via SSM)"
  sensitive   = true
}

output "alb_dns_name" {
  value       = aws_lb.api.dns_name
  description = "Endpoint publico da API"
}

output "alb_url" {
  value = "http://${aws_lb.api.dns_name}"
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  value = aws_ecs_service.api.name
}
