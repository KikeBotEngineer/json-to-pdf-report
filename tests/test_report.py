import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import ReportRequest

client = TestClient(app)
SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.json"


def ticket(**overrides):
    t = {
        "id": "TCK-1",
        "status": "resolved",
        "priority": "high",
        "category": "billing",
        "created_at": "2026-01-03T09:00:00Z",
        "resolved_at": "2026-01-03T12:00:00Z",
    }
    return t | overrides


def request(*tickets):
    return {
        "title": "Test",
        "period": {"start": "2026-01-01", "end": "2026-01-31"},
        "tickets": list(tickets) or [ticket()],
    }


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_contract_accepts_valid_request():
    ReportRequest.model_validate(request())


@pytest.mark.parametrize(
    "bad",
    [
        ticket(resolved_at=None),
        ticket(status="closed", resolved_at=None),
        ticket(resolved_at="2026-01-03T08:00:00Z"),
        ticket(status="unknown"),
    ],
    ids=["resolved-without-date", "closed-without-date", "resolved-before-created", "bad-status"],
)
def test_contract_rejects_invalid_ticket(bad):
    with pytest.raises(ValidationError):
        ReportRequest.model_validate(request(bad))


def test_contract_rejects_inverted_period():
    body = request() | {"period": {"start": "2026-02-01", "end": "2026-01-01"}}
    with pytest.raises(ValidationError):
        ReportRequest.model_validate(body)


def test_metrics_small_case():
    from app.metrics import PriorityRow, compute

    req = ReportRequest.model_validate(
        request(
            ticket(id="A", priority="high", resolved_at="2026-01-03T11:00:00Z"),  # 2 h
            ticket(
                id="B", status="closed", priority="low", resolved_at="2026-01-03T13:00:00Z"
            ),  # 4 h
            ticket(id="C", priority="high", resolved_at="2026-01-03T15:00:00Z"),  # 6 h
            ticket(id="D", status="open", priority="medium", resolved_at=None),
            ticket(id="E", status="in_progress", priority="critical", resolved_at=None),
        )
    )
    m, df = compute(req)

    assert (m.total, m.open, m.resolved) == (5, 2, 3)
    assert m.pct_resolved == pytest.approx(60.0)
    assert m.mean_hours == pytest.approx(4.0)
    assert m.median_hours == pytest.approx(4.0)
    assert m.p90_hours == pytest.approx(5.6)  # linear interpolation over [2, 4, 6]
    assert m.by_priority == [
        PriorityRow("low", 1, pytest.approx(4.0)),
        PriorityRow("medium", 1, None),
        PriorityRow("high", 2, pytest.approx(4.0)),
        PriorityRow("critical", 1, None),
    ]
    assert len(df) == 5


def test_report_end_to_end():
    r = client.post("/report", json=json.loads(SAMPLE.read_text(encoding="utf-8")))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="report.pdf"'
    assert r.content.startswith(b"%PDF")
    assert len(re.findall(rb"/Type /Page[^s]", r.content)) >= 3


def test_report_rejects_invalid_contract_with_422():
    r = client.post("/report", json=request(ticket(resolved_at=None)))
    assert r.status_code == 422


def test_report_survives_markup_in_title():
    r = client.post("/report", json=request() | {"title": "<b>Q1 & <unclosed"})
    assert r.status_code == 200


def test_report_rejects_large_body_by_content_length():
    body = b"x" * (5 * 1024 * 1024 + 1)
    r = client.post("/report", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json() == {"detail": "payload too large"}


def test_report_rejects_large_chunked_body():
    def chunks():
        for _ in range(6):
            yield b" " * (1024 * 1024)

    r = client.post("/report", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json() == {"detail": "payload too large"}
