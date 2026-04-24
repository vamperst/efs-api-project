terraform {
  backend "s3" {
    key = "efs-api-lab/05-ec2-populator/terraform.tfstate"
  }
}
