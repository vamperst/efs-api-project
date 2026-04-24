terraform {
  backend "s3" {
    key = "efs-api-lab/02-observability/terraform.tfstate"
  }
}
