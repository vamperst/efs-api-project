terraform {
  backend "s3" {
    key = "efs-api-lab/06-s3files/terraform.tfstate"
  }
}
