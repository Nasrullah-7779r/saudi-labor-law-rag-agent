variable "aws_region" {
  description = "Region for the state bucket and all project resources."
  type        = string
  default     = "us-east-1"
}

variable "github_repository" {
  description = "GitHub repo (owner/name) allowed to assume the CI roles."
  type        = string
  default     = "Nasrullah-7779r/saudi-labor-law-rag-agent"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform remote state."
  type        = string
}

variable "state_key" {
  description = "State object key used by infra/live (must match its backend config)."
  type        = string
  default     = "live/terraform.tfstate"
}
