# Deploy role: main branch only, runs `terraform apply`.
# AdministratorAccess is a deliberate bootstrap shortcut; scope it down once
# the live stack's resource set is known.
resource "aws_iam_role" "github_deploy" {
  name               = "saudi-labor-law-rag-agent-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_trust["deploy"].json
}

resource "aws_iam_role_policy_attachment" "github_deploy_admin" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
