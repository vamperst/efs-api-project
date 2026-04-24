output "state_bucket" {
  value = aws_s3_bucket.state.id
}

output "lock_table" {
  value = aws_dynamodb_table.lock.name
}

output "region" {
  value = var.aws_region
}

# Conteudo sugerido do backend.hcl que cada stack deve usar.
# Imprimir isso facilita o setup manual.
output "backend_hcl_template" {
  value = <<-EOT
    # Copie e salve como backend.hcl em cada stack (01-vpc, 02-efs, 03-ecs, 04-ec2-populator)
    # A linha 'key' MUDA por stack (ex.: "efs-api-lab/01-vpc/terraform.tfstate")
    bucket         = "${aws_s3_bucket.state.id}"
    dynamodb_table = "${aws_dynamodb_table.lock.name}"
    region         = "${var.aws_region}"
    encrypt        = true
  EOT
}
