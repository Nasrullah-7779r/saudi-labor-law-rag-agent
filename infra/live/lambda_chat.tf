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

locals {
  # Cross-Region inference profile ids carry a geo prefix; the rest are on-demand model ids.
  chat_model_profile_prefixes = ["us", "eu", "apac", "global"]
  chat_model_arns = flatten([
    for id in var.chat_model_allowlist : (
      contains(local.chat_model_profile_prefixes, split(".", id)[0])
      ? [
        "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${id}",
        "arn:aws:bedrock:*::foundation-model/${join(".", slice(split(".", id), 1, length(split(".", id))))}",
      ]
      : ["arn:aws:bedrock:${var.aws_region}::foundation-model/${id}"]
    )
  ])
}

# Active chat model id, switched at runtime with `aws ssm put-parameter --overwrite`
# (see README). Terraform only seeds it; the backend accepts only allowlisted ids.
resource "aws_ssm_parameter" "chat_model_id" {
  name        = "/${local.name}/chat-model-id"
  description = "Active Bedrock chat model id; must be in chat_model_allowlist."
  type        = "String"
  value       = var.chat_model_allowlist[0]

  lifecycle {
    ignore_changes = [value]
  }
}

data "aws_iam_policy_document" "chat_lambda" {
  statement {
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "${aws_cloudwatch_log_group.chat_lambda.arn}:*", # chat Lambda log streams
    ]
  }

  # Converse/ConverseStream are authorised as InvokeModel/InvokeModelWithResponseStream.
  statement {
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = concat(
      local.chat_model_arns, # allowlisted chat models (on-demand, or inference profile + destination models)
      [
        "arn:aws:bedrock:${var.aws_region}::foundation-model/cohere.embed-multilingual-v3", # query embeddings
      ],
    )
  }

  statement {
    actions = ["ssm:GetParameter"]
    resources = [
      aws_ssm_parameter.chat_model_id.arn, # active chat model id
    ]
  }

  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.pinecone_api_key.arn, # Pinecone API key
    ]
  }

  statement {
    actions = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [
      aws_dynamodb_table.usage.arn, # usage-guard counters
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
      FRONTEND_ORIGIN              = "https://${aws_cloudfront_distribution.frontend.domain_name}"
      CHAT_MODEL_ID                = var.chat_model_allowlist[0]
      CHAT_MODEL_PARAMETER_NAME    = aws_ssm_parameter.chat_model_id.name
      CHAT_MODEL_ALLOWLIST         = join(",", var.chat_model_allowlist)
      CHAT_MODEL_PROVIDER          = "bedrock_converse"
      CHAT_MAX_OUTPUT_TOKENS       = tostring(var.chat_max_output_tokens)
      PINECONE_INDEX_NAME          = var.pinecone_index_name
      PINECONE_API_KEY_SECRET_ID   = aws_secretsmanager_secret.pinecone_api_key.name
      USAGE_TABLE_NAME             = aws_dynamodb_table.usage.name
      IP_DAILY_QUESTION_QUOTA      = tostring(var.ip_daily_question_quota)
      GLOBAL_DAILY_TOKEN_BUDGET    = tostring(var.global_daily_token_budget)
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
