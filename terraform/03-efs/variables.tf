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

variable "throughput_mode" {
  description = "EFS throughput mode. `bursting` (credits), `elastic` (scale on demand), `provisioned` (fixed MiB/s)."
  type        = string
  default     = "elastic"

  validation {
    condition     = contains(["bursting", "elastic", "provisioned"], var.throughput_mode)
    error_message = "throughput_mode deve ser bursting, elastic ou provisioned."
  }
}

variable "provisioned_throughput_mibps" {
  description = "Somente se throughput_mode=provisioned. MiB/s reservados (custo $6/MiB/mes)."
  type        = number
  default     = 512
}
