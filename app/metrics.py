from dataclasses import dataclass

import pandas as pd

from app.models import Priority, ReportRequest, Status

DONE = (Status.resolved, Status.closed)


@dataclass(frozen=True)
class PriorityRow:
    priority: str
    count: int
    mean_hours: float | None


@dataclass(frozen=True)
class Metrics:
    total: int
    open: int
    resolved: int
    pct_resolved: float
    mean_hours: float | None
    median_hours: float | None
    p90_hours: float | None
    by_priority: list[PriorityRow]


def to_frame(req: ReportRequest) -> pd.DataFrame:
    df = pd.DataFrame([t.model_dump() for t in req.tickets])
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["resolved_at"] = pd.to_datetime(df["resolved_at"], utc=True)
    df["hours"] = (df["resolved_at"] - df["created_at"]).dt.total_seconds() / 3600
    return df


def _num(x) -> float | None:
    return None if pd.isna(x) else float(x)


def compute(req: ReportRequest) -> tuple[Metrics, pd.DataFrame]:
    df = to_frame(req)
    done = df["status"].isin(DONE)
    hours = df.loc[done, "hours"]
    total = len(df)

    by_priority = []
    for p in Priority:
        rows = df[df["priority"] == p]
        by_priority.append(
            PriorityRow(
                p.value, len(rows), _num(rows.loc[rows["status"].isin(DONE), "hours"].mean())
            )
        )

    metrics = Metrics(
        total=total,
        open=total - int(done.sum()),
        resolved=int(done.sum()),
        pct_resolved=float(100 * done.sum() / total),
        mean_hours=_num(hours.mean()),
        median_hours=_num(hours.median()),
        p90_hours=_num(hours.quantile(0.9)),
        by_priority=by_priority,
    )
    return metrics, df
