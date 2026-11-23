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


def test_report_accepts_naive_and_aware_mix():
    t = ticket(created_at="2026-01-03T09:00:00", resolved_at="2026-01-03T12:00:00Z")
    r = client.post("/report", json=request(t))
    assert r.status_code == 200


def test_contract_rejects_naive_resolved_before_aware_created():
    t = ticket(created_at="2026-01-03T09:00:00+00:00", resolved_at="2026-01-03T08:00:00")
    with pytest.raises(ValidationError):
        ReportRequest.model_validate(request(t))


@pytest.mark.parametrize(
    "created_at",
    ["2025-12-31T23:59:59Z", "2026-02-01T00:00:00Z", "2026-01-31T20:00:00-05:00"],
    ids=["before-start", "after-end", "after-end-in-utc"],
)
def test_report_rejects_ticket_outside_period_with_422(created_at):
    t = ticket(created_at=created_at, resolved_at="2026-02-03T00:00:00Z")
    r = client.post("/report", json=request(t))
    assert r.status_code == 422


def test_contract_accepts_ticket_resolved_after_period():
    t = ticket(created_at="2026-01-31T10:00:00Z", resolved_at="2026-02-05T10:00:00Z")
    ReportRequest.model_validate(request(t))


def test_report_rejects_duplicate_ids_with_422():
    r = client.post("/report", json=request(ticket(id="A"), ticket(id="B"), ticket(id="A")))
    assert r.status_code == 422
    assert "duplicate ticket ids: A" in r.text


def test_contract_rejects_inverted_period():
    body = request() | {"period": {"start": "2026-02-01", "end": "2026-01-01"}}
    with pytest.raises(ValidationError):
        ReportRequest.model_validate(body)


def test_contract_accepts_leap_year_period():
    t = ticket(created_at="2024-12-31T09:00:00Z", resolved_at="2024-12-31T12:00:00Z")
    body = request(t) | {"period": {"start": "2024-01-01", "end": "2024-12-31"}}
    ReportRequest.model_validate(body)


def test_report_rejects_overlong_period_with_422():
    body = request() | {"period": {"start": "0001-01-01", "end": "9999-12-31"}}
    r = client.post("/report", json=body)
    assert r.status_code == 422


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


@pytest.mark.parametrize("category", [r"$\foo$", r"$a^^b$", "costs $5 / $10"])
def test_report_survives_mathtext_in_category(category):
    r = client.post("/report", json=request(ticket(category=category)))
    assert r.status_code == 200


def test_report_rejects_large_body_by_content_length():
    body = b"x" * (5 * 1024 * 1024 + 1)
    r = client.post("/report", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json() == {"detail": "payload too large"}


@pytest.mark.parametrize("length", ["abc", "-1", ""])
def test_report_rejects_invalid_content_length_with_400(length):
    r = client.post(
        "/report",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": length},
    )
    assert r.status_code == 400


def test_report_rejects_large_chunked_body():
    def chunks():
        for _ in range(6):
            yield b" " * (1024 * 1024)

    r = client.post("/report", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json() == {"detail": "payload too large"}
