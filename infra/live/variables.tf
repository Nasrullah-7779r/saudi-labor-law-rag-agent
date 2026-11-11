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
