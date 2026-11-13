locals {
  name = "saudi-labor-law-rag-agent"
  # Inference profile id minus its geo prefix, e.g. "us.anthropic.x" -> "anthropic.x".
  chat_foundation_model_id = join(".", slice(split(".", var.chat_model_id), 1, length(split(".", var.chat_model_id))))
}
