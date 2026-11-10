data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Remote state bucket (native S3 locking via <key>.tflock, no DynamoDB)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "terraform_state" {
  bucket = var.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# GitHub Actions OIDC
# thumbprint_list omitted: AWS verifies GitHub against its own trusted CA
# library (aws provider docs, aws_iam_openid_connect_provider).
# ---------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  oidc_host = "token.actions.githubusercontent.com"

  # Sub claim formats: docs.github.com "Configuring OpenID Connect in AWS".
  main_branch_sub  = "repo:${var.github_repository}:ref:refs/heads/main"
  pull_request_sub = "repo:${var.github_repository}:pull_request"

  state_object_arn = "${aws_s3_bucket.terraform_state.arn}/${var.state_key}"
  state_lock_arn   = "${aws_s3_bucket.terraform_state.arn}/${var.state_key}.tflock"
}

data "aws_iam_policy_document" "github_deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = [local.main_branch_sub]
    }
  }
}

data "aws_iam_policy_document" "github_plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = [local.pull_request_sub]
    }
  }
}

# Deploy role: main branch only, runs `terraform apply`.
# AdministratorAccess is a deliberate bootstrap shortcut; scope it down once
# the live stack's resource set is known.
resource "aws_iam_role" "github_deploy" {
  name               = "labor-law-agent-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_deploy_trust.json
}

resource "aws_iam_role_policy_attachment" "github_deploy_admin" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# Plan role: pull requests, read-only plus state read and lock file write.
resource "aws_iam_role" "github_plan" {
  name               = "labor-law-agent-github-plan"
  assume_role_policy = data.aws_iam_policy_document.github_plan_trust.json
}

resource "aws_iam_role_policy_attachment" "github_plan_readonly" {
  role       = aws_iam_role.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Permissions per Terraform S3 backend docs (use_lockfile section).
data "aws_iam_policy_document" "github_plan_state" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.terraform_state.arn]
  }
  statement {
    actions = ["s3:GetObject"]
    resources = [
      local.state_object_arn, # state file
    ]
  }
  statement {
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      local.state_lock_arn, # native lock file
    ]
  }
}

resource "aws_iam_role_policy" "github_plan_state" {
  name   = "terraform-state-access"
  role   = aws_iam_role.github_plan.id
  policy = data.aws_iam_policy_document.github_plan_state.json
}
