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

variable "instance_type" {
  description = <<-EOT
    Tipo Nitro com rede alta para NAO ser gargalo na migracao.
    c6in.2xlarge: 8 vCPU, 16 GB, ate 50 Gbps rede, EBS 50k IOPS.
  EOT
  type        = string
  default     = "c6in.2xlarge"
}

variable "auto_run_migration" {
  description = "Se true, o user-data ja dispara a migracao ao subir"
  type        = bool
  default     = false
}

variable "dataset_subpath" {
  description = <<-EOT
    Caminho relativo dentro do EFS a migrar. Vazio = migra TUDO.
    Ex: 'datasets/fiap-data' para migrar so esse dataset.
  EOT
  type        = string
  default     = ""
}

variable "s3_subpath" {
  description = "Subpasta dentro de /mnt/s3 para destino. Vazio = raiz."
  type        = string
  default     = ""
}

variable "rsync_parallelism" {
  description = "Quantos processos rsync em paralelo (divide a carga por diretorio de primeiro nivel)"
  type        = number
  default     = 4
}
