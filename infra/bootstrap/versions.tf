# One-time, human-applied stack. Uses LOCAL state on purpose: it creates the
# remote-state bucket and the OIDC roles CI needs, so CI cannot apply it.
terraform {
  # use_lockfile (native S3 locking) is GA since Terraform 1.11.
  required_version = ">= 1.11, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
