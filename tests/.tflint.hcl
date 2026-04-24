# TFLint - config compartilhada entre todas as stacks
# Rodar: cd terraform/<stack> && tflint --config=../../tests/.tflint.hcl --init && tflint --config=../../tests/.tflint.hcl

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.30.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
  deep_check = false # true requer credenciais AWS
}

# Regras especificas
rule "terraform_required_providers"  { enabled = true }
rule "terraform_required_version"    { enabled = true }
rule "terraform_standard_module_structure" { enabled = true }
rule "terraform_deprecated_interpolation"  { enabled = true }
rule "terraform_unused_declarations" { enabled = true }
rule "terraform_comment_syntax"      { enabled = true }
rule "terraform_documented_outputs"  { enabled = false } # outputs auto-documentados via name
rule "terraform_documented_variables" { enabled = false }
rule "terraform_naming_convention" {
  enabled = true
  format  = "snake_case"
}

# AWS - valida tipos de instancia, regiao valida, etc
rule "aws_instance_invalid_type"     { enabled = true }
rule "aws_s3_bucket_name"            { enabled = true }
rule "aws_iam_policy_document_gov_friendly_arns" { enabled = false }
