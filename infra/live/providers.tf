provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "saudi-labor-law-rag-agent"
      ManagedBy = "terraform"
    }
  }
}
