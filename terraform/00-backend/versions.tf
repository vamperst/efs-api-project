terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Esta stack e o BOOTSTRAP do backend remoto. Ela nao pode usar S3 state
  # porque o bucket/tabela ainda nao existem - entao fica com state LOCAL.
  # O arquivo terraform.tfstate dela mora no repositorio (commit em VCS)
  # ou em um cofre, e raramente muda.
}

provider "aws" {
  region = var.aws_region
}
