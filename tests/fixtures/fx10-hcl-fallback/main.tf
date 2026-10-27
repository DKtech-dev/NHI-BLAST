# HCL-only fixture: no Terraform JSON is present, so the HCL fallback runs.
# Facts derived from HCL never exceed DERIVED (docs/SPEC.md 8.5).

terraform {
  required_version = ">= 1.9"
}

provider "aws" {
  region = "us-east-1"
}

variable "trusted_ref" {
  type    = string
  default = "repo:acme/shop:ref:refs/heads/main"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "deploy_prod" {
  name                 = "deploy-prod"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com" }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike   = { "token.actions.githubusercontent.com:sub" = var.trusted_ref }
      }
    }]
  })
}

resource "aws_ssm_parameter" "pipeline_token" {
  name  = "/prod/pipeline-token"
  type  = "SecureString"
  value = "FIXTURE_PLACEHOLDER_VALUE_NOT_A_SECRET"
}

resource "aws_iam_role_policy" "deploy_prod_read" {
  name = "read-pipeline-token"
  role = aws_iam_role.deploy_prod.id
  policy = <<-EOT
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": ["ssm:GetParameter"],
          "Resource": "arn:aws:ssm:us-east-1:111122223333:parameter/prod/pipeline-token"
        }
      ]
    }
  EOT
}

# for_each is not expanded by the HCL fallback: the role trust stays UNKNOWN and
# a D-TF-HCL-LIMIT diagnostic is emitted (docs/SPEC.md 8.5).
resource "aws_iam_role" "multi" {
  for_each = toset(["blue", "green"])
  name     = "deploy-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com" }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringLike = { "token.actions.githubusercontent.com:sub" = "repo:acme/shop:ref:refs/heads/${each.key}" } }
    }]
  })
}

# A remote module is never fetched: module expansion is UNKNOWN with D-TF-HCL-LIMIT.
module "remote_roles" {
  source  = "acme/oidc-roles/aws"
  version = "1.2.0"
  repo    = "acme/shop"
}
