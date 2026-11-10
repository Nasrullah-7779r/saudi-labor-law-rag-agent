terraform {
  required_version = ">= 1.11, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Partial config: bucket comes from -backend-config in CI/locally
  # (see README "Bootstrap"). Native S3 locking, no DynamoDB table.
  backend "s3" {
    key          = "live/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
