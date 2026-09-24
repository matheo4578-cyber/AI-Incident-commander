import json

from lambda_src.handler import handler


class FakeSQS:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send_message(self, **kwargs: str) -> dict[str, str]:
        self.messages.append(kwargs)
        return {"MessageId": "message-123"}


def test_lambda_normalizes_cloudwatch_alarm_and_queues_it(monkeypatch) -> None:
    sqs = FakeSQS()
    monkeypatch.setenv("INCIDENT_QUEUE_URL", "https://sqs.example/incidents")
    event = {
        "source": "aws.cloudwatch",
        "detail-type": "CloudWatch Alarm State Change",
        "detail": {
            "alarmName": "checkout-errors",
            "state": {"value": "ALARM", "reason": "Error rate is above 20%"},
            "configuration": {"metrics": []},
        },
        "resources": ["arn:aws:cloudwatch:us-east-1:123:alarm:checkout-errors"],
    }

    result = handler(event, None, sqs_client=sqs)

    assert result["statusCode"] == 202
    queued = json.loads(sqs.messages[0]["MessageBody"])
    assert queued["service"] == "checkout-errors"
    assert queued["source"] == "cloudwatch"
    assert sqs.messages[0]["QueueUrl"] == "https://sqs.example/incidents"


def test_lambda_accepts_custom_eventbridge_incident(monkeypatch) -> None:
    sqs = FakeSQS()
    monkeypatch.setenv("INCIDENT_QUEUE_URL", "https://sqs.example/incidents")
    event = {
        "source": "incident.commander",
        "detail-type": "Incident Report",
        "detail": {
            "incident_id": "inc-caller-controlled",
            "service": "home-lab-frigate",
            "title": "Camera processing degraded",
            "description": "Detector latency crossed its threshold",
            "logs": ["detector inference timeout"],
            "metrics": {"latency_ms": 2400},
        },
    }

    result = handler(event, None, sqs_client=sqs)

    assert result["statusCode"] == 202
    queued = json.loads(sqs.messages[0]["MessageBody"])
    assert queued["service"] == "home-lab-frigate"
    assert queued["source"] == "eventbridge"
    assert queued["incident_id"] != "inc-caller-controlled"
    assert queued["incident_id"].startswith("inc-")


def test_lambda_rejects_unusable_payload(monkeypatch) -> None:
    monkeypatch.setenv("INCIDENT_QUEUE_URL", "https://sqs.example/incidents")

    result = handler({}, None, sqs_client=FakeSQS())

    assert result["statusCode"] == 400
