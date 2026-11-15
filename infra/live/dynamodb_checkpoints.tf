# Agent conversation checkpoints (langgraph-checkpoint-aws DynamoDBSaver). Schema per the package:
# string PK/SK keys, TTL on `ttl` (set from ttl_seconds = 7 days in the app).
# https://github.com/langchain-ai/langchain-aws/tree/main/libs/langgraph-checkpoint-aws

resource "aws_dynamodb_table" "checkpoints" {
  name         = "${local.name}-checkpoints"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
