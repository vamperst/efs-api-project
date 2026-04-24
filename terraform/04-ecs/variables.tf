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
  description = "Tag da imagem no ECR (o script de build faz push dessa tag)"
  type        = string
  default     = "latest"
}

variable "api_desired_count" {
  type    = number
  default = 1
}

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
  description = "Se true, ALB fica em subnets publicas (acessivel pela internet)"
  type        = bool
  default     = true
}
