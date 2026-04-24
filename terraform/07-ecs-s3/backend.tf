terraform {
  backend "s3" {
    key = "efs-api-lab/07-ecs-s3/terraform.tfstate"
  }
}
