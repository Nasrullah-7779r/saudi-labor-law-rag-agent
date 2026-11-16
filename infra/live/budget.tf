# Cost backstop: monthly account cost budget with email alerts, and at 100% an
# automatic Budgets action that attaches a deny-Bedrock policy to the chat Lambda role.
# This is the last line of defence behind the usage guard (per-IP quota + daily token budget).
# Docs: registry.terraform.io/providers/hashicorp/aws/6.x budgets_budget / budgets_budget_action;
# https://docs.aws.amazon.com/cost-management/latest/userguide/billing-example-policies.html
#
# Account-wide on purpose (no Service cost_filter): third-party Bedrock models can bill
# under AWS Marketplace rather than "Amazon Bedrock", and a filter would miss them.
#
# Recovery after a trip: detach the policy (or reset the action) in the Budgets console;
# it does not auto-revert when the month rolls over.

locals {
  budget_name = "${local.name}-monthly-cost"
}

resource "aws_budgets_budget" "monthly_cost" {
  name         = local.budget_name
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_cost_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }
}

# Attached to the chat Lambda role by the budget action. An explicit Deny wins over the
# role's inline Allow; Converse/ConverseStream authorise as these two actions.
data "aws_iam_policy_document" "deny_bedrock" {
  statement {
    effect    = "Deny"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "deny_bedrock" {
  name        = "${local.name}-deny-bedrock"
  description = "Attached by the AWS Budgets action when the monthly cost budget is exceeded."
  policy      = data.aws_iam_policy_document.deny_bedrock.json
}

# Role AWS Budgets assumes to run the action, scoped to this account's budgets.
data "aws_iam_policy_document" "budgets_action_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:budgets::${data.aws_caller_identity.current.account_id}:budget/*"]
    }
  }
}

resource "aws_iam_role" "budgets_action" {
  name               = "${local.name}-budgets-action"
  assume_role_policy = data.aws_iam_policy_document.budgets_action_trust.json
}

data "aws_iam_policy_document" "budgets_action" {
  statement {
    actions = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
    resources = [
      aws_iam_role.chat_lambda.arn, # the only role the action may touch
    ]
    condition {
      test     = "ArnEquals"
      variable = "iam:PolicyARN"
      values   = [aws_iam_policy.deny_bedrock.arn]
    }
  }
}

resource "aws_iam_role_policy" "budgets_action" {
  name   = "attach-deny-bedrock"
  role   = aws_iam_role.budgets_action.id
  policy = data.aws_iam_policy_document.budgets_action.json
}

resource "aws_budgets_budget_action" "deny_bedrock" {
  budget_name        = aws_budgets_budget.monthly_cost.name
  action_type        = "APPLY_IAM_POLICY"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budgets_action.arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    iam_action_definition {
      policy_arn = aws_iam_policy.deny_bedrock.arn
      roles      = [aws_iam_role.chat_lambda.name]
    }
  }

  subscriber {
    address           = var.budget_alert_email
    subscription_type = "EMAIL"
  }

  depends_on = [aws_iam_role_policy.budgets_action]
}
