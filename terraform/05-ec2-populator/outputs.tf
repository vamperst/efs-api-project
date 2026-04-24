output "instance_id" {
  value = aws_instance.populator.id
}

output "private_ip" {
  value = aws_instance.populator.private_ip
}

output "ssm_connect_command" {
  value = "aws ssm start-session --target ${aws_instance.populator.id} --region ${var.aws_region}"
}

output "efs_id" {
  value = local.efs_file_system_id
}

output "efs_access_point_id" {
  value = local.efs_ap_id
}

output "target_data_size_gb" {
  value = var.target_data_size_gb
}
