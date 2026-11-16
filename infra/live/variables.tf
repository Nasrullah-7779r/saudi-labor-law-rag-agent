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

variable "chat_model_id" {
  description = "Initial Bedrock chat model id: seeds the chat-model-id SSM parameter and is the Lambda's env fallback. Switch later with put-parameter (README); IAM allows any Bedrock model or inference profile."
  type        = string
  # GLM 4.7 Flash: on-demand in us-east-1, Converse tool use, no access request.
  default = "zai.glm-4.7-flash"
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

variable "frontend_domain" {
  description = "Custom domain for the frontend (DNS at Hostinger, CNAME to CloudFront)."
  type        = string
  default     = "nizam.mnasrullah.dev"
}

variable "monthly_cost_budget_usd" {
  description = "Hard monthly account cost budget (USD). Email alerts at 50/80/100%; at 100% Bedrock is denied to the chat Lambda."
  type        = number
  default     = 5
}

variable "budget_alert_email" {
  description = "Recipient of budget alerts. Set via TF_VAR_budget_alert_email (GitHub repo variable BUDGET_ALERT_EMAIL in CI)."
  type        = string
}
