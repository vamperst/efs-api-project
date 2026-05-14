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

variable "api_image_tag" {
  description = "Tag da imagem no ECR (mesma imagem usada na stack 04 - a variante e decidida via env STORAGE_VARIANT)"
  type        = string
  default     = "latest"
}

variable "api_desired_count" {
  type    = number
  default = 10
}

# Deixei identico a stack 04 para o bench ser apples-to-apples.
# Fargate soh aceita combinacoes especificas de cpu/memory:
# 512 CPU -> 1024/2048/3072/4096 MB
variable "api_cpu" {
  type    = string
  default = "512"
}

variable "api_memory" {
  type    = string
  default = "1024"
}

variable "api_port" {
  type    = number
  default = 8000
}

variable "alb_public" {
  type    = bool
  default = true
}

# POSIX uid/gid do access point S3 Files.
# A imagem da API roda como uid/gid 1000 (apiuser).
variable "posix_uid" {
  type    = number
  default = 1000
}

variable "posix_gid" {
  type    = number
  default = 1000
}
