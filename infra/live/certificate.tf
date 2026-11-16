# ACM cert for the frontend domain. CloudFront needs it in us-east-1 (= var.aws_region).
# DNS is at Hostinger, so the validation CNAME is added there by hand from the
# `frontend_cert_validation_records` output (first apply: -target=aws_acm_certificate.frontend).
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/acm_certificate_validation

resource "aws_acm_certificate" "frontend" {
  domain_name       = var.frontend_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Blocks the apply until ACM sees the validation CNAME and issues the cert.
resource "aws_acm_certificate_validation" "frontend" {
  certificate_arn = aws_acm_certificate.frontend.arn
}
