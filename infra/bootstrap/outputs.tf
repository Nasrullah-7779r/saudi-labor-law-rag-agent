output "state_bucket_name" {
  value = aws_s3_bucket.terraform_state.bucket
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "github_plan_role_arn" {
  value = aws_iam_role.github_plan.arn
}


output "github_ingest_role_arn" {
  value = aws_iam_role.github_ingest.arn
}
