variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "efs-api-lab"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "bucket_name" {
  description = <<-EOT
    Nome do bucket S3. Se vazio, usamos <project>-files-<account_id>-<region>.
    Precisa ser globalmente unico.
  EOT
  type        = string
  default     = ""
}

variable "create_gateway_endpoint" {
  description = <<-EOT
    Se true, cria um VPC Gateway Endpoint para S3 na VPC do projeto.
    Deixa o trafego S3 dentro da AWS (sem sair pro NAT), mais rapido e barato.
    Recomendado: true.
  EOT
  type        = bool
  default     = true
}
