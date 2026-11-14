output "api_url" {
  description = "Invoke URL of the prod stage (append /chat or /health)."
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "backend_ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "chat_lambda_function_name" {
  value = aws_lambda_function.chat.function_name
}

output "pinecone_api_key_secret_name" {
  value = aws_secretsmanager_secret.pinecone_api_key.name
}

output "frontend_url" {
  description = "Public chat page served through CloudFront."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.id
}

output "frontend_distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}
