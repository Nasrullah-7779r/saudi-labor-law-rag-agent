# Usage-guard counters: per-IP daily questions and the global daily token total.
# TTL on `expires_at` purges past days (https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html).

resource "aws_dynamodb_table" "usage" {
  name         = "${local.name}-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
