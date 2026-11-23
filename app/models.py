from collections import Counter
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# One chart point per day; an unbounded period lets one request pin a worker.
MAX_PERIOD_DAYS = 366


class Status(StrEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class Priority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Period(Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def check_order(self):
        if self.start > self.end:
            raise ValueError("period.start must be <= period.end")
        if (self.end - self.start).days >= MAX_PERIOD_DAYS:
            raise ValueError(f"period must span at most {MAX_PERIOD_DAYS} days")
        return self


class Ticket(Strict):
    id: Annotated[str, Field(min_length=1, max_length=50)]
    status: Status
    priority: Priority
    category: Annotated[str, Field(min_length=1, max_length=50)]
    created_at: datetime
    resolved_at: datetime | None = None

    @field_validator("created_at", "resolved_at")
    @classmethod
    def assume_utc(cls, v: datetime | None) -> datetime | None:
        # Naive timestamps are UTC (same as pd.to_datetime(utc=True) in metrics).
        # Without this, comparing naive vs aware raises TypeError -> 500.
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @model_validator(mode="after")
    def check_resolution(self):
        if self.resolved_at is None:
            if self.status in (Status.resolved, Status.closed):
                raise ValueError(f"resolved_at is required when status is {self.status}")
        elif self.resolved_at < self.created_at:
            raise ValueError("resolved_at must be >= created_at")
        return self


class ReportRequest(Strict):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    period: Period
    tickets: Annotated[list[Ticket], Field(min_length=1, max_length=10_000)]

    @model_validator(mode="after")
    def check_tickets_in_period(self):
        # Charts bucket by UTC day inside the period; metrics count every ticket.
        # A ticket outside the period would make the two disagree silently.
        start, end = self.period.start, self.period.end
        outside = [
            t.id for t in self.tickets if not start <= t.created_at.astimezone(UTC).date() <= end
        ]
        if outside:
            sample = ", ".join(outside[:5])
            raise ValueError(f"{len(outside)} ticket(s) created outside the period: {sample}")
        return self

    @model_validator(mode="after")
    def check_unique_ids(self):
        counts = Counter(t.id for t in self.tickets)
        dupes = [i for i, n in counts.items() if n > 1]
        if dupes:
            raise ValueError(f"duplicate ticket ids: {', '.join(dupes[:5])}")
        return self
