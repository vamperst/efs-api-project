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
  description = "Tag da imagem no ECR (a mesma criada no build_and_push.sh)"
  type        = string
  default     = "latest"
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "api_port" {
  type    = number
  default = 8000
}

variable "instance_type" {
  description = <<-EOT
    Tipo das EC2 do cluster ECS. Nitro recomendado para nao ser gargalo
    nos testes de benchmark (leitura/escrita pelo Mountpoint).
    c6in.large: 2 vCPU, 4 GB, ate 25 Gbps rede.
  EOT
  type        = string
  default     = "c6in.large"
}

variable "asg_min" {
  type    = number
  default = 1
}

variable "asg_max" {
  type    = number
  default = 2
}

variable "asg_desired" {
  type    = number
  default = 1
}

variable "alb_public" {
  description = "Se true, ALB fica em subnets publicas"
  type        = bool
  default     = true
}
