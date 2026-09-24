import pytest
from pydantic import ValidationError

from incident_commander.models import IncidentInput


def test_incident_rejects_blank_service() -> None:
    with pytest.raises(ValidationError):
        IncidentInput(service=" ", title="API errors", description="Requests fail")


def test_incident_normalizes_signal_collections() -> None:
    incident = IncidentInput(
        service="checkout-api",
        title="Latency spike",
        description="Checkout latency exceeded the SLO",
        logs=[" timeout ", ""],
        metrics={"cpu_percent": 94.5},
    )

    assert incident.logs == ["timeout"]
    assert incident.metrics == {"cpu_percent": 94.5}
