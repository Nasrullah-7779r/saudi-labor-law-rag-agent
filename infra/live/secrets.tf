# Pinecone API key. Terraform owns the secret container only; the value is set
# out of band so it never lands in state:
#   aws secretsmanager put-secret-value --secret-id saudi-labor-law-rag-agent/pinecone-api-key --secret-string '<key>'
resource "aws_secretsmanager_secret" "pinecone_api_key" {
  name        = "${local.name}/pinecone-api-key"
  description = "Pinecone API key (plain string) for the labor law index."
}
