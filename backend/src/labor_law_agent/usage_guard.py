"""Usage guard: per-IP daily question quota and a global daily token budget, in DynamoDB.

One table, partition key ``pk`` (S), TTL attribute ``expires_at``. Items are per UTC day:
``ip#<date>#<ip>`` holds ``questions``; ``global#<date>`` holds ``tokens``.

- The IP quota is a conditional atomic ``ADD`` (``attribute_not_exists OR questions < :limit``);
  a failed condition raises ``ConditionalCheckFailedException`` and nothing is incremented.
- The token budget is a soft cap: admission reads the day's total (strongly consistent) and
  actual usage is ``ADD``-ed after the turn, so concurrent turns can overshoot it.

Docs: DynamoDB UpdateItem conditional writes / atomic counters / ReturnValues
(https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html),
TTL (https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from botocore.exceptions import ClientError
from pydantic import BaseModel

QuotaReason = Literal["ip_quota", "global_budget"]
# Keep items a day past their window so late `record` calls still land on the same item.
_TTL_GRACE = timedelta(days=1)


class QuotaExceeded(Exception):
    def __init__(self, reason: QuotaReason) -> None:
        super().__init__(reason)
        self.reason: QuotaReason = reason


class Admission(BaseModel):
    remaining_questions: int


class UsageGuard(Protocol):
    def admit(self, source_ip: str) -> Admission:
        """Count one question for ``source_ip``; raise ``QuotaExceeded`` if over a limit."""
        ...

    def record(self, tokens: int) -> None:
        """Add a finished turn's actual token usage to the day's global total."""
        ...


class UsageLimits(BaseModel):
    ip_daily_question_quota: int
    global_daily_token_budget: int


class DynamoUsageGuard:
    def __init__(
        self,
        table_name: str,
        limits: UsageLimits,
        dynamodb_client: Any,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._table = table_name
        self._limits = limits
        self._ddb = dynamodb_client
        self._now = now

    def _day(self) -> tuple[str, int]:
        now = self._now()
        day_end = datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1)
        return now.date().isoformat(), int((day_end + _TTL_GRACE).timestamp())

    def admit(self, source_ip: str) -> Admission:
        day, expires_at = self._day()
        # Global budget first, so an exhausted demo doesn't also burn the caller's IP quota.
        item = self._ddb.get_item(
            TableName=self._table,
            Key={"pk": {"S": f"global#{day}"}},
            ConsistentRead=True,
        ).get("Item", {})
        if int(item.get("tokens", {"N": "0"})["N"]) >= self._limits.global_daily_token_budget:
            raise QuotaExceeded("global_budget")

        try:
            updated = self._ddb.update_item(
                TableName=self._table,
                Key={"pk": {"S": f"ip#{day}#{source_ip}"}},
                UpdateExpression="ADD questions :one SET expires_at = :exp",
                ConditionExpression="attribute_not_exists(questions) OR questions < :limit",
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":exp": {"N": str(expires_at)},
                    ":limit": {"N": str(self._limits.ip_daily_question_quota)},
                },
                ReturnValues="UPDATED_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise QuotaExceeded("ip_quota") from e
            raise
        asked = int(updated["Attributes"]["questions"]["N"])
        return Admission(remaining_questions=max(self._limits.ip_daily_question_quota - asked, 0))

    def record(self, tokens: int) -> None:
        if tokens <= 0:
            return
        day, expires_at = self._day()
        self._ddb.update_item(
            TableName=self._table,
            Key={"pk": {"S": f"global#{day}"}},
            UpdateExpression="ADD tokens :t SET expires_at = :exp",
            ExpressionAttributeValues={
                ":t": {"N": str(tokens)},
                ":exp": {"N": str(expires_at)},
            },
        )
