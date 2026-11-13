# Chat API Lambda: container image running FastAPI behind Lambda Web Adapter
# (https://github.com/awslabs/aws-lambda-web-adapter) in response-stream mode.

data "aws_caller_identity" "current" {}

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

  # Converse/ConverseStream are authorised as InvokeModel/InvokeModelWithResponseStream.
  # A cross-Region inference profile needs the profile ARN plus the foundation model in every
  # destination Region it routes to (https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html).
  statement {
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.chat_model_id}", # chat model inference profile
      "arn:aws:bedrock:*::foundation-model/${local.chat_foundation_model_id}",                                                   # chat model in profile destination Regions
      "arn:aws:bedrock:${var.aws_region}::foundation-model/cohere.embed-multilingual-v3",                                        # query embeddings
    ]
  }

  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.pinecone_api_key.arn, # Pinecone API key
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
      CHAT_MODEL_ID                = var.chat_model_id
      CHAT_MODEL_PROVIDER          = "bedrock_converse"
      CHAT_MAX_OUTPUT_TOKENS       = tostring(var.chat_max_output_tokens)
      PINECONE_INDEX_NAME          = var.pinecone_index_name
      PINECONE_API_KEY_SECRET_ID   = aws_secretsmanager_secret.pinecone_api_key.name
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
