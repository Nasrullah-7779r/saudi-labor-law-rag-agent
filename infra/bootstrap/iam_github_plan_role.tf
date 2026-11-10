# Plan role: pull requests, read-only plus state read and lock file write.
resource "aws_iam_role" "github_plan" {
  name               = "saudi-labor-law-rag-agent-github-plan"
  assume_role_policy = data.aws_iam_policy_document.github_trust["plan"].json
}

resource "aws_iam_role_policy_attachment" "github_plan_readonly" {
  role       = aws_iam_role.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# ReadOnlyAccess already covers reading the bucket and state object; plan only
# additionally needs to write/delete the native lock file (Terraform S3
# backend docs, use_lockfile section).
data "aws_iam_policy_document" "github_plan_state" {
  statement {
    actions = ["s3:PutObject", "s3:DeleteObject"]
    resources = [
      local.state_lock_arn, # native lock file for infra/live state
    ]
  }
}

resource "aws_iam_role_policy" "github_plan_state" {
  name   = "terraform-state-access"
  role   = aws_iam_role.github_plan.id
  policy = data.aws_iam_policy_document.github_plan_state.json
}
