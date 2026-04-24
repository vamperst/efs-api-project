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

variable "state_bucket_name" {
  description = <<-EOT
    Nome do bucket S3 que guarda os states. Precisa ser globalmente unico.
    Se vazio, usamos <project>-tfstate-<account_id>-<region>.
  EOT
  type        = string
  default     = ""
}

variable "lock_table_name" {
  description = "Nome da DynamoDB table usada para state locking"
  type        = string
  default     = ""
}
