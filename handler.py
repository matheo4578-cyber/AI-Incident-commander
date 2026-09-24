from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import boto3


def _response(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
        **payload,
    }


def _bounded_logs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:1000] for item in value[:20] if str(item).strip()]


def _bounded_metrics(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    metrics: dict[str, float] = {}
    for key, raw in list(value.items())[:50]:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            metrics[str(key)[:100]] = float(raw)
    return metrics


def _normalize(event: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(event.get("body"), str):
        try:
            event = json.loads(event["body"])
        except json.JSONDecodeError:
            return None
    detail = event.get("detail", {})
    if event.get("source") == "incident.commander" and isinstance(detail, dict):
        event = {**detail, "source": "eventbridge"}
        detail = {}
    if event.get("source") == "aws.cloudwatch" and detail.get("alarmName"):
        name = str(detail["alarmName"]).strip()[:100]
        reason = str(
            detail.get("state", {}).get("reason", "CloudWatch alarm entered ALARM")
        ).strip()[:5000]
        return {
            "incident_id": f"inc-{uuid4().hex[:12]}",
            "service": name,
            "title": f"CloudWatch alarm: {name}"[:200],
            "description": reason,
            "logs": [reason],
            "metrics": {},
            "source": "cloudwatch",
        }
    required = ("service", "title", "description")
    if all(isinstance(event.get(key), str) and event[key].strip() for key in required):
        return {
            "incident_id": f"inc-{uuid4().hex[:12]}",
            "service": event["service"].strip()[:100],
            "title": event["title"].strip()[:200],
            "description": event["description"].strip()[:5000],
            "logs": _bounded_logs(event.get("logs")),
            "metrics": _bounded_metrics(event.get("metrics")),
            "source": str(event.get("source", "lambda")).strip()[:50] or "lambda",
        }
    return None


def handler(
    event: dict[str, Any], context: Any, *, sqs_client: Any | None = None
) -> dict[str, Any]:
    del context
    queue_url = os.environ.get("INCIDENT_QUEUE_URL")
    if not queue_url:
        return _response(500, {"error": "Incident queue is not configured"})
    incident = _normalize(event)
    if incident is None:
        return _response(400, {"error": "service, title, and description are required"})
    sqs = sqs_client or boto3.client("sqs")
    result = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(incident))
    return _response(
        202,
        {"incident_id": incident["incident_id"], "message_id": result["MessageId"]},
    )
