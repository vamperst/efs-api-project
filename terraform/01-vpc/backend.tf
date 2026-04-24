terraform {
  # Backend S3 + DynamoDB lock.
  # A configuracao real (bucket, region, dynamodb_table) vem do backend.hcl,
  # que deve ser passado no init:
  #
  #   terraform init -backend-config=backend.hcl
  #
  # (backend.hcl e gerado pela stack 00-backend)
  backend "s3" {
    key = "efs-api-lab/01-vpc/terraform.tfstate"
  }
}
