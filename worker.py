from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread
from typing import Any, Protocol

import boto3

from incident_commander.models import IncidentInput, IncidentReport
from incident_commander.storage import ReportRepository, repository_from_env
from incident_commander.workflow import IncidentWorkflow, build_workflow

LOGGER = logging.getLogger(__name__)


class WorkflowProtocol(Protocol):
    def analyze(self, incident: IncidentInput) -> IncidentReport: ...


def process_sqs_message(
    body: str, workflow: WorkflowProtocol, repository: ReportRepository
) -> IncidentReport:
    incident = IncidentInput.model_validate(json.loads(body))
    existing = repository.get(incident.incident_id)
    if existing is not None:
        repository.save(existing)
        return existing
    report = workflow.analyze(incident)
    repository.save(report)
    return report


@contextmanager
def visibility_heartbeat(
    sqs: Any,
    queue_url: str,
    receipt_handle: str,
    *,
    interval_seconds: float = 300,
) -> Iterator[None]:
    stop = Event()

    def extend_visibility() -> None:
        while not stop.is_set():
            try:
                sqs.change_message_visibility(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle,
                    VisibilityTimeout=900,
                )
            except Exception:
                LOGGER.exception("visibility_heartbeat_failed")
            if stop.wait(interval_seconds):
                break

    thread = Thread(target=extend_visibility, name="sqs-visibility-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


def run() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    queue_url = os.environ["INCIDENT_QUEUE_URL"]
    sqs = boto3.client("sqs")
    workflow: IncidentWorkflow = build_workflow(
        llm_mode=os.getenv("LLM_MODE", "deterministic"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )
    repository = repository_from_env()
    LOGGER.info("worker_started")
    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=900,
        )
        for message in response.get("Messages", []):
            try:
                with visibility_heartbeat(sqs, queue_url, message["ReceiptHandle"]):
                    report = process_sqs_message(message["Body"], workflow, repository)
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
                LOGGER.info("incident_completed id=%s", report.incident_id)
            except Exception:
                LOGGER.exception("incident_processing_failed")
