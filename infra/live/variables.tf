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

variable "chat_lambda_reserved_concurrency" {
  description = "Reserved concurrency for the chat Lambda (cost/abuse cap). -1 = no reservation. Lambda keeps 100 executions unreserved, so a value > 0 needs an account limit above 100; this account is at 10 (Nov 2026). Set to 5 once a quota increase lands."
  type        = number
  default     = -1
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
