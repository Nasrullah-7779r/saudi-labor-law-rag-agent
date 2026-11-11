# Chat API Lambda: container image running FastAPI behind Lambda Web Adapter
# (https://github.com/awslabs/aws-lambda-web-adapter) in response-stream mode.

data "aws_iam_policy_document" "chat_lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "chat_lambda" {
  name               = "${local.name}-chat-lambda"
  assume_role_policy = data.aws_iam_policy_document.chat_lambda_trust.json
}

resource "aws_cloudwatch_log_group" "chat_lambda" {
  name              = "/aws/lambda/${local.name}-chat"
  retention_in_days = 14
}

data "aws_iam_policy_document" "chat_lambda" {
  statement {
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "${aws_cloudwatch_log_group.chat_lambda.arn}:*", # chat Lambda log streams
    ]
  }
}

resource "aws_iam_role_policy" "chat_lambda" {
  name   = "chat-lambda"
  role   = aws_iam_role.chat_lambda.id
  policy = data.aws_iam_policy_document.chat_lambda.json
}

resource "aws_lambda_function" "chat" {
  function_name = "${local.name}-chat"
  role          = aws_iam_role.chat_lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
  architectures = ["x86_64"]
  memory_size   = 1024
  timeout       = 120

  environment {
    variables = {
      AWS_LWA_INVOKE_MODE          = "response_stream"
      AWS_LWA_PORT                 = "8080"
      AWS_LWA_READINESS_CHECK_PATH = "/health"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.chat_lambda.name
  }

  lifecycle {
    # Code is rolled out by the deploy workflow (update-function-code), not Terraform.
    ignore_changes = [image_uri]
  }

  depends_on = [aws_iam_role_policy.chat_lambda]
}
