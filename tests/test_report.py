import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import ReportRequest

client = TestClient(app)


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
