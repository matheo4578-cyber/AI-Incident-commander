import inspect
import json
from threading import Event
from typing import Any

from incident_commander import worker
from incident_commander.models import IncidentReport
from incident_commander.worker import process_sqs_message, visibility_heartbeat


class FakeWorkflow:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, incident: Any) -> IncidentReport:
        self.calls += 1
        return IncidentReport(
            incident_id=incident.incident_id,
            service=incident.service,
            status="completed",
            severity="high",
            summary="Investigated",
            probable_root_cause="Database connection pool saturation",
            confidence=0.8,
            evidence=["connection pool exhausted"],
            recommendations=["Request approval to increase pool capacity"],
            timeline=["triage completed"],
            agents_run=["triage", "commander"],
            requires_human_approval=True,
        )


class FakeRepository:
    def __init__(self) -> None:
        self.saved: IncidentReport | None = None

    def save(self, report: IncidentReport) -> None:
        self.saved = report

    def get(self, incident_id: str) -> IncidentReport | None:
        del incident_id
        return self.saved


class FakeSQS:
    def __init__(self) -> None:
        self.extensions = 0
        self.called = Event()

    def change_message_visibility(self, **kwargs: Any) -> None:
        assert kwargs["VisibilityTimeout"] == 900
        self.extensions += 1
        self.called.set()


def test_worker_analyzes_and_persists_sqs_message() -> None:
    repository = FakeRepository()
    body = json.dumps(
        {
            "incident_id": "inc-123",
            "service": "orders-db",
            "title": "Pool exhausted",
            "description": "Connections unavailable",
            "logs": ["connection pool exhausted"],
            "metrics": {"db_connections_percent": 99},
            "source": "cloudwatch",
        }
    )

    report = process_sqs_message(body, FakeWorkflow(), repository)

    assert report.incident_id == "inc-123"
    assert repository.saved == report


def test_worker_skips_duplicate_incident_already_in_repository() -> None:
    repository = FakeRepository()
    workflow = FakeWorkflow()
    first = process_sqs_message(
        json.dumps(
            {
                "incident_id": "inc-123",
                "service": "checkout-api",
                "title": "Errors",
                "description": "Requests fail",
            }
        ),
        workflow,
        repository,
    )

    second = process_sqs_message(
        json.dumps(
            {
                "incident_id": "inc-123",
                "service": "checkout-api",
                "title": "Errors",
                "description": "Requests fail",
            }
        ),
        workflow,
        repository,
    )

    assert second == first
    assert workflow.calls == 1


def test_worker_receives_one_message_with_long_visibility_window() -> None:
    source = inspect.getsource(worker.run)

    assert "MaxNumberOfMessages=1" in source
    assert "VisibilityTimeout=900" in source


def test_visibility_heartbeat_extends_long_running_message() -> None:
    sqs = FakeSQS()

    with visibility_heartbeat(sqs, "queue", "receipt", interval_seconds=0.01):
        assert sqs.called.wait(1)

    assert sqs.extensions >= 1
