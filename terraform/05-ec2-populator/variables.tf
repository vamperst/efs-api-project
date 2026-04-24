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
  description = "Tipo Nitro com rede alta para nao ser gargalo na criacao dos arquivos"
  type        = string
  default     = "c6in.2xlarge" # Nitro, 8 vCPU, 16 GB RAM, ate 50 Gbps rede, EBS 50k IOPS
}

variable "target_data_size_gb" {
  description = "Tamanho alvo em GB para popular no EFS"
  type        = number
  default     = 100
}

variable "key_name" {
  description = "Nome de key-pair EC2. Vazio = acesso apenas por SSM Session Manager"
  type        = string
  default     = ""
}

variable "auto_run_populator" {
  description = "Se true, o user-data ja dispara o script de populate automaticamente"
  type        = bool
  default     = false
}

variable "enable_ssm_vpc_endpoints" {
  description = <<-EOT
    Cria VPC Interface Endpoints para ssm, ssmmessages e ec2messages.
    Recomendado: true, pois torna o SSM independente do NAT e mais confiavel
    em subnets privadas. Custo: ~$22/mes (3 endpoints x 3 AZs x $0.01/h).
    Se preferir economizar e seu NAT estiver operando, pode deixar false - o
    SSM funciona normalmente via NAT.
  EOT
  type        = bool
  default     = true
}
