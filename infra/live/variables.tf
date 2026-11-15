variable "aws_region" {
  description = "Region for project resources."
  type        = string
  default     = "us-east-1"
}

variable "backend_image_tag" {
  description = "Backend image tag used when the Lambda is first created. Later code updates go through `aws lambda update-function-code` in the deploy workflow (image_uri is ignored by Terraform after creation)."
  type        = string
  default     = "bootstrap"
}

variable "api_throttle_rate_limit" {
  description = "API Gateway stage steady-state request rate (requests/second)."
  type        = number
  default     = 2
}

variable "api_throttle_burst_limit" {
  description = "API Gateway stage burst limit (requests)."
  type        = number
  default     = 5
}

variable "chat_model_allowlist" {
  description = "Bedrock chat model ids the chat Lambda may switch to at runtime (via the chat-model-id SSM parameter). IAM is granted for exactly these; the first entry seeds the parameter and is the env fallback."
  type        = list(string)
  # Plain ids are on-demand in-Region models. Ids with a geo prefix (us./eu./apac./global.)
  # are cross-Region inference profiles and get the profile ARN plus the destination model ARNs:
  #   "us.anthropic.claude-haiku-5-5",
  default = [
    "zai.glm-4.7-flash", # on-demand in us-east-1, Converse tool use, no access request
    "zai.glm-4.7",
  ]

  validation {
    condition     = length(var.chat_model_allowlist) > 0
    error_message = "chat_model_allowlist needs at least one model id."
  }
}

variable "chat_max_output_tokens" {
  description = "max_tokens per model call."
  type        = number
  default     = 1024
}

variable "pinecone_index_name" {
  description = "Pinecone index holding the ingested law (same as the ingest workflow's PINECONE_INDEX_NAME)."
  type        = string
  default     = "saudi-labor-law"
}

variable "ip_daily_question_quota" {
  description = "Questions per source IP per UTC day."
  type        = number
  default     = 20
}

variable "global_daily_token_budget" {
  description = "Soft cap on model tokens (input + output) across the demo per UTC day."
  type        = number
  default     = 2000000
}
