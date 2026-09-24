from fastapi.testclient import TestClient

from incident_commander.api import create_app


def test_health_endpoint_reports_ready() -> None:
    client = TestClient(create_app(llm_mode="deterministic"))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "incident-commander"}


def test_analyze_endpoint_returns_report() -> None:
    client = TestClient(create_app(llm_mode="deterministic"))

    response = client.post(
        "/api/incidents/analyze",
        json={
            "service": "checkout-api",
            "title": "Bad deployment",
            "description": "Errors started immediately after release v42",
            "logs": ["version=v42 AttributeError in checkout"],
            "metrics": {"error_rate": 0.31, "latency_ms": 1200},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"]
    assert body["severity"] == "critical"
    assert "deployment" in body["probable_root_cause"].lower()


def test_analyze_endpoint_rejects_caller_supplied_incident_id() -> None:
    client = TestClient(create_app(llm_mode="deterministic"))

    response = client.post(
        "/api/incidents/analyze",
        json={
            "incident_id": "inc-attacker-chosen",
            "service": "checkout-api",
            "title": "Errors",
            "description": "Requests fail",
        },
    )

    assert response.status_code == 422


def test_dashboard_is_served() -> None:
    client = TestClient(create_app(llm_mode="deterministic"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Incident Commander" in response.text
