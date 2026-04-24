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

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "metric_namespace" {
  description = "Namespace CloudWatch onde as metricas EMF sao publicadas"
  type        = string
  default     = "EfsS3Bench"
}
