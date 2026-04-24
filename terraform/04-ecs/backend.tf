terraform {
  backend "s3" {
    key = "efs-api-lab/04-ecs/terraform.tfstate"
  }
}
