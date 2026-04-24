terraform {
  backend "s3" {
    key = "efs-api-lab/03-efs/terraform.tfstate"
  }
}
