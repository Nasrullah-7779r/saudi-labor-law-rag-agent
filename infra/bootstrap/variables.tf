variable "aws_region" {
  description = "Region for the state bucket and all project resources."
  type        = string
  default     = "us-east-1"
}

variable "github_oidc_sub_prefix" {
  description = <<-EOT
    Prefix of the GitHub OIDC `sub` claim for this repo, without the trailing
    context. Repos created after 2026-07-15 use the immutable form
    repo:OWNER@OWNER-ID/REPO@REPO-ID (docs.github.com, OIDC reference).
    Read the actual value with:
      gh api repos/OWNER/REPO/actions/oidc/customization/sub --jq .sub_claim_prefix
  EOT
  type        = string
  default     = "repo:Nasrullah-7779r@134123519/saudi-labor-law-rag-agent@1452239139"
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
