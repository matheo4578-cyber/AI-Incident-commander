import json
from contextlib import suppress

from botocore.exceptions import ClientError

from incident_commander.models import IncidentReport
from incident_commander.storage import AwsReportRepository
from incident_commander.worker import process_sqs_message


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}

    def put_item(self, *, Item: dict, ConditionExpression: str) -> None:
        assert ConditionExpression == "attribute_not_exists(incident_id)"
        incident_id = Item["incident_id"]
        if incident_id in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
                "PutItem",
            )
        self.items[incident_id] = Item

    def get_item(self, *, Key: dict, ConsistentRead: bool = False) -> dict:
        assert ConsistentRead
        item = self.items.get(Key["incident_id"])
        return {"Item": item} if item else {}


class FakeS3:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_once = fail_once

    def put_object(self, **kwargs) -> None:
        if self.fail_once:
            self.fail_once = False
            raise ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "retry"}},
                "PutObject",
            )
        assert kwargs["IfNoneMatch"] == "*"
        key = kwargs["Key"]
        if key in self.objects:
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed", "Message": "exists"}},
                "PutObject",
            )
        self.objects[key] = kwargs["Body"]


def make_report() -> IncidentReport:
    return IncidentReport(
        incident_id="inc-immutable-123",
        service="checkout-api",
        status="completed",
        severity="high",
        summary="Investigated",
        probable_root_cause="Bad deployment",
        confidence=0.8,
        evidence=["version=v42"],
        recommendations=["Request approval to roll back"],
        timeline=["triage completed"],
        agents_run=["triage", "commander"],
    )


def test_aws_repository_preserves_first_report_on_duplicate_save() -> None:
    table = FakeTable()
    s3 = FakeS3()
    repository = AwsReportRepository("reports", "archive", table=table, s3=s3)
    report = make_report()

    repository.save(report)
    repository.save(report.model_copy(update={"summary": "Attacker replacement"}))

    assert table.items[report.incident_id]["summary"] == "Investigated"
    key = f"reports/{report.incident_id}.json"
    assert set(s3.objects) == {key}
    assert b'"summary": "Investigated"' in s3.objects[key]


def test_aws_repository_repairs_s3_after_partial_failure_with_canonical_report() -> None:
    table = FakeTable()
    s3 = FakeS3(fail_once=True)
    repository = AwsReportRepository("reports", "archive", table=table, s3=s3)
    report = make_report()

    with suppress(ClientError):
        repository.save(report)
    repository.save(report.model_copy(update={"summary": "Different retry output"}))

    key = f"reports/{report.incident_id}.json"
    assert table.items[report.incident_id]["summary"] == "Investigated"
    assert b'"summary": "Investigated"' in s3.objects[key]


class FakeWorkflow:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, incident) -> IncidentReport:
        self.calls += 1
        return make_report().model_copy(update={"incident_id": incident.incident_id})


def test_sqs_retry_repairs_s3_after_dynamodb_success() -> None:
    table = FakeTable()
    s3 = FakeS3(fail_once=True)
    repository = AwsReportRepository("reports", "archive", table=table, s3=s3)
    workflow = FakeWorkflow()
    body = json.dumps(
        {
            "incident_id": "inc-immutable-123",
            "service": "checkout-api",
            "title": "Errors",
            "description": "Requests fail",
        }
    )

    with suppress(ClientError):
        process_sqs_message(body, workflow, repository)
    repaired = process_sqs_message(body, workflow, repository)

    key = f"reports/{repaired.incident_id}.json"
    assert key in s3.objects
    assert workflow.calls == 1
