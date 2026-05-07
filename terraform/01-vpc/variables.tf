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

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

# Newbits para cidrsubnet (igual ao repo FIAP de referencia).
# Com /16 + 6 -> /22 por subnet (1024 IPs cada).
variable "subnet_scale" {
  type    = number
  default = 6
}

# NATs - default 1 (mais barato e dentro do limite default de EIPs=5).
# Para HA por AZ, use length(azs) ou ajuste para o quanto quiser.
# Com 1 NAT, todas as subnets privadas roteiam via ele (perde HA se AZ cair).
variable "nat_count" {
  type    = number
  default = 1
}
