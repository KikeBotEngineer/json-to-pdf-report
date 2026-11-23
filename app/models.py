from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
        return self


class Ticket(Strict):
    id: Annotated[str, Field(min_length=1, max_length=50)]
    status: Status
    priority: Priority
    category: Annotated[str, Field(min_length=1, max_length=50)]
    created_at: datetime
    resolved_at: datetime | None = None

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
