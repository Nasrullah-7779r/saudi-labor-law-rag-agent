# Ingest role: main branch only, used by the manual `ingest` workflow to embed the
# BOE Labor Law with Bedrock Cohere and upsert into Pinecone. No Terraform access.
resource "aws_iam_role" "github_ingest" {
  name               = "saudi-labor-law-rag-agent-github-ingest"
  assume_role_policy = data.aws_iam_policy_document.github_trust["ingest"].json
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "github_ingest" {
  statement {
    actions = ["bedrock:InvokeModel"]
    resources = [
      # Cohere Embed Multilingual v3, on-demand foundation model
      "arn:aws:bedrock:${var.aws_region}::foundation-model/cohere.embed-multilingual-v3",
    ]
  }
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      # Pinecone API key (secret created in infra/live; "-*" is the random ARN suffix)
      "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:saudi-labor-law-rag-agent/pinecone-api-key-*",
    ]
  }
}

resource "aws_iam_role_policy" "github_ingest" {
  name   = "ingest"
  role   = aws_iam_role.github_ingest.id
  policy = data.aws_iam_policy_document.github_ingest.json
}
