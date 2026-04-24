output "alb_url" {
  value       = "http://${aws_lb.api.dns_name}"
  description = "Endpoint publico da API S3-backed"
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

output "asg_name" {
  value = aws_autoscaling_group.ecs.name
}
