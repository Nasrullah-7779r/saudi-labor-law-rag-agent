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
}

# One trust policy per CI role; each accepts a single exact GitHub `sub`.
locals {
  github_role_subs = {
    deploy = local.main_branch_sub
    plan   = local.pull_request_sub
  }
}

data "aws_iam_policy_document" "github_trust" {
  for_each = local.github_role_subs

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
      values   = [each.value]
    }
  }
}
