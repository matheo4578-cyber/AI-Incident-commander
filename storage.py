from __future__ import annotations

import json
import os
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError

from incident_commander.models import IncidentReport


class ReportRepository(Protocol):
    def save(self, report: IncidentReport) -> None: ...

    def get(self, incident_id: str) -> IncidentReport | None: ...


class MemoryReportRepository:
    def __init__(self) -> None:
        self._reports: dict[str, IncidentReport] = {}

    def save(self, report: IncidentReport) -> None:
        self._reports[report.incident_id] = report

    def get(self, incident_id: str) -> IncidentReport | None:
        return self._reports.get(incident_id)


class AwsReportRepository:
    def __init__(
        self,
        table_name: str,
        bucket_name: str,
        *,
        table: Any | None = None,
        s3: Any | None = None,
    ) -> None:
        self.table = table or boto3.resource("dynamodb").Table(table_name)
        self.s3 = s3 or boto3.client("s3")
        self.bucket_name = bucket_name

    def save(self, report: IncidentReport) -> None:
        payload = report.model_dump(mode="json")
        item = json.loads(json.dumps(payload), parse_float=str)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(incident_id)",
            )
            canonical = payload
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            existing = self.table.get_item(
                Key={"incident_id": report.incident_id}, ConsistentRead=True
            ).get("Item")
            if not existing:
                raise RuntimeError("existing report could not be reconciled") from error
            canonical = IncidentReport.model_validate(existing).model_dump(mode="json")

        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=f"reports/{report.incident_id}.json",
                Body=json.dumps(canonical, indent=2).encode(),
                ContentType="application/json",
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "PreconditionFailed":
                raise

    def get(self, incident_id: str) -> IncidentReport | None:
        response = self.table.get_item(Key={"incident_id": incident_id}, ConsistentRead=True)
        item = response.get("Item")
        return IncidentReport.model_validate(item) if item else None


def repository_from_env() -> ReportRepository:
    table = os.getenv("REPORTS_TABLE")
    bucket = os.getenv("REPORTS_BUCKET")
    if table and bucket:
        return AwsReportRepository(table, bucket)
    return MemoryReportRepository()
