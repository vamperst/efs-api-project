data "aws_caller_identity" "current" {}

locals {
  bucket = "${var.project}-bench-results-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  common_tags = {
    env     = var.env
    project = var.project
    purpose = "observability"
  }
}
