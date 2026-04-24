output "instance_id" {
  value = aws_instance.migrator.id
}

output "private_ip" {
  value = aws_instance.migrator.private_ip
}

output "ssm_connect_command" {
  value = "aws ssm start-session --target ${aws_instance.migrator.id} --region ${var.aws_region}"
}

output "source_path" {
  value = local.efs_source
}

output "destination_s3_uri" {
  value = local.s3_dest
}

output "migrate_command" {
  value       = "sudo /usr/local/bin/migrate.sh"
  description = "Rode dentro da EC2 (via SSM) para iniciar a migracao"
}
