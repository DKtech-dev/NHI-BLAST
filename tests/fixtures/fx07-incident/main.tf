# Terraform source for the fixture incident state.
# Checked in for provenance: the reference command scans tfstate.json (applied state),
# not this HCL. The two assume_role_policy sub lines are laid out at the exact
# line numbers cited by docs/SPEC.md 14.4: deploy-prod trust main.tf:48 and
# legacy-ci trust main.tf:61.

terraform {
  required_version = ">= 1.9"
}

provider "aws" {
  region = "us-east-1"
}

locals {
  account      = "111122223333"
  oidc_host    = "token.actions.githubusercontent.com"
  provider_arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.oidc_host}"
  client_id_list = ["sts.amazonaws.com"]
}

# ---
# The production role is intentionally narrow: one tag family, one audience.
# ---
# ---
# The production role is intentionally narrow: one tag family, one audience.
# ---
# ---
# The production role is intentionally narrow: one tag family, one audience.
# ---
# ---
# The production role is intentionally narrow: one tag family, one audience.
# ---
# ---
# The production role is intentionally narrow: one tag family, one audience.
# ---
resource "aws_iam_role" "deploy_prod" {
  name                 = "deploy-prod"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Federated = local.provider_arn }, Action = "sts:AssumeRoleWithWebIdentity", Condition = {
      StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
      StringLike   = { "token.actions.githubusercontent.com:sub" = "repo:acme/shop:ref:refs/tags/v*" }
    } }]
  })
}
# ---
# The production role is intentionally narrow: one tag family, one audience.
# ---
resource "aws_iam_role" "legacy_ci" {
  name = "legacy-ci"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Federated = local.provider_arn }, Action = "sts:AssumeRoleWithWebIdentity", Condition = {
      StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
      StringLike   = { "token.actions.githubusercontent.com:sub" = "repo:acme/*" }
    } }]
  })
}

resource "aws_secretsmanager_secret" "db_master" {
  name = "prod/db-master"
}

resource "aws_secretsmanager_secret" "app_config" {
  name = "prod/app-config"
}

resource "aws_secretsmanager_secret_rotation" "app_config" {
  secret_id = aws_secretsmanager_secret.app_config.id
  rotation_rules {
    automatically_after_days = 30
  }
}

resource "aws_ssm_parameter" "stripe_live_key" {
  name = "/prod/stripe/live_key"
  type = "SecureString"
}

resource "aws_ssm_parameter" "legacy_ci_token" {
  name = "/legacy/ci-token"
  type = "SecureString"
}
