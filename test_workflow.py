from incident_commander.models import IncidentInput
from incident_commander.workflow import build_workflow


def test_workflow_produces_evidence_based_report_for_memory_leak() -> None:
    workflow = build_workflow(llm_mode="deterministic")
    incident = IncidentInput(
        service="payments-api",
        title="Pods restarting",
        description="Memory rises continuously until pods restart",
        logs=["OOMKilled container payments", "restart count=8"],
        metrics={"memory_percent": 97, "error_rate": 0.18, "latency_ms": 1800},
    )

    report = workflow.analyze(incident)

    assert report.status == "completed"
    assert report.severity == "critical"
    assert "memory" in report.probable_root_cause.lower()
    assert any("OOMKilled" in item for item in report.evidence)
    assert report.requires_human_approval is True
    assert report.agents_run == [
        "triage",
        "metrics",
        "logs",
        "root_cause",
        "runbook",
        "commander",
    ]


def test_workflow_uses_lower_risk_branch_for_minor_incident() -> None:
    workflow = build_workflow(llm_mode="deterministic")
    incident = IncidentInput(
        service="catalog-api",
        title="Small latency increase",
        description="Latency is slightly above normal",
        logs=["request completed slowly"],
        metrics={"latency_ms": 650, "error_rate": 0.01},
    )

    report = workflow.analyze(incident)

    assert report.severity == "low"
    assert report.agents_run[:3] == ["triage", "logs", "metrics"]


def test_workflow_never_claims_automatic_remediation() -> None:
    workflow = build_workflow(llm_mode="deterministic")
    report = workflow.analyze(
        IncidentInput(
            service="orders-db",
            title="Connection saturation",
            description="Clients cannot acquire database connections",
            logs=["connection pool exhausted"],
            metrics={"db_connections_percent": 99, "error_rate": 0.4},
        )
    )

    assert report.requires_human_approval is True
    assert all("automatically executed" not in action.lower() for action in report.recommendations)
