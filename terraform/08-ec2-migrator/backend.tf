terraform {
  backend "s3" {
    key = "efs-api-lab/08-ec2-migrator/terraform.tfstate"
  }
}
